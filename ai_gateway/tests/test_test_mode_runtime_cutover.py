"""
Test-mode runtime cutover regressions.
"""

import asyncio
import json
from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import load_mcp_settings
from services.mcp.runtime.base import ChatRuntimeInput, McpContextInput
from services.mcp.runtime.test_mode_runtime import TestModeChatRuntime
from services.mcp.shared_planner.models import (
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
    params: dict | None = None,
):
    resolved_params = params or {"query": "위약금", "category": "test문서"}
    provenance = PlannerDecisionProvenance(
        decision_source="keyword_rule",
        matched_rule=f"{provider}.{action}",
        normalized_query=str(resolved_params.get("query", "")),
        provider_candidates=(f"{provider}.{action}",),
        selected_provider=provider,
        selected_action=action,
        active_category=resolved_params.get("category"),
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
        self.calls = []

    def decide(
        self,
        user_text: str,
        active_category: str | None = None,
        *,
        rag_enabled: bool = False,
        provider_id: str | None = None,
        provider_categories: dict[str, tuple[str, ...]] | None = None,
    ):
        self.calls.append(
            {
                "user_text": user_text,
                "active_category": active_category,
                "rag_enabled": rag_enabled,
                "provider_id": provider_id,
                "provider_categories": provider_categories,
            }
        )
        return self._decision


class FakeHost:
    def __init__(self):
        self.default_provider_id = "internal_docs"
        self.discover_calls = []
        self.execute_calls = []
        self.validated_decisions = []
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
        self.discover_calls.append(provider_id)
        return {"tools": ["search_docs_rag"]}

    async def validate_planner_decision(self, decision):
        self.validated_decisions.append(decision)

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
        self.execute_calls.append(
            {
                "action": "search_docs_rag",
                "arguments": {
                    k: v
                    for k, v in {"query": query, "category": category}.items()
                    if v is not None
                },
                "provider_id": provider_id,
            }
        )
        return {"files": [], "snippets": []}

    def _resolve_doc_search_plan_params(self, plan_params, *, default_query):
        from services.mcp.config import load_mcp_settings
        from services.mcp.doc_search_policy import normalize_doc_search_rag_params

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
        arguments: dict | None = None,
        provider_id: str | None = None,
    ):
        self.execute_calls.append(
            {
                "action": action,
                "arguments": arguments,
                "provider_id": provider_id,
            }
        )
        return {"files": [], "snippets": []}


def test_test_runtime_passes_selected_provider_to_discovery_and_tool_calls():
    plan = _build_plan()
    planner = FakePlanner(
        PlannerDecision(route="catalog_match", clean_query="위약금", plans=(plan,))
    )
    host = FakeHost()
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=host,
        settings=_build_settings().host,
        planner=planner,
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

    assert planner.calls[0]["active_category"] == "test문서"
    assert planner.calls[0]["provider_id"] == "internal_docs"
    assert planner.calls[0]["provider_categories"] == {"internal_docs": ("회의록",)}
    assert host.validated_decisions[0].route == "catalog_match"
    assert host.discover_calls == ["internal_docs"]
    assert host.execute_calls == [
        {
            "action": "search_docs_rag",
            "arguments": {"query": "위약금", "category": "test문서"},
            "provider_id": "internal_docs",
        }
    ]
    tool_decision_event = next(
        payload for payload in payloads if payload.get("phase") == "planning"
    )
    assert tool_decision_event["provider"] == "internal_docs"
    assert tool_decision_event["provider_id"] == "internal_docs"
    assert tool_decision_event["provider_display_name"] == "Internal Docs"
    assert tool_decision_event["selection_reason"] == "keyword rule matched"
    assert tool_decision_event["selection_rank"] == 1
    assert tool_decision_event["candidate_summary"] == ["internal_docs.search_docs_rag"]


def test_test_runtime_discovers_each_provider_once_for_multi_provider_plan():
    plans = (
        _build_plan(
            provider="internal_docs", params={"query": "위약금", "category": "test문서"}
        ),
        _build_plan(
            provider="legal_cases", action="read_doc", params={"filename": "case-1.md"}
        ),
    )
    planner = FakePlanner(
        PlannerDecision(route="scenario", clean_query="위약금", plans=plans)
    )
    host = FakeHost()
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=host,
        settings=_build_settings().host,
        planner=planner,
    )

    payloads = asyncio.run(
        _run_runtime(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=["복합 MCP 실행"],
                is_stream=True,
                mcp_context=McpContextInput(
                    active_category="test문서",
                    rag_enabled=False,
                    provider_id="internal_docs",
                ),
            ),
        )
    )

    assert host.discover_calls == ["internal_docs", "legal_cases"]
    assert host.validated_decisions[0].route == "scenario"
    assert host.execute_calls == [
        {
            "action": "search_docs_rag",
            "arguments": {"query": "위약금", "category": "test문서"},
            "provider_id": "internal_docs",
        },
        {
            "action": "read_doc",
            "arguments": {"filename": "case-1.md"},
            "provider_id": "legal_cases",
        },
    ]
    provider_connect_events = [
        payload
        for payload in payloads
        if payload.get("phase") == "provider_connect"
        and payload.get("title") == "Provider connect start"
    ]
    assert [payload["provider_id"] for payload in provider_connect_events] == [
        "internal_docs",
        "legal_cases",
    ]


def test_test_runtime_uses_selected_provider_when_no_tool_is_planned():
    planner = FakePlanner(
        PlannerDecision(route="chat_only", clean_query="위약금", plans=())
    )
    host = FakeHost()
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=host,
        settings=_build_settings().host,
        planner=planner,
    )

    payloads = asyncio.run(
        _run_runtime(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=["위약금 찾아줘"],
                is_stream=True,
                mcp_context=McpContextInput(
                    active_category=None, rag_enabled=True, provider_id="legal_cases"
                ),
            ),
        )
    )

    assert planner.calls[0]["rag_enabled"] is True
    assert planner.calls[0]["provider_id"] == "legal_cases"
    assert host.validated_decisions[0].route == "chat_only"
    assert host.discover_calls == ["legal_cases"]
    assert host.execute_calls == []
    assistant_final = next(
        payload
        for payload in payloads
        if payload.get("event_type") == "assistant_final"
    )
    assert "선택된 MCP tool이 없습니다" in assistant_final["content"]
