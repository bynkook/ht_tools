"""Shared MCP plan execution loop for host-backed runtimes."""

from dataclasses import dataclass
import logging
from typing import Any, Awaitable, Callable

from .context_merge import merge_system_prompts
from .shared_planner.models import (
    PlannerDecision,
    PlannerDecisionProvenance,
    PlannerToolPlan,
)
from .shared_planner.result_chaining import (
    chain_document_text,
    extract_top_filename_from_rag_result,
    should_chain_doc_to_lexguard,
)


logger = logging.getLogger(__name__)

ExecutorHook = Callable[..., Awaitable[None]]


@dataclass(frozen=True)
class ExecutorHooks:
    on_plan_start: ExecutorHook | None = None
    on_tool_decision: ExecutorHook | None = None
    on_before_tool_call: ExecutorHook | None = None
    on_after_tool_call: ExecutorHook | None = None
    on_plan_inserted: ExecutorHook | None = None
    on_context_aggregated: ExecutorHook | None = None
    on_error: ExecutorHook | None = None


@dataclass(frozen=True)
class PlanExecutionResult:
    results: list[dict[str, Any]]
    system_prompt: str | None
    context_results: tuple[dict[str, Any], ...]
    plans: list[PlannerToolPlan]


class McpPlanExecutor:
    async def execute(
        self,
        *,
        decision: PlannerDecision,
        execute_fn: Callable[[PlannerToolPlan], Awaitable[dict[str, Any]]],
        hooks: ExecutorHooks | None = None,
    ) -> PlanExecutionResult:
        plans_list = self._normalize_plan_order(decision.plans)
        results: list[dict[str, Any]] = []
        system_prompt = None
        current_plan: PlannerToolPlan | None = None
        current_index = -1

        try:
            index = 0
            while index < len(plans_list):
                plan = plans_list[index]
                current_plan = plan
                current_index = index
                await self._invoke_hook(
                    hooks.on_plan_start if hooks else None,
                    plan=plan,
                    index=index,
                    total_plans=len(plans_list),
                    results=list(results),
                    system_prompt=system_prompt,
                )

                effective_plan = plan
                if index > 0 and results:
                    prev_plan = plans_list[index - 1]
                    prev_result = results[-1]
                    if should_chain_doc_to_lexguard(prev_plan.action, plan.action):
                        effective_plan = PlannerToolPlan(
                            provider=plan.provider,
                            action=plan.action,
                            params=chain_document_text(plan.params, prev_result),
                            provenance=plan.provenance,
                        )

                current_plan = effective_plan
                await self._invoke_hook(
                    hooks.on_tool_decision if hooks else None,
                    plan=effective_plan,
                    original_plan=plan,
                    index=index,
                    total_plans=len(plans_list),
                    results=list(results),
                )
                await self._invoke_hook(
                    hooks.on_before_tool_call if hooks else None,
                    plan=effective_plan,
                    original_plan=plan,
                    index=index,
                    total_plans=len(plans_list),
                    results=list(results),
                )

                # document_issue_tool: document_text 필수 파라미터 검증
                if effective_plan.action == "document_issue_tool":
                    doc_text = effective_plan.params.get("document_text")
                    if not doc_text or not str(doc_text).strip():
                        logger.warning(
                            "[MCP executor] document_issue_tool 실행 취소: "
                            "document_text가 비어 있습니다 (search_docs_rag 결과 없음). "
                            "index=%d",
                            index,
                        )
                        skipped_result: dict[str, Any] = {
                            "raw_result": {
                                "skipped": True,
                                "reason": "search_docs_rag returned no results — document_text is empty",
                            },
                            "action": "document_issue_tool",
                            "skipped": True,
                            "reason": "search_docs_rag returned no results — document_text is empty",
                        }
                        results.append(skipped_result)
                        await self._invoke_hook(
                            hooks.on_after_tool_call if hooks else None,
                            plan=effective_plan,
                            original_plan=plan,
                            index=index,
                            total_plans=len(plans_list),
                            result=skipped_result,
                            results=list(results),
                            system_prompt=system_prompt,
                        )
                        index += 1
                        continue

                result = await execute_fn(effective_plan)
                results.append(result)
                system_prompt = merge_system_prompts(
                    system_prompt,
                    result.get("system_prompt")
                    or self._get_context_result(result).get("system_prompt"),
                )
                await self._invoke_hook(
                    hooks.on_after_tool_call if hooks else None,
                    plan=effective_plan,
                    original_plan=plan,
                    index=index,
                    total_plans=len(plans_list),
                    result=result,
                    results=list(results),
                    system_prompt=system_prompt,
                )

                next_index = index + 1
                if (
                    plan.params.get("full_read_mode")
                    and next_index < len(plans_list)
                    and plans_list[next_index].action == "document_issue_tool"
                ):
                    top_filename = extract_top_filename_from_rag_result(result)
                    if top_filename:
                        search_category = plan.params.get("category")
                        read_doc_params: dict[str, Any] = {"filename": top_filename}
                        if search_category:
                            read_doc_params["category"] = search_category
                        read_doc_plan = PlannerToolPlan(
                            provider=plan.provider,
                            action="read_doc",
                            params=read_doc_params,
                            provenance=PlannerDecisionProvenance(
                                decision_source="dynamic_full_read",
                                matched_rule="full_read_mode_insertion",
                                normalized_query=decision.clean_query,
                                provider_candidates=(f"{plan.provider}.read_doc",),
                                selected_provider=plan.provider,
                                selected_action="read_doc",
                                reason=(
                                    f"Dynamically inserted read_doc for '{top_filename}' "
                                    "because search_docs_rag was co-matched with document_issue_tool "
                                    "(full_read_mode). Snippet text is insufficient for full document analysis."
                                ),
                            ),
                        )
                        plans_list.insert(next_index, read_doc_plan)
                        logger.info(
                            "[MCP full_read_mode] Inserted read_doc plan for '%s' "
                            "(category=%r) between search_docs_rag and document_issue_tool.",
                            top_filename,
                            search_category,
                        )
                        await self._invoke_hook(
                            hooks.on_plan_inserted if hooks else None,
                            inserted_plan=read_doc_plan,
                            trigger_plan=plan,
                            index=next_index,
                            total_plans=len(plans_list),
                            results=list(results),
                        )
                    else:
                        logger.warning(
                            "[MCP full_read_mode] TOP1 filename not found in search_docs_rag result. "
                            "Falling back to snippet-based chaining for document_issue_tool."
                        )

                index += 1

            context_results = [self._get_context_result(result) for result in results]
            await self._invoke_hook(
                hooks.on_context_aggregated if hooks else None,
                results=list(results),
                context_results=context_results,
                plans=list(plans_list),
                system_prompt=system_prompt,
            )
            return PlanExecutionResult(
                results=results,
                system_prompt=system_prompt,
                context_results=tuple(context_results),
                plans=list(plans_list),
            )
        except Exception as error:
            logger.error(
                "[MCP executor] Plan execution failed at index %d (action=%r): %s",
                current_index,
                current_plan.action if current_plan else "unknown",
                error,
                exc_info=True,
            )
            await self._invoke_hook(
                hooks.on_error if hooks else None,
                error=error,
                plan=current_plan,
                index=current_index,
                total_plans=len(plans_list),
                results=list(results),
                system_prompt=system_prompt,
                plans=list(plans_list),
            )
            raise

    @staticmethod
    def _get_context_result(result: dict[str, Any]) -> dict[str, Any]:
        context_result = result.get("context_result")
        if isinstance(context_result, dict):
            return context_result
        return result

    @staticmethod
    def _normalize_plan_order(
        plans: tuple[PlannerToolPlan, ...],
    ) -> list[PlannerToolPlan]:
        """Normalize supported document-retrieval chains for execution.

        Combined provider catalogs can legitimately order a legal-analysis tool
        ahead of the internal-docs retrieval step because catalog priority is
        global across providers. The executor, however, must run the retrieval
        step before `document_issue_tool` so result chaining can supply
        `document_text` on the unified path.

        Scope is intentionally narrow: only move a full-read `search_docs_rag`
        plan ahead of the first later `document_issue_tool` plan.
        """
        normalized = list(plans)
        for search_idx, plan in enumerate(normalized):
            if plan.action != "search_docs_rag":
                continue
            if not plan.params.get("full_read_mode"):
                continue

            issue_idx = next(
                (
                    idx
                    for idx, candidate in enumerate(normalized)
                    if idx < search_idx and candidate.action == "document_issue_tool"
                ),
                None,
            )
            if issue_idx is None:
                continue

            search_plan = normalized.pop(search_idx)
            normalized.insert(issue_idx, search_plan)

        return normalized

    @staticmethod
    async def _invoke_hook(hook: ExecutorHook | None, **kwargs: Any) -> None:
        if hook is None:
            return
        await hook(**kwargs)


__all__ = ["ExecutorHooks", "McpPlanExecutor", "PlanExecutionResult"]
