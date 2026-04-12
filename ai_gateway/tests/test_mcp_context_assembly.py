"""Regression fixtures for the MCP context assembly contract.

Current legal-tool contract:

- `ai_gateway/services/mcp/host.py::normalize_context_result()` preserves lexguard
  `structured_result` and defers `system_prompt` rendering.
- `ai_gateway/services/mcp/host.py::build_context_debug_payload()` reflects the deferred
  shape as-is for test/debug payloads.
- `ai_gateway/services/mcp/runtime/normal_runtime.py::NormalChatRuntime.stream_chat()`
  lazily renders deferred legal fragments at the final upstream LLM boundary.

Related regression coverage:

- `ai_gateway/tests/test_test_mode_runtime.py`
- `ai_gateway/tests/test_test_mode_runtime_executor.py`
- `ai_gateway/tests/test_mcp_plan_executor.py`
"""

import asyncio
from collections.abc import AsyncIterator
import json
from types import SimpleNamespace
from typing import Any, cast

from ai_gateway.services.mcp.config import McpSettings, load_mcp_settings
from ai_gateway.services.mcp.host import (
    GenericMcpHost,
    normalize_context_result,
    render_context_result_system_prompt,
)
from ai_gateway.services.mcp.runtime.base import ChatRuntimeInput, McpContextInput
from ai_gateway.services.mcp.runtime.normal_runtime import NormalChatRuntime
from ai_gateway.services.mcp.runtime.test_mode_runtime import TestModeChatRuntime
from ai_gateway.services.mcp.runtime.upstream import FabrixUpstreamClient
from ai_gateway.services.mcp.shared_planner.core import SharedPlannerCore
from ai_gateway.services.mcp.shared_planner.models import (
    PlannerDecision,
    PlannerDecisionProvenance,
    PlannerToolPlan,
)
from ai_gateway.services.mcp.test_mode.planner import DeterministicToolPlanner


LEGAL_QUERY = '해고 통지서에 "정당한 이유"가 없고 파일 경로가 C:\\temp\\판례.txt 라면 어떻게 되나요?'
BASE_SYSTEM_PROMPT = "BASE SYSTEM PROMPT"
LEGAL_RAW_RESULT = {
    "success": True,
    "query": LEGAL_QUERY,
    "answer": '근로기준법상 해고는 "정당한 이유"가 필요합니다.\n해고 사유는 서면으로 통지되어야 합니다.',
    "results": [
        {
            "source": "판례",
            "case_number": "2024두12345",
            "summary": '사용자 파일 경로 C:\\temp\\판례.txt 와 "징계사유" 문구를 함께 검토해야 합니다.',
        }
    ],
    "metadata": {
        "note": '원문 인용: "정당한 이유"',
        "path": "C:\\temp\\판례.txt",
    },
}
EXPECTED_LEGAL_RAW_JSON = json.dumps(LEGAL_RAW_RESULT, ensure_ascii=False)
EXPECTED_NORMAL_MODE_LEGAL_PROMPT = (
    "당신은 법률 전문가 어시스턴트입니다.\n"
    "아래 법률 검색 결과(JSON)를 바탕으로 사용자의 질문에 정확하게 답하세요.\n"
    "검색 결과에 없는 내용은 '제공된 정보에서 찾을 수 없습니다'라고 솔직하게 답하세요.\n\n"
    f"=== 법률 검색 결과 ===\n\n{EXPECTED_LEGAL_RAW_JSON}\n\n===================="
)
EXPECTED_TEST_MODE_LEGAL_PROMPT = f"=== [TEST] 법률 검색 결과 ===\n\n{EXPECTED_LEGAL_RAW_JSON}\n\n===================="
EXPECTED_NORMAL_MODE_UPSTREAM_PROMPT = (
    f"{BASE_SYSTEM_PROMPT}\n\n---\n\n{EXPECTED_NORMAL_MODE_LEGAL_PROMPT}"
)
EXPECTED_TEST_MODE_CONTEXT_AGGREGATED_RAW: dict[str, object] = {
    "fragment_count": 1,
    "fragments": [
        {
            "type": "tool_result",
            "action": "legal_qa_tool",
            "query": LEGAL_QUERY,
            "category": None,
            "files": [],
            "snippets": [],
            "system_prompt": None,
            "structured_result": LEGAL_RAW_RESULT,
        }
    ],
    "base_system_prompt": BASE_SYSTEM_PROMPT,
    "final_system_prompt": BASE_SYSTEM_PROMPT,
}

LEGAL_TRANSPORT_ERROR_RESULT = {
    "success": False,
    "error_code": "API_ERROR_TIMEOUT",
    "error": "upstream timeout",
}

LEGAL_TOOL_ERROR_RESULT = {
    "success": False,
    "error": "unknown committee_type",
}

LEGAL_BACKSLASH_RESULT = {
    "success": True,
    "query": LEGAL_QUERY,
    "answer": '경로 C:\\tmp\\case.txt 와 "징계사유" 및 다음 줄\n개행을 확인하세요.',
    "results": [
        {
            "source": "판례",
            "case_number": "2024두54321",
            "summary": '문서 경로 C:\\tmp\\case.txt 와 "징계사유" 문구를 함께 검토합니다.\n추가 줄입니다.',
        }
    ],
    "metadata": {
        "note": '인용: "징계사유"',
        "path": "C:\\tmp\\case.txt",
        "details": "첫째 줄\n둘째 줄",
    },
}


def _build_settings() -> McpSettings:
    return load_mcp_settings(
        {
            "mcp": {
                "host": {
                    "test_mode_verbose_json": True,
                    "test_mode_max_payload_chars": 100_000,
                    "test_mode_raw_bytes_limit": 100_000,
                },
                "providers": {
                    "lexguard": {
                        "display_name": "Lexguard",
                        "base_url": "http://127.0.0.1:9099/mcp",
                        "transport": "streamable_http",
                    },
                    "internal_docs": {
                        "display_name": "Internal Docs",
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    },
                },
            }
        }
    )


def _build_legal_plan() -> PlannerToolPlan:
    return PlannerToolPlan(
        provider="lexguard",
        action="legal_qa_tool",
        params={"query": LEGAL_QUERY},
        provenance=PlannerDecisionProvenance(
            decision_source="keyword_rule",
            matched_rule="lexguard.legal_qa_tool",
            normalized_query=LEGAL_QUERY,
            provider_candidates=("lexguard.legal_qa_tool",),
            selected_provider="lexguard",
            selected_action="legal_qa_tool",
            reason="keyword rule matched",
        ),
    )


class _StaticPlanner:
    def __init__(self, decision: PlannerDecision) -> None:
        self._decision = decision

    def plan(self, *_args: object, **_kwargs: object) -> PlannerDecision:
        return self._decision

    def decide(self, *_args: object, **_kwargs: object) -> PlannerDecision:
        return self._decision


class _LexguardFixtureHost(GenericMcpHost):
    async def validate_planner_decision(self, decision: PlannerDecision) -> None:
        return None

    async def execute_tool_action(
        self,
        *,
        action: str,
        arguments: dict[str, Any] | None = None,
        provider_id: str | None = None,
    ) -> Any:
        assert action == "legal_qa_tool"
        assert provider_id == "lexguard"
        assert arguments == {"query": LEGAL_QUERY}
        return LEGAL_RAW_RESULT

    async def discover_provider_capabilities(
        self, *, provider_id: str | None = None
    ) -> dict[str, list[str]]:
        assert provider_id == "lexguard"
        return {
            "tools": ["legal_qa_tool"],
            "resources": [],
            "prompts": [],
        }

    async def build_planner_provider_categories(self) -> dict[str, tuple[str, ...]]:
        return {}


class _RecordingUpstreamClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def stream_chat(
        self,
        *,
        model_ids: list[str],
        contents: list[str],
        is_stream: bool,
        system_prompt: str | None,
        llm_config: dict[str, Any] | None,
    ) -> AsyncIterator[str]:
        self.calls.append(
            {
                "model_ids": model_ids,
                "contents": contents,
                "is_stream": is_stream,
                "system_prompt": system_prompt,
                "llm_config": llm_config,
            }
        )

        async def _stream():
            yield 'data: {"event_type": "assistant_chunk", "content": "ok"}\n\n'

        return _stream()


async def _drain_stream(async_iterable: AsyncIterator[str]) -> list[str]:
    chunks: list[str] = []
    async for chunk in async_iterable:
        chunks.append(chunk)
    return chunks


async def _collect_payloads(async_iterable: AsyncIterator[str]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    async for chunk in async_iterable:
        chunk = chunk.strip()
        if not chunk.startswith("data: "):
            continue
        payload = json.loads(chunk[6:])
        assert isinstance(payload, dict)
        payloads.append(payload)
    return payloads


async def _collect_normal_runtime_chunks(
    runtime: NormalChatRuntime, runtime_input: ChatRuntimeInput
) -> list[str]:
    stream = await runtime.stream_chat(runtime_input)
    return await _drain_stream(stream)


async def _collect_test_mode_payloads(
    runtime: TestModeChatRuntime, runtime_input: ChatRuntimeInput
) -> list[dict[str, Any]]:
    stream = await runtime.stream_chat(runtime_input)
    return await _collect_payloads(stream)


def test_capture_normal_mode_legal_prompt_golden():
    settings = _build_settings()
    decision = PlannerDecision(
        route="catalog_match",
        clean_query=LEGAL_QUERY,
        plans=(_build_legal_plan(),),
    )
    planner = cast(SharedPlannerCore, cast(object, _StaticPlanner(decision)))
    host = _LexguardFixtureHost(settings, planner=planner)
    upstream = _RecordingUpstreamClient()
    runtime = NormalChatRuntime(
        request=SimpleNamespace(),
        mcp_host=host,
        upstream_client=cast(FabrixUpstreamClient, cast(object, upstream)),
    )

    chunks = asyncio.run(
        _collect_normal_runtime_chunks(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=[LEGAL_QUERY],
                is_stream=True,
                system_prompt=BASE_SYSTEM_PROMPT,
                mcp_context=McpContextInput(
                    active_category=None,
                    rag_enabled=False,
                    provider_id="lexguard",
                ),
            ),
        )
    )

    assert chunks
    assert len(upstream.calls) == 1
    assert upstream.calls[0]["system_prompt"] == EXPECTED_NORMAL_MODE_UPSTREAM_PROMPT


def test_capture_test_mode_context_aggregated_fixture():
    settings = _build_settings()
    decision = PlannerDecision(
        route="catalog_match",
        clean_query=LEGAL_QUERY,
        plans=(_build_legal_plan(),),
    )
    planner = _StaticPlanner(decision)
    host = _LexguardFixtureHost(
        settings,
        planner=cast(SharedPlannerCore, cast(object, planner)),
    )
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, host),
        settings=settings.host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    payloads = asyncio.run(
        _collect_test_mode_payloads(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=[LEGAL_QUERY],
                is_stream=True,
                system_prompt=BASE_SYSTEM_PROMPT,
                mcp_context=McpContextInput(
                    active_category=None,
                    rag_enabled=False,
                    provider_id="lexguard",
                ),
            ),
        )
    )

    context_aggregated = [
        payload
        for payload in payloads
        if payload.get("phase") == "context_merge"
        and payload.get("title") == "Context aggregated"
    ]

    assert len(context_aggregated) == 1
    assert context_aggregated[0]["raw"] == EXPECTED_TEST_MODE_CONTEXT_AGGREGATED_RAW
    assert context_aggregated[0]["raw"]["fragments"][0]["system_prompt"] is None


def test_normalize_context_result_preserves_structured_legal_result():
    context_result = normalize_context_result(
        action="legal_qa_tool",
        arguments={"query": LEGAL_QUERY},
        raw_result=LEGAL_RAW_RESULT,
        test_mode=False,
    )
    assert context_result["structured_result"] == LEGAL_RAW_RESULT
    assert context_result["system_prompt"] is None


def test_structured_fragment_retains_chaining_fields():
    context_result = normalize_context_result(
        action="legal_qa_tool",
        arguments={"query": LEGAL_QUERY, "category": "test_cat"},
        raw_result=LEGAL_RAW_RESULT,
        test_mode=False,
    )
    assert context_result["action"] == "legal_qa_tool"
    assert context_result["query"] == LEGAL_QUERY
    assert context_result["category"] == "test_cat"
    assert context_result["system_prompt"] is None
    assert "files" not in context_result
    assert "snippets" not in context_result
    assert context_result["structured_result"] == LEGAL_RAW_RESULT


def test_mixed_structured_and_none_structured_result():
    read_doc_result = normalize_context_result(
        action="read_doc",
        arguments={"query": LEGAL_QUERY, "filename": "case.txt"},
        raw_result={
            "success": True,
            "query": LEGAL_QUERY,
            "filename": "case.txt",
            "content": "문서 본문",
        },
        test_mode=False,
    )
    legal_result = normalize_context_result(
        action="legal_qa_tool",
        arguments={"query": LEGAL_QUERY, "category": "law"},
        raw_result=LEGAL_RAW_RESULT,
        test_mode=False,
    )

    assert read_doc_result["structured_result"] == {
        "success": True,
        "query": LEGAL_QUERY,
        "filename": "case.txt",
        "content": "문서 본문",
    }
    assert read_doc_result["system_prompt"] is None
    assert read_doc_result["action"] == "read_doc"
    assert read_doc_result["query"] == LEGAL_QUERY
    assert read_doc_result["filename"] == "case.txt"

    assert legal_result["structured_result"] == LEGAL_RAW_RESULT
    assert legal_result["system_prompt"] is None
    assert legal_result["action"] == "legal_qa_tool"
    assert legal_result["query"] == LEGAL_QUERY
    assert legal_result["category"] == "law"


def test_legal_error_result_structured_result_preserved():
    context_result = normalize_context_result(
        action="legal_qa_tool",
        arguments={"query": LEGAL_QUERY},
        raw_result=LEGAL_TRANSPORT_ERROR_RESULT,
        test_mode=False,
    )

    assert context_result["structured_result"] == LEGAL_TRANSPORT_ERROR_RESULT
    assert context_result["system_prompt"] is None
    assert context_result["action"] == "legal_qa_tool"
    assert context_result["query"] == LEGAL_QUERY


def test_full_suite_backslash_regression():
    settings = _build_settings()
    decision = PlannerDecision(
        route="catalog_match",
        clean_query=LEGAL_QUERY,
        plans=(_build_legal_plan(),),
    )
    planner = _StaticPlanner(decision)

    class _BackslashFixtureHost(_LexguardFixtureHost):
        async def execute_tool_action(
            self,
            *,
            action: str,
            arguments: dict[str, Any] | None = None,
            provider_id: str | None = None,
        ) -> Any:
            assert action == "legal_qa_tool"
            assert provider_id == "lexguard"
            assert arguments == {"query": LEGAL_QUERY}
            return LEGAL_BACKSLASH_RESULT

    host = _BackslashFixtureHost(
        settings,
        planner=cast(SharedPlannerCore, cast(object, planner)),
    )

    normal_upstream = _RecordingUpstreamClient()
    normal_runtime = NormalChatRuntime(
        request=SimpleNamespace(),
        mcp_host=host,
        upstream_client=cast(FabrixUpstreamClient, cast(object, normal_upstream)),
    )
    asyncio.run(
        _collect_normal_runtime_chunks(
            normal_runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=[LEGAL_QUERY],
                is_stream=True,
                system_prompt=BASE_SYSTEM_PROMPT,
                mcp_context=McpContextInput(
                    active_category=None,
                    rag_enabled=False,
                    provider_id="lexguard",
                ),
            ),
        )
    )

    expected_backslash_json = json.dumps(LEGAL_BACKSLASH_RESULT, ensure_ascii=False)
    double_escaped_backslash_json = expected_backslash_json.replace("\\", "\\\\")
    assert len(normal_upstream.calls) == 1
    assert expected_backslash_json in normal_upstream.calls[0]["system_prompt"]
    assert (
        double_escaped_backslash_json not in normal_upstream.calls[0]["system_prompt"]
    )
    assert "첫째 줄\\n둘째 줄" in normal_upstream.calls[0]["system_prompt"]

    test_runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, host),
        settings=settings.host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    payloads = asyncio.run(
        _collect_test_mode_payloads(
            test_runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=[LEGAL_QUERY],
                is_stream=True,
                system_prompt=BASE_SYSTEM_PROMPT,
                mcp_context=McpContextInput(
                    active_category=None,
                    rag_enabled=False,
                    provider_id="lexguard",
                ),
            ),
        )
    )

    context_aggregated = [
        payload
        for payload in payloads
        if payload.get("phase") == "context_merge"
        and payload.get("title") == "Context aggregated"
    ]

    assert len(context_aggregated) == 1
    fragment = context_aggregated[0]["raw"]["fragments"][0]
    assert fragment["structured_result"]["metadata"]["path"] == "C:\\tmp\\case.txt"
    assert fragment["structured_result"] == LEGAL_BACKSLASH_RESULT
    assert fragment["system_prompt"] is None


def test_normal_mode_render_is_byte_identical():
    context_result = normalize_context_result(
        action="legal_qa_tool",
        arguments={"query": LEGAL_QUERY},
        raw_result=LEGAL_RAW_RESULT,
        test_mode=False,
    )

    assert (
        render_context_result_system_prompt(context_result)
        == EXPECTED_NORMAL_MODE_LEGAL_PROMPT
    )


def test_normal_mode_legal_error_render_contract_unchanged():
    transport_error_context = normalize_context_result(
        action="legal_qa_tool",
        arguments={"query": LEGAL_QUERY},
        raw_result=LEGAL_TRANSPORT_ERROR_RESULT,
        test_mode=False,
    )
    tool_error_context = normalize_context_result(
        action="legal_qa_tool",
        arguments={"query": LEGAL_QUERY},
        raw_result=LEGAL_TOOL_ERROR_RESULT,
        test_mode=False,
    )

    assert render_context_result_system_prompt(transport_error_context) is None
    assert render_context_result_system_prompt(tool_error_context) is None
    assert (
        render_context_result_system_prompt(transport_error_context, test_mode=True)
        == f"=== [TEST] 법률 MCP 오류 응답 ===\n\n{json.dumps(LEGAL_TRANSPORT_ERROR_RESULT, ensure_ascii=False)}\n\n===================="
    )
    assert (
        render_context_result_system_prompt(tool_error_context, test_mode=True)
        == f"=== [TEST] 법률 MCP 오류 응답 ===\n\n{json.dumps(LEGAL_TOOL_ERROR_RESULT, ensure_ascii=False)}\n\n===================="
    )


def test_test_mode_context_aggregated_payload_is_structured():
    settings = _build_settings()
    decision = PlannerDecision(
        route="catalog_match",
        clean_query=LEGAL_QUERY,
        plans=(_build_legal_plan(),),
    )
    planner = _StaticPlanner(decision)
    host = _LexguardFixtureHost(
        settings,
        planner=cast(SharedPlannerCore, cast(object, planner)),
    )
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, host),
        settings=settings.host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    payloads = asyncio.run(
        _collect_test_mode_payloads(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=[LEGAL_QUERY],
                is_stream=True,
                system_prompt=BASE_SYSTEM_PROMPT,
                mcp_context=McpContextInput(
                    active_category=None,
                    rag_enabled=False,
                    provider_id="lexguard",
                ),
            ),
        )
    )

    context_aggregated = [
        payload
        for payload in payloads
        if payload.get("phase") == "context_merge"
        and payload.get("title") == "Context aggregated"
    ]

    assert len(context_aggregated) == 1
    fragment = context_aggregated[0]["raw"]["fragments"][0]
    assert fragment["structured_result"] == LEGAL_RAW_RESULT
    assert fragment["system_prompt"] is None


def test_test_mode_payload_avoids_nested_json_string_escaping():
    settings = _build_settings()
    decision = PlannerDecision(
        route="catalog_match",
        clean_query=LEGAL_QUERY,
        plans=(_build_legal_plan(),),
    )
    planner = _StaticPlanner(decision)
    host = _LexguardFixtureHost(
        settings,
        planner=cast(SharedPlannerCore, cast(object, planner)),
    )
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, host),
        settings=settings.host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    async def _run_test():
        stream = await runtime.stream_chat(
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=[LEGAL_QUERY],
                is_stream=True,
                system_prompt=BASE_SYSTEM_PROMPT,
                mcp_context=McpContextInput(
                    active_category=None,
                    rag_enabled=False,
                    provider_id="lexguard",
                ),
            )
        )
        return await _drain_stream(stream)

    chunks = asyncio.run(_run_test())

    # Find the Context aggregated chunk
    context_chunk = None
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.startswith("data: "):
            continue
        payload = json.loads(chunk[6:])
        if (
            payload.get("phase") == "context_merge"
            and payload.get("title") == "Context aggregated"
        ):
            context_chunk = chunk[6:]
            break

    assert context_chunk is not None

    # Parse the JSON once
    parsed = json.loads(context_chunk)

    # Assert the structured_result value is a proper Python dict, not a string
    fragment = parsed["raw"]["fragments"][0]
    assert isinstance(fragment["structured_result"], dict)

    # Verify the backslashes are preserved correctly in the dict
    assert fragment["structured_result"]["metadata"]["path"] == "C:\\temp\\판례.txt"

    # Verify it doesn't contain double-escaped strings like "C:\\\\temp\\\\판례.txt"
    # The raw JSON string should have "C:\\temp\\판례.txt" (which is 2 backslashes in JSON)
    assert '"C:\\\\temp\\\\판례.txt"' in context_chunk
    assert '"C:\\\\\\\\temp\\\\\\\\판례.txt"' not in context_chunk


def test_context_aggregated_consumers_accept_structured_payload():
    # This test simulates a consumer that expects the new structured payload
    # and verifies it can access the fields without errors.

    # Use the existing fixture logic to get the payload
    settings = _build_settings()
    decision = PlannerDecision(
        route="catalog_match",
        clean_query=LEGAL_QUERY,
        plans=(_build_legal_plan(),),
    )
    planner = _StaticPlanner(decision)
    host = _LexguardFixtureHost(
        settings,
        planner=cast(SharedPlannerCore, cast(object, planner)),
    )
    runtime = TestModeChatRuntime(
        request=SimpleNamespace(),
        mcp_host=cast(GenericMcpHost, host),
        settings=settings.host,
        planner=cast(DeterministicToolPlanner, cast(object, planner)),
    )

    payloads = asyncio.run(
        _collect_test_mode_payloads(
            runtime,
            ChatRuntimeInput(
                model_ids=["test-model"],
                contents=[LEGAL_QUERY],
                is_stream=True,
                system_prompt=BASE_SYSTEM_PROMPT,
                mcp_context=McpContextInput(
                    active_category=None,
                    rag_enabled=False,
                    provider_id="lexguard",
                ),
            ),
        )
    )

    context_aggregated = [
        payload
        for payload in payloads
        if payload.get("phase") == "context_merge"
        and payload.get("title") == "Context aggregated"
    ]

    assert len(context_aggregated) == 1
    raw_payload = context_aggregated[0]["raw"]

    # Simulate a consumer
    for fragment in raw_payload["fragments"]:
        # Consumer should be able to access structured_result
        assert "structured_result" in fragment
        assert fragment["structured_result"] == LEGAL_RAW_RESULT

        # Consumer should be able to access system_prompt (which is None)
        assert "system_prompt" in fragment
        assert fragment["system_prompt"] is None
