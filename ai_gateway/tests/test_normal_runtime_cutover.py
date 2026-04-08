import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import load_mcp_settings
from services.mcp.host import GenericMcpHost
from services.mcp.runtime.base import ChatRuntimeInput, McpContextInput
from services.mcp.runtime.normal_runtime import NormalChatRuntime
from services.mcp.shared_planner.models import PlannerDecision, PlannerDecisionProvenance, PlannerToolPlan


def _build_host() -> GenericMcpHost:
    settings = load_mcp_settings(
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    },
                    "legal_cases": {
                        "base_url": "http://127.0.0.1:8003/mcp",
                        "transport": "streamable_http",
                        "activation_rule_ref": "internal_docs.default",
                    },
                }
            }
        }
    )
    return GenericMcpHost(settings)


def test_host_uses_shared_planner_catalog_for_doc_search_prompt_without_rag_toggle():
    host = _build_host()
    observed = {}

    async def fake_run_rag_search(self, **kwargs):
        observed.update(kwargs)
        return {"system_prompt": "=== 참고 문서 ===\n\n위약금 조항"}

    async def fake_validate_planner_decision(self, decision):
        return None

    with (
        patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search),
        patch.object(GenericMcpHost, "validate_planner_decision", fake_validate_planner_decision),
    ):
        resolution = asyncio.run(
            host.build_chat_resolution(
                user_text="표준계약서에서 위약금 관련 내용을 검색",
                active_category="test문서",
                rag_enabled=False,
            )
        )

    assert resolution.route == "catalog_match"
    assert resolution.decision is not None
    assert resolution.decision.route == "catalog_match"
    assert resolution.decision.plans[0].provider == "internal_docs"
    assert observed["query"] == "표준계약서에서 위약금 관련 내용을 검색"
    assert observed["category"] == "test문서"
    assert observed["provider_id"] == "internal_docs"
    assert "위약금 조항" in (resolution.system_prompt or "")


def test_host_uses_selected_provider_for_rag_fallback_resolution():
    host = _build_host()
    observed = {}

    async def fake_run_rag_search(self, **kwargs):
        observed.update(kwargs)
        return {"system_prompt": "=== 참고 문서 ===\n\n법률 문서"}

    async def fake_validate_planner_decision(self, decision):
        return None

    with (
        patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search),
        patch.object(GenericMcpHost, "validate_planner_decision", fake_validate_planner_decision),
    ):
        resolution = asyncio.run(
            host.build_chat_resolution(
                user_text="오늘 일정 알려줘",
                active_category="판례",
                rag_enabled=True,
                provider_id="legal_cases",
            )
        )

    assert resolution.route == "rag_search"
    assert resolution.decision is not None
    assert resolution.decision.plans[0].provider == "legal_cases"
    assert observed["provider_id"] == "legal_cases"
    assert observed["category"] == "판례"


def test_host_keeps_general_chat_as_no_tool_when_planner_returns_chat_only():
    host = _build_host()

    async def fail_run_rag_search(self, **kwargs):
        raise AssertionError("run_rag_search should not be called for general chat")

    with patch.object(GenericMcpHost, "run_rag_search", fail_run_rag_search):
        resolution = asyncio.run(
            host.build_chat_resolution(
                user_text="오늘 날씨 어때?",
                rag_enabled=False,
            )
        )

    assert resolution.route == "chat_only"
    assert resolution.decision is not None
    assert resolution.decision.route == "chat_only"
    assert resolution.system_prompt is None
    assert resolution.missing_mentions == []


def test_host_retries_chat_only_with_dynamic_provider_categories():
    host = _build_host()
    observed = {"calls": 0}

    def fake_plan(self, user_text, *, active_category=None, rag_enabled=False, provider_hint=None, provider_categories=None):
        observed["calls"] += 1
        if provider_categories is None:
            return PlannerDecision(route="chat_only", clean_query=user_text, plans=())
        return PlannerDecision(
            route="catalog_match",
            clean_query=user_text,
            plans=(
                PlannerToolPlan(
                    provider="internal_docs",
                    action="search_docs_rag",
                    params={"query": user_text, "category": "회의록"},
                    provenance=PlannerDecisionProvenance(
                        decision_source="keyword_rule",
                        matched_rule="dynamic-category",
                        normalized_query=user_text,
                        provider_candidates=("internal_docs.search_docs_rag",),
                        selected_provider="internal_docs",
                        selected_action="search_docs_rag",
                        active_category="회의록",
                    ),
                ),
            ),
        )

    async def fake_build_planner_provider_categories(self):
        return {"internal_docs": ("회의록",)}

    async def fake_validate_planner_decision(self, decision):
        return None

    async def fake_run_rag_search(self, **kwargs):
        observed["kwargs"] = kwargs
        return {"system_prompt": "=== 참고 문서 ===\n\n회의록 요약"}

    with (
        patch.object(type(host._planner), "plan", fake_plan),
        patch.object(GenericMcpHost, "build_planner_provider_categories", fake_build_planner_provider_categories),
        patch.object(GenericMcpHost, "validate_planner_decision", fake_validate_planner_decision),
        patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search),
    ):
        resolution = asyncio.run(
            host.build_chat_resolution(
                user_text="회의록 폴더에서 가장 최근 회의록을 검색해서 주요 내용을 요약해줘",
                rag_enabled=False,
            )
        )

    assert observed["calls"] == 2
    assert observed["kwargs"]["category"] == "회의록"
    assert resolution.route == "catalog_match"


def test_normal_runtime_merges_shared_planner_system_prompt_before_upstream_call():
    host = _build_host()
    captured = {}

    async def fake_run_rag_search(self, **kwargs):
        return {"system_prompt": "=== 참고 문서 ===\n\n위약금 조항"}

    class FakeUpstreamClient:
        async def stream_chat(self, **kwargs):
            captured.update(kwargs)

            async def _events():
                if False:
                    yield ""

            return _events()

    runtime = NormalChatRuntime(
        request=SimpleNamespace(),
        mcp_host=host,
        upstream_client=FakeUpstreamClient(),
    )
    runtime_input = ChatRuntimeInput(
        model_ids=["gpt-test"],
        contents=["표준계약서에서 위약금 관련 내용을 검색"],
        is_stream=True,
        system_prompt="BASE SYSTEM PROMPT",
        mcp_context=McpContextInput(active_category="test문서", rag_enabled=False),
    )

    async def fake_validate_planner_decision(self, decision):
        return None

    with (
        patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search),
        patch.object(GenericMcpHost, "validate_planner_decision", fake_validate_planner_decision),
    ):
        asyncio.run(runtime.stream_chat(runtime_input))

    assert captured["model_ids"] == ["gpt-test"]
    assert captured["contents"] == ["표준계약서에서 위약금 관련 내용을 검색"]
    assert "BASE SYSTEM PROMPT" in (captured["system_prompt"] or "")
    assert "위약금 조항" in (captured["system_prompt"] or "")


def test_normal_runtime_forwards_selected_provider_into_chat_resolution():
    host = _build_host()
    observed = {}

    async def fake_build_chat_resolution(self, **kwargs):
        observed.update(kwargs)
        return SimpleNamespace(system_prompt=None)

    class FakeUpstreamClient:
        async def stream_chat(self, **kwargs):
            async def _events():
                if False:
                    yield ""

            return _events()

    runtime = NormalChatRuntime(
        request=SimpleNamespace(),
        mcp_host=host,
        upstream_client=FakeUpstreamClient(),
    )
    runtime_input = ChatRuntimeInput(
        model_ids=["gpt-test"],
        contents=["판례를 찾아줘"],
        is_stream=True,
        mcp_context=McpContextInput(active_category="판례", rag_enabled=True, provider_id="legal_cases"),
    )

    with patch.object(GenericMcpHost, "build_chat_resolution", fake_build_chat_resolution):
        asyncio.run(runtime.stream_chat(runtime_input))

    assert observed["provider_id"] == "legal_cases"
    assert observed["active_category"] == "판례"
    assert observed["rag_enabled"] is True


def test_host_merges_multi_provider_context_when_planner_returns_multiple_plans():
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
    plans = (
        PlannerToolPlan(
            provider="internal_docs",
            action="search_docs_rag",
            params={"query": "위약금", "category": "계약문서"},
            provenance=PlannerDecisionProvenance(
                decision_source="keyword_rule",
                matched_rule="docs-search",
                normalized_query="위약금",
                provider_candidates=("internal_docs.search_docs_rag", "legal_cases.search_docs_rag"),
                selected_provider="internal_docs",
                selected_action="search_docs_rag",
            ),
        ),
        PlannerToolPlan(
            provider="legal_cases",
            action="search_docs_rag",
            params={"query": "위약금"},
            provenance=PlannerDecisionProvenance(
                decision_source="keyword_rule",
                matched_rule="legal-search",
                normalized_query="위약금",
                provider_candidates=("internal_docs.search_docs_rag", "legal_cases.search_docs_rag"),
                selected_provider="legal_cases",
                selected_action="search_docs_rag",
            ),
        ),
    )
    host = GenericMcpHost(
        settings,
        planner=SimpleNamespace(
            plan=lambda *args, **kwargs: PlannerDecision(route="catalog_match", clean_query="위약금", plans=plans)
        ),
    )
    observed_calls = []

    async def fake_validate_planner_decision(self, decision):
        return None

    async def fake_run_rag_search(self, **kwargs):
        observed_calls.append(kwargs)
        provider_id = kwargs["provider_id"]
        return {"system_prompt": f"=== 참고 문서 ===\n\n{provider_id} context"}

    with (
        patch.object(GenericMcpHost, "validate_planner_decision", fake_validate_planner_decision),
        patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search),
    ):
        resolution = asyncio.run(
            host.build_chat_resolution(
                user_text="위약금 관련 내용을 검색",
                active_category="계약문서",
                rag_enabled=False,
            )
        )

    assert observed_calls == [
        {
            "query": "위약금",
            "category": "계약문서",
            "filename_filter": None,
            "max_docs": 10,
            "snippet_chars": 1500,
            "provider_id": "internal_docs",
        },
        {
            "query": "위약금",
            "category": None,
            "filename_filter": None,
            "max_docs": 10,
            "snippet_chars": 1500,
            "provider_id": "legal_cases",
        },
    ]
    assert "internal_docs context" in (resolution.system_prompt or "")
    assert "legal_cases context" in (resolution.system_prompt or "")
