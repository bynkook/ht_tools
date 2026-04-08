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

    with patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search):
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

    with patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search):
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

    with patch.object(GenericMcpHost, "run_rag_search", fake_run_rag_search):
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