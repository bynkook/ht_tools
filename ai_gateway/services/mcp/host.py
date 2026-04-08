"""
Generic MCP host helpers used by FabriX Chat runtimes and MCP command routes.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from .config import DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF, DOC_SEARCH_PROVIDER_ID, McpSettings
from .context_merge import build_multi_file_system_prompt, merge_system_prompts
from .providers import require_provider_manifest
from .rag_context import build_rag_response
from .registry import connect_provider
from .result_normalizer import tool_result_to_dict
from .shared_planner.core import SharedPlannerCore
from .shared_planner.models import PlannerDecision


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


def normalize_context_result(*, action: str, arguments: dict[str, Any] | None, raw_result: Any) -> dict[str, Any]:
    resolved_arguments = dict(arguments or {})
    if action == "search_docs_rag":
        return build_rag_response(
            query=str(resolved_arguments.get("query", "")),
            category=resolved_arguments.get("category"),
            filename_filter=resolved_arguments.get("filename_filter"),
            data=_coerce_result_dict(raw_result),
        )

    return {
        "action": action,
        "arguments": resolved_arguments,
        "raw_result": _coerce_result_dict(raw_result),
        "system_prompt": None,
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
        self._planner_cache: dict[str, SharedPlannerCore] = {}
        base_provider = settings.require_provider(self.default_provider_id)
        self._planner_cache[self.default_provider_id] = planner or SharedPlannerCore(
            default_provider_id=self.default_provider_id,
            activation_rule_ref=base_provider.activation_rule_ref or DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
        )

    def _resolve_provider_id(self, provider_id: str | None = None) -> str:
        resolved_provider_id = provider_id or self.default_provider_id
        self.settings.require_provider(resolved_provider_id)
        return resolved_provider_id

    def _planner_for_provider(self, provider_id: str | None = None) -> SharedPlannerCore:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        cached = self._planner_cache.get(resolved_provider_id)
        if cached is not None:
            return cached
        provider_config = self.settings.require_provider(resolved_provider_id)
        planner_core = SharedPlannerCore(
            default_provider_id=resolved_provider_id,
            activation_rule_ref=provider_config.activation_rule_ref or DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
        )
        self._planner_cache[resolved_provider_id] = planner_core
        return planner_core

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
        return await self._call_provider_action(
            action=action,
            arguments=arguments,
            provider_id=provider_id,
        )

    async def list_category_catalog(self, *, provider_id: str | None = None) -> list[dict[str, Any]]:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        async with connect_provider(resolved_provider_id, settings=self.settings) as provider:
            if hasattr(provider, "list_category_catalog"):
                categories = await provider.list_category_catalog()
            elif hasattr(provider, "list_categories_detail"):
                detail = await provider.list_categories_detail()
                categories = detail.get("categories", []) if isinstance(detail, dict) else []
            else:
                raise ValueError(f"MCP provider does not support category listing: {resolved_provider_id}")
        return categories if isinstance(categories, list) else []

    async def validate_category(self, category: str, *, provider_id: str | None = None) -> dict[str, Any]:
        target = category.strip()
        if not target:
            raise ValueError("카테고리 이름을 입력하세요.")
        categories = await self.list_category_catalog(provider_id=provider_id)
        normalized_target = target.casefold()
        for item in categories:
            name = str(item.get("name", "")).strip()
            if name.casefold() == normalized_target:
                return item
        raise ValueError(f"카테고리를 찾을 수 없습니다: {category}")

    async def run_rag_search(
        self,
        *,
        query: str,
        category: str | None = None,
        filename_filter: str | None = None,
        max_docs: int = 10,
        snippet_chars: int = 1500,
        provider_id: str | None = None,
    ) -> dict[str, Any]:
        data = await self.execute_tool_action(
            action="search_docs_rag",
            arguments={
                "query": query,
                "category": category,
                "filename_filter": filename_filter,
                "max_docs": max_docs,
                "snippet_chars": snippet_chars,
            },
            provider_id=provider_id,
        )
        return build_rag_response(
            query=query,
            category=category,
            filename_filter=filename_filter,
            data=_coerce_result_dict(data),
        )

    async def build_chat_resolution(
        self,
        *,
        user_text: str,
        active_category: str | None = None,
        rag_enabled: bool = False,
        provider_id: str | None = None,
    ) -> McpChatResolution:
        decision = self._planner_for_provider(provider_id).plan(
            user_text,
            active_category=active_category,
            rag_enabled=rag_enabled,
        )

        if decision.route == "chat_only":
            return McpChatResolution(route="chat_only", system_prompt=None, missing_mentions=[], decision=decision)

        if decision.route == "manual_mentions":
            missing_mentions: list[str] = []
            resolved_mentions: list[dict[str, Any]] = []

            for raw_target, plan in zip(decision.mentions, decision.plans):
                try:
                    result = await self.run_rag_search(
                        query=str(plan.params.get("query", raw_target)),
                        category=plan.params.get("category"),
                        filename_filter=plan.params.get("filename_filter"),
                        max_docs=int(plan.params.get("max_docs", 10)),
                        snippet_chars=int(plan.params.get("snippet_chars", 1500)),
                        provider_id=plan.provider,
                    )
                except HTTPException as error:
                    if error.status_code == 404:
                        missing_mentions.append(raw_target)
                        continue
                    raise

                snippets = result.get("snippets") or []
                resolved_filename = (
                    plan.params.get("filename_filter")
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

        primary_plan = decision.plans[0]
        rag_result = await self.run_rag_search(
            query=str(primary_plan.params.get("query", decision.clean_query)),
            category=primary_plan.params.get("category"),
            filename_filter=primary_plan.params.get("filename_filter"),
            max_docs=int(primary_plan.params.get("max_docs", 10)),
            snippet_chars=int(primary_plan.params.get("snippet_chars", 1500)),
            provider_id=primary_plan.provider,
        )
        return McpChatResolution(
            route=decision.route,
            system_prompt=rag_result.get("system_prompt"),
            missing_mentions=[],
            decision=decision,
        )

    async def execute_manual_command(
        self,
        *,
        action: str,
        query: str | None = None,
        category: str | None = None,
        filename: str | None = None,
        max_results: int = 5,
        provider_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_provider_id = self._resolve_provider_id(provider_id)
        require_provider_manifest(resolved_provider_id)
        async with connect_provider(resolved_provider_id, settings=self.settings) as provider:
            provider_command = getattr(provider, "execute_manual_command", None)
            if not callable(provider_command):
                raise ValueError(f"Manual MCP commands are not supported by provider: {resolved_provider_id}")
            return await provider_command(
                action=action,
                query=query,
                category=category,
                filename=filename,
                max_results=max_results,
            )


__all__ = [
    "GenericMcpHost",
    "McpChatResolution",
    "build_context_debug_payload",
    "normalize_context_result",
]
