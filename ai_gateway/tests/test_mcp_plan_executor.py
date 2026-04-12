import asyncio
import logging
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from ai_gateway.services.mcp.mcp_plan_executor import ExecutorHooks, McpPlanExecutor
from ai_gateway.services.mcp.shared_planner.models import (
    PlannerDecision,
    PlannerDecisionProvenance,
    PlannerToolPlan,
)


def _make_plan(
    *,
    action: str,
    params: dict[str, Any] | None = None,
    provider: str = "internal_docs",
    query: str = "표준계약서 부당특약 검토",
) -> PlannerToolPlan:
    resolved_params = params or {}
    return PlannerToolPlan(
        provider=provider,
        action=action,
        params=resolved_params,
        provenance=PlannerDecisionProvenance(
            decision_source="keyword_rule",
            matched_rule=f"{provider}.{action}",
            normalized_query=query,
            provider_candidates=(f"{provider}.{action}",),
            selected_provider=provider,
            selected_action=action,
            active_category=resolved_params.get("category"),
            reason="keyword rule matched",
        ),
    )


def test_executor_runs_single_plan_without_chaining_or_full_read_mode():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="위약금 찾아줘",
        plans=(
            _make_plan(
                action="search_docs_rag",
                params={"query": "위약금", "category": "계약문서"},
            ),
        ),
    )
    observed: list[PlannerToolPlan] = []

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed.append(plan)
        return {
            "raw_result": {
                "snippets": [{"filename": "contract.md", "snippet": "위약금 조항"}]
            },
            "context_result": {"system_prompt": "=== 참고 문서 ===\n\n위약금 조항"},
            "system_prompt": "=== 참고 문서 ===\n\n위약금 조항",
        }

    result = asyncio.run(
        McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn)
    )

    assert [plan.action for plan in observed] == ["search_docs_rag"]
    assert len(result.results) == 1
    assert "위약금 조항" in (result.system_prompt or "")


def test_executor_chains_document_text_into_following_issue_plan():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(
            _make_plan(
                action="search_docs_rag",
                params={"query": "부당특약", "category": "계약문서"},
            ),
            _make_plan(action="document_issue_tool", params={"query": "부당특약 검토"}),
        ),
    )
    observed_arguments: list[dict[str, Any]] = []

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_arguments.append(dict(plan.params))
        if plan.action == "search_docs_rag":
            return {
                "raw_result": {
                    "snippets": [
                        {"filename": "contract.md", "snippet": "계약서 전문 일부"}
                    ],
                    "files": [{"filename": "contract.md"}],
                },
                "context_result": {"system_prompt": "search prompt"},
                "system_prompt": "search prompt",
            }
        if plan.action == "document_issue_tool":
            return {
                "raw_result": {"issues": []},
                "context_result": {"system_prompt": "issue prompt"},
                "system_prompt": "issue prompt",
            }
        raise AssertionError(plan.action)

    asyncio.run(McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn))

    assert observed_arguments[1]["document_text"] == "계약서 전문 일부"


def test_executor_inserts_read_doc_for_full_read_mode_before_issue_tool():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(
            _make_plan(
                action="search_docs_rag",
                params={
                    "query": "부당특약",
                    "category": "계약문서",
                    "full_read_mode": True,
                },
            ),
            _make_plan(action="document_issue_tool", params={"query": "부당특약 검토"}),
        ),
    )
    observed_actions: list[str] = []
    observed_issue_arguments: dict[str, Any] = {}
    inserted: list[PlannerToolPlan] = []

    async def on_plan_inserted(**kwargs: Any) -> None:
        inserted.append(kwargs["inserted_plan"])

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_actions.append(plan.action)
        if plan.action == "search_docs_rag":
            return {
                "raw_result": {
                    "snippets": [
                        {"filename": "표준계약서.md", "snippet": "계약서 일부"}
                    ],
                    "files": [{"filename": "표준계약서.md"}],
                },
                "context_result": {"system_prompt": None},
                "system_prompt": None,
            }
        if plan.action == "read_doc":
            return {
                "raw_result": {
                    "content": "전체 계약서 전문 내용입니다.",
                    "filename": "표준계약서.md",
                },
                "context_result": {"system_prompt": None},
                "system_prompt": None,
            }
        if plan.action == "document_issue_tool":
            observed_issue_arguments.update(plan.params)
            return {
                "raw_result": {"issues": []},
                "context_result": {"system_prompt": "issue prompt"},
                "system_prompt": "issue prompt",
            }
        raise AssertionError(plan.action)

    asyncio.run(
        McpPlanExecutor().execute(
            decision=decision,
            execute_fn=execute_fn,
            hooks=ExecutorHooks(on_plan_inserted=on_plan_inserted),
        )
    )

    assert observed_actions == ["search_docs_rag", "read_doc", "document_issue_tool"]
    assert inserted[0].action == "read_doc"
    assert inserted[0].params == {"filename": "표준계약서.md", "category": "계약문서"}
    assert observed_issue_arguments["document_text"] == "전체 계약서 전문 내용입니다."


def test_executor_full_read_mode_falls_back_when_filename_missing(
    caplog: pytest.LogCaptureFixture,
):
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(
            _make_plan(
                action="search_docs_rag",
                params={
                    "query": "부당특약",
                    "category": "계약문서",
                    "full_read_mode": True,
                },
            ),
            _make_plan(action="document_issue_tool", params={"query": "부당특약 검토"}),
        ),
    )
    observed_actions: list[str] = []
    observed_issue_arguments: dict[str, Any] = {}

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_actions.append(plan.action)
        if plan.action == "search_docs_rag":
            return {
                "raw_result": {"snippets": [{"snippet": "스니펫 텍스트"}], "files": []},
                "context_result": {"system_prompt": None},
                "system_prompt": None,
            }
        observed_issue_arguments.update(plan.params)
        return {
            "raw_result": {"issues": []},
            "context_result": {"system_prompt": None},
            "system_prompt": None,
        }

    with caplog.at_level(logging.WARNING):
        asyncio.run(McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn))

    assert observed_actions == ["search_docs_rag", "document_issue_tool"]
    assert observed_issue_arguments["document_text"] == "스니펫 텍스트"
    assert "TOP1 filename not found" in caplog.text


def test_executor_calls_before_and_after_hooks_with_expected_arguments():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="위약금 찾아줘",
        plans=(
            _make_plan(
                action="search_docs_rag",
                params={"query": "위약금", "category": "계약문서"},
            ),
        ),
    )
    before_hook = AsyncMock()
    after_hook = AsyncMock()

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        return {
            "raw_result": {"snippets": []},
            "context_result": {"system_prompt": "prompt"},
            "system_prompt": "prompt",
        }

    asyncio.run(
        McpPlanExecutor().execute(
            decision=decision,
            execute_fn=execute_fn,
            hooks=ExecutorHooks(
                on_before_tool_call=before_hook,
                on_after_tool_call=after_hook,
            ),
        )
    )

    assert before_hook.await_count == 1
    assert after_hook.await_count == 1
    before_call = before_hook.await_args
    after_call = after_hook.await_args
    assert before_call is not None
    assert after_call is not None
    assert before_call.kwargs["plan"].action == "search_docs_rag"
    assert after_call.kwargs["result"]["raw_result"] == {"snippets": []}


def test_executor_calls_on_error_and_reraises_http_exception():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="위약금 찾아줘",
        plans=(
            _make_plan(
                action="search_docs_rag",
                params={"query": "위약금", "category": "계약문서"},
            ),
        ),
    )
    error_hook = AsyncMock()

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        raise HTTPException(status_code=502, detail="upstream failed")

    with pytest.raises(HTTPException, match="upstream failed"):
        asyncio.run(
            McpPlanExecutor().execute(
                decision=decision,
                execute_fn=execute_fn,
                hooks=ExecutorHooks(on_error=error_hook),
            )
        )

    assert error_hook.await_count == 1
    error_call = error_hook.await_args
    assert error_call is not None
    assert error_call.kwargs["plan"].action == "search_docs_rag"
    assert isinstance(error_call.kwargs["error"], HTTPException)
