"""
Test-mode runtime executor integration tests.
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast

from fastapi import HTTPException

from ai_gateway.services.mcp.config import load_mcp_settings
from ai_gateway.services.mcp.host import GenericMcpHost
from ai_gateway.services.mcp.runtime.base import ChatRuntimeInput, McpContextInput
from ai_gateway.services.mcp.runtime.test_mode_runtime import TestModeChatRuntime
from ai_gateway.services.mcp.test_mode.planner import DeterministicToolPlanner
from ai_gateway.services.mcp.shared_planner.models import (
    PlannerDecision,
    PlannerDecisionProvenance,
    PlannerToolPlan,
)


def _build_settings():
    return load_mcp_settings(
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    }
                }
            }
        }
    )


async def _collect_payloads(async_iterable):
    payloads = []
    async for chunk in async_iterable:
        chunk = chunk.strip()
        if not chunk.startswith("data: "):
            continue
        payloads.append(json.loads(chunk[6:]))
    return payloads


async def _run_runtime(runtime, runtime_input):
    stream = await runtime.stream_chat(runtime_input)
    return await _collect_payloads(stream)


def _build_plan(
    provider: str = "internal_docs",
    action: str = "search_docs_rag",
    params: dict[str, object] | None = None,
):
    resolved_params = params or {"query": "위약금", "category": "test문서"}
    provenance = PlannerDecisionProvenance(
        decision_source="keyword_rule",
        matched_rule=f"{provider}.{action}",
        normalized_query=str(resolved_params.get("query", "")),
        provider_candidates=(f"{provider}.{action}",),
        selected_provider=provider,
        selected_action=action,
        active_category=cast(str | None, resolved_params.get("category")),
        reason="keyword rule matched",
    )
    return PlannerToolPlan(
        provider=provider,
        action=action,
        params=resolved_params,
        provenance=provenance,
    )


class FakePlanner:
    def __init__(self, decision: PlannerDecision):
        self._decision = decision

    def decide(self, *args, **kwargs):
        return self._decision


class FakeHost:
    def __init__(self, execute_result=None, execute_error=None):
        self.default_provider_id = "internal_docs"
        self.execute_result = execute_result or {"files": [], "snippets": []}
        self.execute_error = execute_error
        display_names = {
            "internal_docs": "Internal Docs",
            "legal_cases": "Legal Cases",
        }
        self.settings = SimpleNamespace(
            require_provider=lambda provider_id: SimpleNamespace(
                display_name=display_names.get(provider_id, provider_id),
                activation_rule_ref="internal_docs.default",
            )
        )

    async def discover_provider_capabilities(self, *, provider_id: str | None = None):
        return {"tools": ["search_docs_rag", "read_doc", "document_issue_tool"]}

    async def validate_planner_decision(self, decision):
        pass

    async def build_planner_provider_categories(self):
        return {"internal_docs": ("회의록",)}

    async def run_rag_search(
        self,
        *,
        query,
        category=None,
        filename_filter=None,
        max_docs=None,
        snippet_chars=None,
        provider_id=None,
    ):
        if self.execute_error:
            raise self.execute_error
        if callable(self.execute_result):
            return self.execute_result(
                "search_docs_rag", {"query": query, "category": category}, provider_id
            )
        return self.execute_result

    def _resolve_doc_search_plan_params(self, plan_params, *, default_query):
        from ai_gateway.services.mcp.config import load_mcp_settings
        from ai_gateway.services.mcp.doc_search_policy import (
            normalize_doc_search_rag_params,
        )

        settings = load_mcp_settings(
            {
                "mcp": {
                    "providers": {
                        "internal_docs": {
                            "base_url": "http://127.0.0.1:8002/mcp",
                            "transport": "streamable_http",
                        }
                    }
                }
            }
        )
        return normalize_doc_search_rag_params(
            plan_params,
            query=str(plan_params.get("query", default_query)),
            settings=settings.host.doc_search,
        )

    async def execute_tool_action(
        self,
        *,
        action: str,
        arguments: dict[str, object] | None = None,
        provider_id: str | None = None,
    ):
        if self.execute_error:
            raise self.execute_error
        if callable(self.execute_result):
            return self.execute_result(action, arguments, provider_id)
        return self.execute_result


def test_happy_path_single_plan_lifecycle_events():
    plan = _build_plan()
    planner = FakePlanner(
        PlannerDecision(route="catalog_match", clean_query="위약금", plans=(plan,))
    )
    host = FakeHost()
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, cast(object, host)),
        settings=_build_settings().host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    payloads = asyncio.run(
        _run_runtime(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=["위약금 찾아줘"],
                is_stream=True,
                mcp_context=McpContextInput(
                    active_category="test문서",
                    rag_enabled=False,
                    provider_id="internal_docs",
                ),
            ),
        )
    )

    event_types = [p.get("event_type") for p in payloads]
    phases = [p.get("phase") for p in payloads if "phase" in p]

    # Check that the expected events are present in the correct order
    assert "tool_call" in phases  # before_tool_call and after_tool_call
    assert "context_merge" in phases
    assert "assistant_final" in event_types
    assert "stream_end" in event_types

    # Verify specific events
    before_tool_calls = [
        p
        for p in payloads
        if p.get("phase") == "tool_call" and p.get("title") == "Before tool call"
    ]
    after_tool_calls = [
        p
        for p in payloads
        if p.get("phase") == "tool_call" and p.get("title") == "After tool call"
    ]
    context_aggregated = [
        p
        for p in payloads
        if p.get("phase") == "context_merge" and p.get("title") == "Context aggregated"
    ]
    assistant_final = [p for p in payloads if p.get("event_type") == "assistant_final"]
    stream_end = [p for p in payloads if p.get("event_type") == "stream_end"]

    assert len(before_tool_calls) == 1
    assert len(after_tool_calls) == 1
    assert len(context_aggregated) == 1
    assert len(assistant_final) == 1
    assert len(stream_end) == 1

    assert stream_end[0]["finish_reason"] == "test_mode_complete"


def test_happy_path_full_read_mode_inserts_read_doc():
    plans = (
        _build_plan(
            provider="internal_docs",
            action="search_docs_rag",
            params={"query": "위약금", "category": "test문서", "full_read_mode": True},
        ),
        _build_plan(
            provider="internal_docs",
            action="document_issue_tool",
            params={"issue": "위약금"},
        ),
    )
    planner = FakePlanner(
        PlannerDecision(route="catalog_match", clean_query="위약금", plans=plans)
    )

    def mock_execute(action, arguments, provider_id):
        if action == "search_docs_rag":
            return {
                "files": [{"filename": "test-doc.md", "snippet": "위약금 조항"}],
                "snippets": [],
            }
        return {"result": "ok"}

    host = FakeHost(execute_result=mock_execute)
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, cast(object, host)),
        settings=_build_settings().host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    payloads = asyncio.run(
        _run_runtime(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=["위약금 찾아줘"],
                is_stream=True,
                mcp_context=McpContextInput(
                    active_category="test문서",
                    rag_enabled=False,
                    provider_id="internal_docs",
                ),
            ),
        )
    )

    # Verify plan_inserted event
    plan_inserted_events = [
        p
        for p in payloads
        if p.get("phase") == "planning" and p.get("title") == "Plan inserted"
    ]
    assert len(plan_inserted_events) == 1
    assert "read_doc" in plan_inserted_events[0]["content"]
    assert plan_inserted_events[0]["tool"] == "read_doc"

    # Verify before_tool_call events for all 3 tools
    before_tool_calls = [
        p
        for p in payloads
        if p.get("phase") == "tool_call" and p.get("title") == "Before tool call"
    ]
    assert len(before_tool_calls) == 3
    tools_called = [p["tool"] for p in before_tool_calls]
    assert tools_called == ["search_docs_rag", "read_doc", "document_issue_tool"]


def test_error_path_emits_error_event_and_stream_end():
    plan = _build_plan()
    planner = FakePlanner(
        PlannerDecision(route="catalog_match", clean_query="위약금", plans=(plan,))
    )
    host = FakeHost(
        execute_error=HTTPException(status_code=500, detail="Internal Server Error")
    )
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, cast(object, host)),
        settings=_build_settings().host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    payloads = asyncio.run(
        _run_runtime(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=["위약금 찾아줘"],
                is_stream=True,
                mcp_context=McpContextInput(
                    active_category="test문서",
                    rag_enabled=False,
                    provider_id="internal_docs",
                ),
            ),
        )
    )

    # Verify error event
    error_events = [
        p
        for p in payloads
        if p.get("phase") == "runtime" and p.get("title") == "Runtime error"
    ]
    assert len(error_events) == 1
    assert error_events[0]["content"] == "Internal Server Error"
    assert error_events[0]["raw"]["status_code"] == 500

    # Verify stream_end
    stream_end = [p for p in payloads if p.get("event_type") == "stream_end"]
    assert len(stream_end) == 1
    assert stream_end[0]["finish_reason"] == "error"


def test_empty_plans_path_emits_assistant_final_and_stream_end():
    planner = FakePlanner(
        PlannerDecision(route="chat_only", clean_query="위약금", plans=())
    )
    host = FakeHost()
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, cast(object, host)),
        settings=_build_settings().host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    payloads = asyncio.run(
        _run_runtime(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=["위약금 찾아줘"],
                is_stream=True,
                mcp_context=McpContextInput(
                    active_category="test문서",
                    rag_enabled=False,
                    provider_id="internal_docs",
                ),
            ),
        )
    )

    # Verify no tool events
    tool_calls = [p for p in payloads if p.get("phase") == "tool_call"]
    assert len(tool_calls) == 0

    # Verify assistant_final and stream_end
    assistant_final = [p for p in payloads if p.get("event_type") == "assistant_final"]
    stream_end = [p for p in payloads if p.get("event_type") == "stream_end"]

    assert len(assistant_final) == 1
    assert len(stream_end) == 1
    assert stream_end[0]["finish_reason"] == "test_mode_complete"


def test_execute_plan_search_docs_rag_calls_run_rag_search():
    """Verify search_docs_rag in test mode uses run_rag_search for consistent raw_result."""
    plan = _build_plan(
        provider="internal_docs",
        action="search_docs_rag",
        params={"query": "위약금", "category": "test문서"},
    )
    planner = FakePlanner(
        PlannerDecision(route="catalog_match", clean_query="위약금", plans=(plan,))
    )

    run_rag_search_called = False
    run_rag_search_args: dict[str, Any] = {}

    class MockHost(FakeHost):
        async def run_rag_search(
            self,
            *,
            query,
            category=None,
            filename_filter=None,
            max_docs=None,
            snippet_chars=None,
            provider_id=None,
        ):
            nonlocal run_rag_search_called, run_rag_search_args
            run_rag_search_called = True
            run_rag_search_args = {
                "query": query,
                "category": category,
                "provider_id": provider_id,
            }
            return {
                "files": [{"filename": "test.md", "snippet": "content"}],
                "snippets": [{"filename": "test.md", "snippet": "위약금 조항"}],
                "system_prompt": "test prompt",
            }

    host = MockHost()
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, cast(object, host)),
        settings=_build_settings().host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    payloads = asyncio.run(
        _run_runtime(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=["위약금 찾아줘"],
                is_stream=True,
                mcp_context=McpContextInput(
                    active_category="test문서",
                    rag_enabled=False,
                    provider_id="internal_docs",
                ),
            ),
        )
    )

    # Verify run_rag_search was called
    assert run_rag_search_called, "run_rag_search should be called for search_docs_rag"
    assert run_rag_search_args["query"] == "위약금"
    assert run_rag_search_args["category"] == "test문서"

    # Verify stream completed successfully
    stream_end = [p for p in payloads if p.get("event_type") == "stream_end"]
    assert len(stream_end) == 1
    assert stream_end[0]["finish_reason"] == "test_mode_complete"
