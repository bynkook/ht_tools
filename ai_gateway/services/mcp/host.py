"""
Generic MCP host helpers used by FabriX Chat runtimes and MCP command routes.
"""

from dataclasses import dataclass
import logging
from typing import Any

from fastapi import HTTPException

from .config import DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF, DOC_SEARCH_PROVIDER_ID, McpSettings
from .context_merge import build_multi_file_system_prompt, merge_system_prompts
from .doc_search_policy import (
    DOC_SEARCH_DEFAULT_MAX_DOCS,
    DOC_SEARCH_DEFAULT_SNIPPET_CHARS,
    normalize_doc_search_rag_params,
)
from .providers import get_provider_manifest, require_provider_manifest
from .rag_context import build_rag_response
from .registry import connect_provider
from .result_normalizer import tool_result_to_dict
from .shared_planner.core import SharedPlannerCore
from .shared_planner.models import PlannerDecision


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class McpChatResolution:
    route: str
    system_prompt: str | None
    missing_mentions: list[str]
    decision: PlannerDecision | None = None


def _coerce_result_dict(raw_result: Any) -> dict[str, Any]:
    if isinstance(raw_result, dict):
        return raw_result
    if hasattr(raw_result, "structured_content") or hasattr(raw_result, "content"):
        return tool_result_to_dict(raw_result)
    return {"value": raw_result}


def _context_fragment_type(context_result: dict[str, Any]) -> str:
    if context_result.get("snippets") or context_result.get("files"):
        return "rag_context"
    if context_result.get("system_prompt"):
        return "system_prompt"
    return "tool_result"


def _with_category(items: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        next_item = dict(item)
        next_item.setdefault("category", category)
        enriched.append(next_item)
    return enriched


def _doc_identity(item: dict[str, Any]) -> tuple[str | None, str]:
    return (item.get("category"), str(item.get("filename", "")))


def _snippet_identity(item: dict[str, Any]) -> tuple[str | None, str, Any, Any]:
    return (
        item.get("category"),
        str(item.get("filename", "")),
        item.get("start"),
        item.get("end"),
    )


def _round_robin_merge(
    grouped_items: list[tuple[str, list[dict[str, Any]]]],
    *,
    limit: int,
    identity_builder,
) -> list[dict[str, Any]]:
    queues = [(category, list(items)) for category, items in grouped_items if items]
    merged: list[dict[str, Any]] = []
    seen: set[Any] = set()

    while queues and len(merged) < limit:
        next_queues: list[tuple[str, list[dict[str, Any]]]] = []
        for category, items in queues:
            while items:
                candidate = items.pop(0)
                identity = identity_builder(candidate)
                if identity in seen:
                    continue
                seen.add(identity)
                merged.append(candidate)
                break
            if items:
                next_queues.append((category, items))
            if len(merged) >= limit:
                break
        queues = next_queues

    return merged


def normalize_context_result(
    *,
    action: str,
    arguments: dict[str, Any] | None,
    raw_result: Any,
    doc_search_settings=None,
) -> dict[str, Any]:
    resolved_arguments = dict(arguments or {})
    if action == "search_docs_rag":
        return build_rag_response(
            query=str(resolved_arguments.get("query", "")),
            category=resolved_arguments.get("category"),
            filename_filter=resolved_arguments.get("filename_filter"),
            data=_coerce_result_dict(raw_result),
            doc_search_settings=doc_search_settings,
        )

    raw_result_dict = _coerce_result_dict(raw_result)
    return {
        "action": action,
        "arguments": resolved_arguments,
        "query": resolved_arguments.get("query"),
        "category": resolved_arguments.get("category"),
        "raw_result": raw_result_dict,
        "system_prompt": raw_result_dict.get("system_prompt"),
    }


def build_context_debug_payload(
    *,
    base_system_prompt: str | None,
    context_results: list[dict[str, Any]],
) -> dict[str, Any]:
    fragments = []
    final_system_prompt = base_system_prompt

    for context_result in context_results:
        fragments.append(
            {
                "type": _context_fragment_type(context_result),
                "action": context_result.get("action"),
                "query": context_result.get("query"),
                "category": context_result.get("category"),
                "files": context_result.get("files", []),
                "snippets": context_result.get("snippets", []),
                "system_prompt": context_result.get("system_prompt"),
            }
        )
        final_system_prompt = merge_system_prompts(final_system_prompt, context_result.get("system_prompt"))

    return {
        "fragment_count": len(fragments),
        "fragments": fragments,
        "base_system_prompt": base_system_prompt,
        "final_system_prompt": final_system_prompt,
    }


class GenericMcpHost:
    def __init__(self, settings: McpSettings, planner: SharedPlannerCore | None = None):
        self.settings = settings
        enabled_providers = settings.enabled_provider_configs()
        self.default_provider_id = enabled_providers[0].provider_id if enabled_providers else DOC_SEARCH_PROVIDER_ID
        self._planner_provider_categories_cache: dict[str, tuple[str, ...]] | None = None
        rule_refs = tuple(
            dict.fromkeys(
                provider.activation_rule_ref or DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF
                for provider in enabled_providers
            )
        )
        self._planner = planner or SharedPlannerCore(
            default_provider_id=self.default_provider_id,
            activation_rule_ref=rule_refs[0] if rule_refs else DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
            activation_rule_refs=rule_refs,
            doc_search_settings=settings.host.doc_search,
        )

    async def build_planner_provider_categories(self) -> dict[str, tuple[str, ...]]:
        if self._planner_provider_categories_cache is not None:
            return dict(self._planner_provider_categories_cache)

        provider_categories: dict[str, tuple[str, ...]] = {}
        for provider_config in self.settings.enabled_provider_configs():
            manifest = get_provider_manifest(provider_config.provider_id)
            if manifest is None:
                continue
            capability_policy = manifest.capability_policy
            if capability_policy is not None and not capability_policy.supports_category_catalog:
                continue
            try:
                categories = await self.list_category_catalog(provider_id=provider_config.provider_id)
            except Exception as error:
                logger.warning(
                    "Planner category preload failed for provider %s: %s",
                    provider_config.provider_id,
                    error,
                )
                continue
            category_names = tuple(
                dict.fromkeys(
                    str(item.get("name", "")).strip()
                    for item in categories
                    if str(item.get("name", "")).strip()
                )
            )
            if category_names:
                provider_categories[provider_config.provider_id] = category_names

        self._planner_provider_categories_cache = dict(provider_categories)
        return dict(provider_categories)

    def _resolve_provider_id(self, provider_id: str | None = None) -> str:
        resolved_provider_id = provider_id or self.default_provider_id
        self.settings.require_provider(resolved_provider_id)
        return resolved_provider_id

    def _require_tool_action_supported(self, action: str, *, provider_id: str | None = None) -> str:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        manifest = require_provider_manifest(resolved_provider_id)
        capability_policy = manifest.capability_policy
        if capability_policy is None:
            return resolved_provider_id

        if action == "search_docs_rag" and not capability_policy.supports_rag_context:
            raise ValueError(f"MCP provider does not support RAG context search: {resolved_provider_id}")
        if action == "search_docs" and not capability_policy.supports_search:
            raise ValueError(f"MCP provider does not support search: {resolved_provider_id}")
        if action == "read_doc" and not capability_policy.supports_document_read:
            raise ValueError(f"MCP provider does not support document read: {resolved_provider_id}")
        if action in {"list_category_catalog", "list_categories_detail", "list_docs_detail"} and not capability_policy.supports_category_catalog:
            raise ValueError(f"MCP provider does not support category listing: {resolved_provider_id}")
        return resolved_provider_id

    def _require_manual_command_supported(self, action: str, *, provider_id: str | None = None) -> str:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        manifest = require_provider_manifest(resolved_provider_id)
        capability_policy = manifest.capability_policy
        if capability_policy is None or not capability_policy.manual_commands:
            return resolved_provider_id
        if action not in capability_policy.manual_commands:
            raise ValueError(f"Manual MCP command is not supported by provider: {resolved_provider_id}.{action}")
        return resolved_provider_id

    @staticmethod
    def _action_uses_category(action: str, arguments: dict[str, Any] | None = None) -> bool:
        if arguments is None:
            return False
        category = arguments.get("category")
        if not isinstance(category, str) or not category.strip():
            return False
        return action in {"search_docs_rag", "search_docs", "list_docs_detail", "read_doc"}

    async def _validate_plan(self, plan) -> None:
        resolved_provider_id = self._require_tool_action_supported(plan.action, provider_id=plan.provider)
        if self._action_uses_category(plan.action, plan.params):
            await self.validate_category(str(plan.params["category"]), provider_id=resolved_provider_id)

    async def validate_planner_decision(self, decision: PlannerDecision) -> None:
        for plan in decision.plans:
            await self._validate_plan(plan)

    async def discover_provider_capabilities(self, *, provider_id: str | None = None) -> dict[str, Any]:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        async with connect_provider(resolved_provider_id, settings=self.settings) as provider:
            if not hasattr(provider, "list_capabilities"):
                raise ValueError(f"MCP provider does not support capability discovery: {resolved_provider_id}")
            return await provider.list_capabilities()

    async def _call_provider_action(
        self,
        *,
        action: str,
        arguments: dict[str, Any] | None = None,
        provider_id: str | None = None,
    ) -> Any:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        tool_arguments = dict(arguments or {})
        async with connect_provider(resolved_provider_id, settings=self.settings) as provider:
            provider_method = getattr(provider, action, None)
            if callable(provider_method):
                return await provider_method(**tool_arguments)
            if hasattr(provider, "call_tool_dict"):
                return await provider.call_tool_dict(action, tool_arguments)
            raise ValueError(f"MCP provider does not support action: {resolved_provider_id}.{action}")

    async def execute_tool_action(
        self,
        *,
        action: str,
        arguments: dict[str, Any] | None = None,
        provider_id: str | None = None,
    ) -> Any:
        self._require_tool_action_supported(action, provider_id=provider_id)
        return await self._call_provider_action(
            action=action,
            arguments=arguments,
            provider_id=provider_id,
        )

    async def list_category_catalog(self, *, provider_id: str | None = None) -> list[dict[str, Any]]:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        manifest = require_provider_manifest(resolved_provider_id)
        capability_policy = manifest.capability_policy
        if capability_policy is not None and not capability_policy.supports_category_catalog:
            raise ValueError(f"MCP provider does not support category listing: {resolved_provider_id}")
        async with connect_provider(resolved_provider_id, settings=self.settings) as provider:
            provider_method = getattr(provider, "list_category_catalog", None)
            if not callable(provider_method):
                raise ValueError(f"MCP provider does not support category listing: {resolved_provider_id}")
            categories = await provider_method()
        return categories if isinstance(categories, list) else []

    async def validate_category(self, category: str, *, provider_id: str | None = None) -> dict[str, Any]:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        manifest = require_provider_manifest(resolved_provider_id)
        capability_policy = manifest.capability_policy
        if capability_policy is not None and not capability_policy.supports_category_catalog:
            raise ValueError(f"MCP provider does not support category validation: {resolved_provider_id}")
        async with connect_provider(resolved_provider_id, settings=self.settings) as provider:
            provider_method = getattr(provider, "validate_category", None)
            if not callable(provider_method):
                raise ValueError(f"MCP provider does not support category validation: {resolved_provider_id}")
            return await provider_method(category)

    async def run_rag_search(
        self,
        *,
        query: str,
        category: str | None = None,
        filename_filter: str | None = None,
        max_docs: int | None = DOC_SEARCH_DEFAULT_MAX_DOCS,
        snippet_chars: int | None = DOC_SEARCH_DEFAULT_SNIPPET_CHARS,
        provider_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_provider_id = self._require_tool_action_supported("search_docs_rag", provider_id=provider_id)
        if category:
            await self.validate_category(category, provider_id=resolved_provider_id)
        data = await self._execute_rag_search_with_coverage(
            query=query,
            category=category,
            filename_filter=filename_filter,
            max_docs=max_docs,
            snippet_chars=snippet_chars,
            provider_id=resolved_provider_id,
        )
        logger.info(
            "RAG retrieval coverage — provider=%s category=%s mode=%s categories=%s files=%d snippets=%d",
            resolved_provider_id,
            category or "all",
            (data.get("retrieval_meta") or {}).get("mode", "direct"),
            len((data.get("retrieval_meta") or {}).get("categories_queried") or []),
            len(data.get("files") or []),
            len(data.get("snippets") or []),
        )
        return build_rag_response(
            query=query,
            category=category,
            filename_filter=filename_filter,
            data=data,
            doc_search_settings=self.settings.host.doc_search,
        )

    async def _execute_rag_search_with_coverage(
        self,
        *,
        query: str,
        category: str | None,
        filename_filter: str | None,
        max_docs: int | None,
        snippet_chars: int | None,
        provider_id: str,
    ) -> dict[str, Any]:
        if category or filename_filter:
            return await self._execute_raw_rag_search(
                query=query,
                category=category,
                filename_filter=filename_filter,
                max_docs=max_docs,
                snippet_chars=snippet_chars,
                provider_id=provider_id,
            )

        balanced = await self._execute_unscoped_balanced_rag_search(
            query=query,
            max_docs=max_docs,
            snippet_chars=snippet_chars,
            provider_id=provider_id,
        )
        if balanced is not None:
            return balanced

        return await self._execute_raw_rag_search(
            query=query,
            category=None,
            filename_filter=None,
            max_docs=max_docs,
            snippet_chars=snippet_chars,
            provider_id=provider_id,
        )

    async def _execute_raw_rag_search(
        self,
        *,
        query: str,
        category: str | None,
        filename_filter: str | None,
        max_docs: int | None,
        snippet_chars: int | None,
        provider_id: str,
    ) -> dict[str, Any]:
        arguments = normalize_doc_search_rag_params(
            {"max_docs": max_docs, "snippet_chars": snippet_chars},
            query=query,
            category=category,
            filename_filter=filename_filter,
            settings=self.settings.host.doc_search,
        )
        data = await self.execute_tool_action(
            action="search_docs_rag",
            arguments=arguments,
            provider_id=provider_id,
        )
        normalized = _coerce_result_dict(data)
        retrieval_meta = dict(normalized.get("retrieval_meta") or {})
        retrieval_meta.setdefault("mode", "direct")
        retrieval_meta.setdefault("categories_queried", [category] if category else [])
        normalized["retrieval_meta"] = retrieval_meta
        return normalized

    async def _execute_unscoped_balanced_rag_search(
        self,
        *,
        query: str,
        max_docs: int | None,
        snippet_chars: int | None,
        provider_id: str,
    ) -> dict[str, Any] | None:
        doc_search_settings = self.settings.host.doc_search
        if not doc_search_settings.unscoped_fanout_enabled:
            return None

        manifest = require_provider_manifest(provider_id)
        capability_policy = manifest.capability_policy
        if capability_policy is not None and not capability_policy.supports_category_catalog:
            return None

        categories = await self.list_category_catalog(provider_id=provider_id)
        category_names = [
            str(item.get("name", "")).strip()
            for item in categories
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        if not category_names:
            return None

        category_limit = doc_search_settings.unscoped_fanout_category_limit
        if category_limit > 0:
            category_names = category_names[:category_limit]

        per_category_docs = min(
            doc_search_settings.unscoped_fanout_per_category_docs,
            max_docs or doc_search_settings.max_docs,
        )
        if per_category_docs <= 0:
            return None

        category_results: list[tuple[str, dict[str, Any]]] = []
        for category_name in category_names:
            raw_result = await self._execute_raw_rag_search(
                query=query,
                category=category_name,
                filename_filter=None,
                max_docs=per_category_docs,
                snippet_chars=snippet_chars,
                provider_id=provider_id,
            )
            category_results.append((category_name, raw_result))

        merged = self._merge_unscoped_rag_results(
            category_results,
            final_max_docs=max_docs or doc_search_settings.max_docs,
        )
        merged["retrieval_meta"] = {
            "mode": "category_fanout",
            "categories_queried": category_names,
            "per_category_max_docs": per_category_docs,
            "category_count": len(category_names),
        }
        return merged

    def _merge_unscoped_rag_results(
        self,
        category_results: list[tuple[str, dict[str, Any]]],
        *,
        final_max_docs: int,
    ) -> dict[str, Any]:
        file_groups = [
            (category, _with_category(result.get("files", []) or [], category))
            for category, result in category_results
        ]
        snippet_groups = [
            (category, _with_category(result.get("snippets", []) or [], category))
            for category, result in category_results
        ]

        merged_files = _round_robin_merge(
            file_groups,
            limit=max(1, final_max_docs),
            identity_builder=_doc_identity,
        )
        merged_snippets = _round_robin_merge(
            snippet_groups,
            limit=max(1, final_max_docs * max(2, self.settings.host.doc_search.prompt_max_per_doc)),
            identity_builder=_snippet_identity,
        )

        return {
            "files": merged_files,
            "snippets": merged_snippets,
        }

    def _resolve_doc_search_plan_params(self, plan_params: dict[str, Any], *, default_query: str) -> dict[str, Any]:
        return normalize_doc_search_rag_params(
            plan_params,
            query=str(plan_params.get("query", default_query)),
            settings=self.settings.host.doc_search,
        )

    async def _execute_context_plan(self, plan, *, default_query: str) -> dict[str, Any]:
        if plan.action == "search_docs_rag":
            resolved_params = self._resolve_doc_search_plan_params(plan.params, default_query=default_query)
            return await self.run_rag_search(
                query=str(resolved_params["query"]),
                category=resolved_params.get("category"),
                filename_filter=resolved_params.get("filename_filter"),
                max_docs=int(resolved_params["max_docs"]),
                snippet_chars=int(resolved_params["snippet_chars"]),
                provider_id=plan.provider,
            )

        raw_result = await self.execute_tool_action(
            action=plan.action,
            arguments=plan.params,
            provider_id=plan.provider,
        )
        return normalize_context_result(
            action=plan.action,
            arguments=plan.params,
            raw_result=raw_result,
            doc_search_settings=self.settings.host.doc_search,
        )

    async def build_chat_resolution(
        self,
        *,
        user_text: str,
        active_category: str | None = None,
        rag_enabled: bool = False,
        provider_id: str | None = None,
    ) -> McpChatResolution:
        decision = self._planner.plan(
            user_text,
            active_category=active_category,
            rag_enabled=rag_enabled,
            provider_hint=provider_id,
        )
        if decision.route == "chat_only":
            provider_categories = await self.build_planner_provider_categories()
            if provider_categories:
                decision = self._planner.plan(
                    user_text,
                    active_category=active_category,
                    rag_enabled=rag_enabled,
                    provider_hint=provider_id,
                    provider_categories=provider_categories,
                )
        await self.validate_planner_decision(decision)

        if decision.route == "chat_only":
            return McpChatResolution(route="chat_only", system_prompt=None, missing_mentions=[], decision=decision)

        if decision.route == "manual_mentions":
            missing_mentions: list[str] = []
            resolved_mentions: list[dict[str, Any]] = []

            for raw_target, plan in zip(decision.mentions, decision.plans):
                resolved_params = self._resolve_doc_search_plan_params(plan.params, default_query=raw_target)
                try:
                    result = await self.run_rag_search(
                        query=str(resolved_params["query"]),
                        category=resolved_params.get("category"),
                        filename_filter=resolved_params.get("filename_filter"),
                        max_docs=int(resolved_params["max_docs"]),
                        snippet_chars=int(resolved_params["snippet_chars"]),
                        provider_id=plan.provider,
                    )
                except HTTPException as error:
                    if error.status_code == 404:
                        missing_mentions.append(raw_target)
                        continue
                    raise

                snippets = result.get("snippets") or []
                resolved_filename = (
                    resolved_params.get("filename_filter")
                    or (snippets[0].get("filename") if snippets else None)
                    or raw_target
                )
                resolved_mentions.append(
                    {
                        "filename": resolved_filename,
                        "snippets": snippets,
                    }
                )

            system_prompt = build_multi_file_system_prompt(resolved_mentions)
            if missing_mentions:
                quoted_mentions = ", ".join(f'@"{name}"' for name in missing_mentions)
                missing_prompt = (
                    "사용자가 지정한 일부 문서를 찾지 못했습니다.\n"
                    f"찾지 못한 대상: {quoted_mentions}\n"
                    "찾은 문서만 근거로 답변하고, 누락된 문서는 찾지 못했다고 명확히 설명하세요."
                )
                system_prompt = merge_system_prompts(system_prompt, missing_prompt)

            return McpChatResolution(
                route="manual_mentions",
                system_prompt=system_prompt,
                missing_mentions=missing_mentions,
                decision=decision,
            )

        if not decision.plans:
            return McpChatResolution(route="chat_only", system_prompt=None, missing_mentions=[], decision=decision)

        system_prompt = None
        for plan in decision.plans:
            context_result = await self._execute_context_plan(plan, default_query=decision.clean_query)
            system_prompt = merge_system_prompts(system_prompt, context_result.get("system_prompt"))
        return McpChatResolution(
            route=decision.route,
            system_prompt=system_prompt,
            missing_mentions=[],
            decision=decision,
        )

    async def execute_manual_command(
        self,
        *,
        action: str,
        query: str | None = None,
        target: str | None = None,
        category: str | None = None,
        filename: str | None = None,
        session_category: str | None = None,
        session_provider_id: str | None = None,
        rag_enabled: bool = False,
        max_results: int = 5,
        provider_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_provider_id = self._require_manual_command_supported(action, provider_id=provider_id)
        async with connect_provider(resolved_provider_id, settings=self.settings) as provider:
            provider_command = getattr(provider, "execute_manual_command", None)
            if not callable(provider_command):
                raise ValueError(f"Manual MCP commands are not supported by provider: {resolved_provider_id}")
            return await provider_command(
                action=action,
                query=query,
                target=target,
                category=category,
                filename=filename,
                session_category=session_category,
                session_provider_id=session_provider_id,
                rag_enabled=rag_enabled,
                max_results=max_results,
            )


__all__ = [
    "GenericMcpHost",
    "McpChatResolution",
    "build_context_debug_payload",
    "normalize_context_result",
]
