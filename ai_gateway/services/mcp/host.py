"""
Generic MCP host helpers used by FabriX Chat runtimes and MCP command routes.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
from typing import Any, cast

from fastapi import HTTPException

from .config import (
    DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
    DOC_SEARCH_PROVIDER_ID,
    McpSettings,
)
from .context_merge import build_multi_file_system_prompt, merge_system_prompts
from .doc_search_policy import (
    DOC_SEARCH_DEFAULT_MAX_DOCS,
    DOC_SEARCH_DEFAULT_SNIPPET_CHARS,
    normalize_doc_search_rag_params,
)
from .mcp_plan_executor import McpPlanExecutor
from .providers import get_provider_manifest, require_provider_manifest
from .rag_context import (
    LEXGUARD_LEGAL_ACTIONS,
    build_rag_response,
    render_legal_context_system_prompt,
)
from .registry import connect_provider
from .result_normalizer import tool_result_to_dict
from .shared_planner.core import SharedPlannerCore
from .shared_planner.models import PlannerDecision, PlannerToolPlan


logger = logging.getLogger(__name__)

_PLANNER_INTERNAL_PARAMS = frozenset({"full_read_mode"})


@dataclass(frozen=True)
class McpChatResolution:
    route: str
    system_prompt: str | None
    missing_mentions: list[str]
    context_results: tuple[dict[str, Any], ...] = ()
    decision: PlannerDecision | None = None
    # True when MCP actually contributed context (route != "chat_only" and system_prompt produced).
    # Used by NormalChatRuntime to emit a single "MCP activated" system event on success.
    activated: bool = False


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


def render_context_result_system_prompt(
    context_result: dict[str, Any],
    *,
    test_mode: bool = False,
) -> str | None:
    system_prompt = context_result.get("system_prompt")
    if system_prompt:
        return str(system_prompt)

    action = context_result.get("action")
    if action in LEXGUARD_LEGAL_ACTIONS:
        structured_result = context_result.get("structured_result")
        if isinstance(structured_result, dict):
            return render_legal_context_system_prompt(
                structured_result,
                test_mode=test_mode,
            )

    return None


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
    test_mode: bool = False,
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

    # lexguard legal tools: preserve structured results and defer prompt rendering
    # until the final normal-mode LLM boundary.
    if action in LEXGUARD_LEGAL_ACTIONS:
        return {
            "action": action,
            "arguments": resolved_arguments,
            "query": resolved_arguments.get("query"),
            "category": resolved_arguments.get("category"),
            "raw_result": raw_result_dict,
            "system_prompt": None,
            "structured_result": raw_result_dict,
        }

    # read_doc: wrap full content for downstream chaining (document_issue_tool).
    # system_prompt is intentionally None — the content is consumed by chaining, not injected
    # into the chat context directly.
    if action == "read_doc":
        # Normalize read_doc result so extract_document_text_from_result always finds
        # a "content" key for downstream chaining (document_issue_tool).
        #
        # The fastmcp server may return the document text under different keys:
        #   - {"raw_text": "..."}  — bare string result (no JSON), stored by tool_result_to_dict
        #   - {"result": "..."}   — structured_content response from fastmcp server
        # Both must be normalized to {"content": "..."}.
        if "content" not in raw_result_dict:
            doc_text = raw_result_dict.get("raw_text") or raw_result_dict.get("result")
            if doc_text and isinstance(doc_text, str):
                raw_result_dict = {"content": doc_text}
        return {
            "action": action,
            "arguments": resolved_arguments,
            "query": resolved_arguments.get("query"),
            "category": resolved_arguments.get("category"),
            "filename": resolved_arguments.get("filename"),
            "raw_result": raw_result_dict,
            "system_prompt": None,
            "structured_result": raw_result_dict,
        }

    return {
        "action": action,
        "arguments": resolved_arguments,
        "query": resolved_arguments.get("query"),
        "category": resolved_arguments.get("category"),
        "raw_result": raw_result_dict,
        "system_prompt": raw_result_dict.get("system_prompt"),
        "structured_result": raw_result_dict,
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
                "structured_result": context_result.get("structured_result"),
            }
        )
        final_system_prompt = merge_system_prompts(
            final_system_prompt, context_result.get("system_prompt")
        )

    return {
        "fragment_count": len(fragments),
        "fragments": fragments,
        "base_system_prompt": base_system_prompt,
        "final_system_prompt": final_system_prompt,
    }


class GenericMcpHost:
    def __init__(self, settings: McpSettings, planner: SharedPlannerCore | None = None):
        self.settings = settings
        self._test_mode = settings.host.test_mode
        enabled_providers = settings.enabled_provider_configs()
        self.default_provider_id = (
            enabled_providers[0].provider_id
            if enabled_providers
            else DOC_SEARCH_PROVIDER_ID
        )
        self._planner_provider_categories_cache: dict[str, tuple[str, ...]] | None = (
            None
        )
        self._planner_categories_lock = asyncio.Lock()
        rule_refs = tuple(
            dict.fromkeys(
                provider.activation_rule_ref
                or DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF
                for provider in enabled_providers
            )
        )
        self._planner = planner or SharedPlannerCore(
            default_provider_id=self.default_provider_id,
            activation_rule_ref=rule_refs[0]
            if rule_refs
            else DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
            activation_rule_refs=rule_refs,
            doc_search_settings=settings.host.doc_search,
        )

    async def build_planner_provider_categories(self) -> dict[str, tuple[str, ...]]:
        if self._planner_provider_categories_cache is not None:
            return dict(self._planner_provider_categories_cache)

        async with self._planner_categories_lock:
            # Double-checked locking: re-check after acquiring the lock
            if self._planner_provider_categories_cache is not None:
                return dict(self._planner_provider_categories_cache)

            provider_categories: dict[str, tuple[str, ...]] = {}
            for provider_config in self.settings.enabled_provider_configs():
                manifest = get_provider_manifest(provider_config.provider_id)
                if manifest is None:
                    continue
                capability_policy = manifest.capability_policy
                if (
                    capability_policy is not None
                    and not capability_policy.supports_category_catalog
                ):
                    continue
                try:
                    categories = await self.list_category_catalog(
                        provider_id=provider_config.provider_id
                    )
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

    def _require_tool_action_supported(
        self, action: str, *, provider_id: str | None = None
    ) -> str:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        manifest = require_provider_manifest(resolved_provider_id)
        capability_policy = manifest.capability_policy
        if capability_policy is None:
            return resolved_provider_id

        if action == "search_docs_rag" and not capability_policy.supports_rag_context:
            raise ValueError(
                f"MCP provider does not support RAG context search: {resolved_provider_id}"
            )
        if action == "search_docs" and not capability_policy.supports_search:
            raise ValueError(
                f"MCP provider does not support search: {resolved_provider_id}"
            )
        if action == "read_doc" and not capability_policy.supports_document_read:
            raise ValueError(
                f"MCP provider does not support document read: {resolved_provider_id}"
            )
        if (
            action
            in {"list_category_catalog", "list_categories_detail", "list_docs_detail"}
            and not capability_policy.supports_category_catalog
        ):
            raise ValueError(
                f"MCP provider does not support category listing: {resolved_provider_id}"
            )
        return resolved_provider_id

    def _require_manual_command_supported(
        self, action: str, *, provider_id: str | None = None
    ) -> str:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        manifest = require_provider_manifest(resolved_provider_id)
        capability_policy = manifest.capability_policy
        if capability_policy is None or not capability_policy.manual_commands:
            return resolved_provider_id
        if action not in capability_policy.manual_commands:
            raise ValueError(
                f"Manual MCP command is not supported by provider: {resolved_provider_id}.{action}"
            )
        return resolved_provider_id

    @staticmethod
    def _action_uses_category(
        action: str, arguments: dict[str, Any] | None = None
    ) -> bool:
        if arguments is None:
            return False
        category = arguments.get("category")
        if not isinstance(category, str) or not category.strip():
            return False
        return action in {
            "search_docs_rag",
            "search_docs",
            "list_docs_detail",
            "read_doc",
        }

    async def _validate_plan(self, plan) -> None:
        resolved_provider_id = self._require_tool_action_supported(
            plan.action, provider_id=plan.provider
        )
        if self._action_uses_category(plan.action, plan.params):
            await self.validate_category(
                str(plan.params["category"]), provider_id=resolved_provider_id
            )

    async def validate_planner_decision(self, decision: PlannerDecision) -> None:
        for plan in decision.plans:
            await self._validate_plan(plan)

    async def discover_provider_capabilities(
        self, *, provider_id: str | None = None
    ) -> dict[str, Any]:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        async with connect_provider(
            resolved_provider_id, settings=self.settings
        ) as provider:
            if not hasattr(provider, "list_capabilities"):
                raise ValueError(
                    f"MCP provider does not support capability discovery: {resolved_provider_id}"
                )
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
        async with connect_provider(
            resolved_provider_id, settings=self.settings
        ) as provider:
            provider_method = getattr(provider, action, None)
            if callable(provider_method):
                provider_callable = cast(
                    Callable[..., Awaitable[Any]],
                    provider_method,
                )
                return await provider_callable(**tool_arguments)
            if hasattr(provider, "call_tool_dict"):
                call_tool_dict = cast(
                    Callable[[str, dict[str, Any]], Awaitable[Any]],
                    provider.call_tool_dict,
                )
                return await call_tool_dict(action, tool_arguments)
            raise ValueError(
                f"MCP provider does not support action: {resolved_provider_id}.{action}"
            )

    async def execute_tool_action(
        self,
        *,
        action: str,
        arguments: dict[str, Any] | None = None,
        provider_id: str | None = None,
    ) -> Any:
        self._require_tool_action_supported(action, provider_id=provider_id)
        clean_arguments = {
            key: value
            for key, value in (arguments or {}).items()
            if key not in _PLANNER_INTERNAL_PARAMS
        }
        return await self._call_provider_action(
            action=action,
            arguments=clean_arguments,
            provider_id=provider_id,
        )

    async def list_category_catalog(
        self, *, provider_id: str | None = None
    ) -> list[dict[str, Any]]:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        manifest = require_provider_manifest(resolved_provider_id)
        capability_policy = manifest.capability_policy
        if (
            capability_policy is not None
            and not capability_policy.supports_category_catalog
        ):
            raise ValueError(
                f"MCP provider does not support category listing: {resolved_provider_id}"
            )
        async with connect_provider(
            resolved_provider_id, settings=self.settings
        ) as provider:
            provider_method = getattr(provider, "list_category_catalog", None)
            if not callable(provider_method):
                raise ValueError(
                    f"MCP provider does not support category listing: {resolved_provider_id}"
                )
            list_category_catalog = cast(Callable[[], Awaitable[Any]], provider_method)
            categories = await list_category_catalog()
        return categories if isinstance(categories, list) else []

    async def validate_category(
        self, category: str, *, provider_id: str | None = None
    ) -> dict[str, Any]:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        manifest = require_provider_manifest(resolved_provider_id)
        capability_policy = manifest.capability_policy
        if (
            capability_policy is not None
            and not capability_policy.supports_category_catalog
        ):
            raise ValueError(
                f"MCP provider does not support category validation: {resolved_provider_id}"
            )
        async with connect_provider(
            resolved_provider_id, settings=self.settings
        ) as provider:
            provider_method = getattr(provider, "validate_category", None)
            if not callable(provider_method):
                raise ValueError(
                    f"MCP provider does not support category validation: {resolved_provider_id}"
                )
            validate_category = cast(
                Callable[[str], Awaitable[dict[str, Any]]],
                provider_method,
            )
            return await validate_category(category)

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
        resolved_provider_id = self._require_tool_action_supported(
            "search_docs_rag", provider_id=provider_id
        )
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
        if (
            capability_policy is not None
            and not capability_policy.supports_category_catalog
        ):
            return None

        categories = await self.list_category_catalog(provider_id=provider_id)
        category_names = [
            str(item.get("name", "")).strip()
            for item in categories
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        ]
        if not category_names:
            logger.warning(
                "Unscoped fanout RAG search skipped: category catalog returned no usable categories "
                "(provider_id=%s)",
                provider_id,
            )
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
            try:
                raw_result = await self._execute_raw_rag_search(
                    query=query,
                    category=category_name,
                    filename_filter=None,
                    max_docs=per_category_docs,
                    snippet_chars=snippet_chars,
                    provider_id=provider_id,
                )
            except Exception as exc:
                logger.warning(
                    "Unscoped fanout RAG search failed for category %r (provider_id=%s): %s",
                    category_name,
                    provider_id,
                    exc,
                )
                continue
            category_results.append((category_name, raw_result))

        if not category_results:
            logger.warning(
                "Unscoped fanout RAG search: all %d categor%s failed; returning None (provider_id=%s)",
                len(category_names),
                "y" if len(category_names) == 1 else "ies",
                provider_id,
            )
            return None

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
            limit=max(
                1,
                final_max_docs
                * max(2, self.settings.host.doc_search.prompt_max_per_doc),
            ),
            identity_builder=_snippet_identity,
        )

        return {
            "files": merged_files,
            "snippets": merged_snippets,
        }

    def _resolve_doc_search_plan_params(
        self, plan_params: dict[str, Any], *, default_query: str
    ) -> dict[str, Any]:
        return normalize_doc_search_rag_params(
            plan_params,
            query=str(plan_params.get("query", default_query)),
            settings=self.settings.host.doc_search,
        )

    async def _execute_context_plan(
        self, plan: PlannerToolPlan, *, default_query: str
    ) -> dict[str, Any]:
        if plan.action == "search_docs_rag":
            resolved_params = self._resolve_doc_search_plan_params(
                plan.params, default_query=default_query
            )
            context_result = await self.run_rag_search(
                query=str(resolved_params["query"]),
                category=resolved_params.get("category"),
                filename_filter=resolved_params.get("filename_filter"),
                max_docs=int(resolved_params["max_docs"]),
                snippet_chars=int(resolved_params["snippet_chars"]),
                provider_id=plan.provider,
            )
            raw_result = context_result.get("raw_result")
            if not isinstance(raw_result, dict):
                raw_result = {
                    "files": list(context_result.get("files") or []),
                    "snippets": list(context_result.get("snippets") or []),
                }
                retrieval_meta = context_result.get("retrieval_meta")
                if retrieval_meta is not None:
                    raw_result["retrieval_meta"] = retrieval_meta
            return {
                "raw_result": raw_result,
                "context_result": context_result,
                "system_prompt": context_result.get("system_prompt"),
            }

        raw_result = await self.execute_tool_action(
            action=plan.action,
            arguments=plan.params,
            provider_id=plan.provider,
        )
        context_result = normalize_context_result(
            action=plan.action,
            arguments=plan.params,
            raw_result=raw_result,
            doc_search_settings=self.settings.host.doc_search,
            test_mode=self._test_mode,
        )
        # Use the coerced dict from context_result as raw_result so that
        # extract_document_text_from_result (result chaining) always receives
        # a plain dict. Storing the raw CallToolResult object here would cause
        # isinstance(raw_result, dict) to fail and silently break chaining.
        return {
            "raw_result": context_result.get("raw_result") or {},
            "context_result": context_result,
            "system_prompt": context_result.get("system_prompt"),
        }

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
            return McpChatResolution(
                route="chat_only",
                system_prompt=None,
                context_results=(),
                missing_mentions=[],
                decision=decision,
            )

        if decision.route == "manual_mentions":
            missing_mentions: list[str] = []
            resolved_mentions: list[dict[str, Any]] = []

            for raw_target, plan in zip(decision.mentions, decision.plans):
                resolved_params = self._resolve_doc_search_plan_params(
                    plan.params, default_query=raw_target
                )
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
                context_results=(),
                missing_mentions=missing_mentions,
                decision=decision,
                activated=bool(system_prompt),
            )

        if not decision.plans:
            return McpChatResolution(
                route="chat_only",
                system_prompt=None,
                context_results=(),
                missing_mentions=[],
                decision=decision,
            )

        execution_result = await McpPlanExecutor().execute(
            decision=decision,
            execute_fn=lambda plan: self._execute_context_plan(
                plan, default_query=decision.clean_query
            ),
        )
        return McpChatResolution(
            route=decision.route,
            system_prompt=execution_result.system_prompt,
            context_results=execution_result.context_results,
            missing_mentions=[],
            decision=decision,
            activated=bool(execution_result.system_prompt)
            or any(
                bool(render_context_result_system_prompt(context_result))
                for context_result in execution_result.context_results
            ),
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
        resolved_provider_id = self._require_manual_command_supported(
            action, provider_id=provider_id
        )
        async with connect_provider(
            resolved_provider_id, settings=self.settings
        ) as provider:
            provider_command = getattr(provider, "execute_manual_command", None)
            if not callable(provider_command):
                raise ValueError(
                    f"Manual MCP commands are not supported by provider: {resolved_provider_id}"
                )
            execute_manual_command = cast(
                Callable[..., Awaitable[dict[str, Any]]],
                provider_command,
            )
            return await execute_manual_command(
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
    "render_context_result_system_prompt",
]
