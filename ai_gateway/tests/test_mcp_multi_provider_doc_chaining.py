import asyncio
from typing import Any

from ai_gateway.services.mcp.mcp_plan_executor import McpPlanExecutor
from ai_gateway.services.mcp.shared_planner.core import SharedPlannerCore
from ai_gateway.services.mcp.shared_planner.models import (
    PlannerDecision,
    PlannerDecisionProvenance,
    PlannerToolPlan,
)


def _make_plan(
    *,
    provider: str,
    action: str,
    params: dict[str, Any] | None = None,
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


def test_executor_reorders_cross_provider_full_read_chain_before_lexguard_analysis():
    planner = SharedPlannerCore(
        activation_rule_refs=["internal_docs.default", "lexguard.default"]
    )
    decision = planner.plan(
        "test문서 폴더에 표준계약서 문서의 부당특약 존재 가능성을 검토해라"
    )

    assert [(plan.provider, plan.action) for plan in decision.plans] == [
        ("lexguard", "document_issue_tool"),
        ("internal_docs", "search_docs_rag"),
    ]
    search_plan = next(
        plan for plan in decision.plans if plan.action == "search_docs_rag"
    )
    assert search_plan.params.get("full_read_mode") is True

    observed_actions: list[tuple[str, str]] = []
    observed_issue_arguments: dict[str, Any] = {}

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_actions.append((plan.provider, plan.action))
        if plan.action == "search_docs_rag":
            return {
                "raw_result": {
                    "files": [{"filename": "표준계약서.md"}],
                    "snippets": [
                        {"filename": "표준계약서.md", "snippet": "계약서 일부"}
                    ],
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
                "context_result": {"system_prompt": None},
                "system_prompt": None,
            }
        raise AssertionError(plan.action)

    result = asyncio.run(
        McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn)
    )

    assert observed_actions == [
        ("internal_docs", "search_docs_rag"),
        ("internal_docs", "read_doc"),
        ("lexguard", "document_issue_tool"),
    ]
    assert observed_issue_arguments["document_text"] == "전체 계약서 전문 내용입니다."
    assert [(plan.provider, plan.action) for plan in result.plans] == observed_actions


def test_executor_skips_read_doc_insertion_when_filename_missing_and_uses_snippet_fallback():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(
            _make_plan(
                provider="internal_docs",
                action="search_docs_rag",
                params={
                    "query": "부당특약",
                    "category": "계약문서",
                    "full_read_mode": True,
                },
            ),
            _make_plan(
                provider="lexguard",
                action="document_issue_tool",
                params={"query": "부당특약 검토"},
            ),
        ),
    )

    observed_actions: list[tuple[str, str]] = []
    observed_issue_arguments: dict[str, Any] = {}

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_actions.append((plan.provider, plan.action))
        if plan.action == "search_docs_rag":
            return {
                "raw_result": {
                    "files": [],
                    "snippets": [{"snippet": "스니펫 기반 문서 내용"}],
                },
                "context_result": {"system_prompt": None},
                "system_prompt": None,
            }
        if plan.action == "document_issue_tool":
            observed_issue_arguments.update(plan.params)
            return {
                "raw_result": {"issues": []},
                "context_result": {"system_prompt": None},
                "system_prompt": None,
            }
        raise AssertionError(plan.action)

    result = asyncio.run(
        McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn)
    )

    assert observed_actions == [
        ("internal_docs", "search_docs_rag"),
        ("lexguard", "document_issue_tool"),
    ]
    assert observed_issue_arguments["document_text"] == "스니펫 기반 문서 내용"
    assert all(plan.action != "read_doc" for plan in result.plans)


def test_executor_calls_lexguard_after_empty_read_doc_result_without_document_text_override():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(
            _make_plan(
                provider="internal_docs",
                action="search_docs_rag",
                params={
                    "query": "부당특약",
                    "category": "계약문서",
                    "full_read_mode": True,
                },
            ),
            _make_plan(
                provider="lexguard",
                action="document_issue_tool",
                params={"query": "부당특약 검토"},
            ),
        ),
    )

    observed_actions: list[tuple[str, str]] = []
    observed_issue_arguments: dict[str, Any] = {}

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_actions.append((plan.provider, plan.action))
        if plan.action == "search_docs_rag":
            return {
                "raw_result": {
                    "files": [{"filename": "표준계약서.md"}],
                    "snippets": [
                        {"filename": "표준계약서.md", "snippet": "검색 스니펫 내용"}
                    ],
                },
                "context_result": {"system_prompt": None},
                "system_prompt": None,
            }
        if plan.action == "read_doc":
            return {
                "raw_result": {"content": "   ", "filename": "표준계약서.md"},
                "context_result": {"system_prompt": None},
                "system_prompt": None,
            }
        if plan.action == "document_issue_tool":
            observed_issue_arguments.update(plan.params)
            return {
                "raw_result": {"issues": []},
                "context_result": {"system_prompt": None},
                "system_prompt": None,
            }
        raise AssertionError(plan.action)

    result = asyncio.run(
        McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn)
    )

    assert observed_actions == [
        ("internal_docs", "search_docs_rag"),
        ("internal_docs", "read_doc"),
        ("lexguard", "document_issue_tool"),
    ]
    assert "document_text" not in observed_issue_arguments
    assert [(plan.provider, plan.action) for plan in result.plans] == observed_actions


def test_executor_skips_read_doc_insertion_when_wrapper_result_is_malformed_no_raw_result():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(
            _make_plan(
                provider="internal_docs",
                action="search_docs_rag",
                params={"query": "부당특약", "full_read_mode": True},
            ),
            _make_plan(
                provider="lexguard",
                action="document_issue_tool",
                params={"query": "부당특약 검토"},
            ),
        ),
    )

    observed_actions: list[tuple[str, str]] = []
    observed_issue_arguments: dict[str, Any] = {}

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_actions.append((plan.provider, plan.action))
        if plan.action == "search_docs_rag":
            return {}  # Malformed: no raw_result
        if plan.action == "document_issue_tool":
            observed_issue_arguments.update(plan.params)
            return {"raw_result": {"issues": []}}
        raise AssertionError(plan.action)

    result = asyncio.run(
        McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn)
    )

    assert observed_actions == [
        ("internal_docs", "search_docs_rag"),
        ("lexguard", "document_issue_tool"),
    ]
    assert "document_text" not in observed_issue_arguments
    assert all(plan.action != "read_doc" for plan in result.plans)


def test_executor_skips_read_doc_insertion_when_wrapper_result_has_none_raw_result():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(
            _make_plan(
                provider="internal_docs",
                action="search_docs_rag",
                params={"query": "부당특약", "full_read_mode": True},
            ),
            _make_plan(
                provider="lexguard",
                action="document_issue_tool",
                params={"query": "부당특약 검토"},
            ),
        ),
    )

    observed_actions: list[tuple[str, str]] = []
    observed_issue_arguments: dict[str, Any] = {}

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_actions.append((plan.provider, plan.action))
        if plan.action == "search_docs_rag":
            return {"raw_result": None}  # Malformed: raw_result is None
        if plan.action == "document_issue_tool":
            observed_issue_arguments.update(plan.params)
            return {"raw_result": {"issues": []}}
        raise AssertionError(plan.action)

    result = asyncio.run(
        McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn)
    )

    assert observed_actions == [
        ("internal_docs", "search_docs_rag"),
        ("lexguard", "document_issue_tool"),
    ]
    assert "document_text" not in observed_issue_arguments
    assert all(plan.action != "read_doc" for plan in result.plans)


def test_executor_skips_read_doc_insertion_when_files_and_snippets_are_empty():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(
            _make_plan(
                provider="internal_docs",
                action="search_docs_rag",
                params={"query": "부당특약", "full_read_mode": True},
            ),
            _make_plan(
                provider="lexguard",
                action="document_issue_tool",
                params={"query": "부당특약 검토"},
            ),
        ),
    )

    observed_actions: list[tuple[str, str]] = []
    observed_issue_arguments: dict[str, Any] = {}

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_actions.append((plan.provider, plan.action))
        if plan.action == "search_docs_rag":
            return {"raw_result": {"files": [], "snippets": []}}
        if plan.action == "document_issue_tool":
            observed_issue_arguments.update(plan.params)
            return {"raw_result": {"issues": []}}
        raise AssertionError(plan.action)

    result = asyncio.run(
        McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn)
    )

    assert observed_actions == [
        ("internal_docs", "search_docs_rag"),
        ("lexguard", "document_issue_tool"),
    ]
    assert "document_text" not in observed_issue_arguments
    assert all(plan.action != "read_doc" for plan in result.plans)


def test_executor_inserts_read_doc_even_if_provider_capability_is_unknown():
    decision = PlannerDecision(
        route="catalog_match",
        clean_query="표준계약서 부당특약 검토",
        plans=(
            _make_plan(
                provider="some_limited_provider",
                action="search_docs_rag",
                params={"query": "부당특약", "full_read_mode": True},
            ),
            _make_plan(
                provider="lexguard",
                action="document_issue_tool",
                params={"query": "부당특약 검토"},
            ),
        ),
    )

    observed_actions: list[tuple[str, str]] = []
    observed_issue_arguments: dict[str, Any] = {}

    async def execute_fn(plan: PlannerToolPlan) -> dict[str, Any]:
        observed_actions.append((plan.provider, plan.action))
        if plan.action == "search_docs_rag":
            return {
                "raw_result": {
                    "files": [{"filename": "표준계약서.md"}],
                    "snippets": [
                        {"filename": "표준계약서.md", "snippet": "계약서 일부"}
                    ],
                }
            }
        if plan.action == "read_doc":
            return {
                "raw_result": {
                    "content": "provider read_doc result",
                    "filename": "표준계약서.md",
                }
            }
        if plan.action == "document_issue_tool":
            observed_issue_arguments.update(plan.params)
            return {"raw_result": {"issues": []}}
        raise AssertionError(plan.action)

    result = asyncio.run(
        McpPlanExecutor().execute(decision=decision, execute_fn=execute_fn)
    )

    assert observed_actions == [
        ("some_limited_provider", "search_docs_rag"),
        ("some_limited_provider", "read_doc"),
        ("lexguard", "document_issue_tool"),
    ]
    assert observed_issue_arguments["document_text"] == "provider read_doc result"
    assert [(plan.provider, plan.action) for plan in result.plans] == observed_actions
