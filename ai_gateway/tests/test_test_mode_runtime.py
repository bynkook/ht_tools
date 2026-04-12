# pyright: reportImplicitRelativeImport=false

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import McpEventPolicy
from services.mcp.event_emitter import SystemEventEmitter
from services.mcp.event_guard import SystemEventGuard, _build_raw_preview
from services.mcp.host import build_context_debug_payload, normalize_context_result
from services.mcp.test_mode.planner import ToolPlan


def test_search_docs_result_is_normalized_into_rag_context():
    plan = ToolPlan(
        provider="internal_docs",
        action="search_docs_rag",
        params={"query": "위약금", "category": "test문서"},
    )
    raw_result = {
        "files": [{"filename": "standard-contract.md", "snippet": "위약금 관련 조항"}],
        "snippets": [
            {
                "filename": "standard-contract.md",
                "start": 10,
                "end": 20,
                "snippet": "위약금 관련 조항",
            }
        ],
    }

    normalized = normalize_context_result(
        action=plan.action,
        arguments=plan.params,
        raw_result=raw_result,
    )

    assert normalized["query"] == "위약금"
    assert normalized["category"] == "test문서"
    assert normalized["system_prompt"]
    assert "=== 참고 문서 ===" in normalized["system_prompt"]


def test_context_aggregated_payload_contains_final_system_prompt():
    context_results = [
        {
            "query": "표준계약서에서 위약금 관련 내용을 검색",
            "category": "test문서",
            "files": [
                {"filename": "standard-contract.md", "snippet": "위약금 관련 조항"}
            ],
            "snippets": [
                {
                    "filename": "standard-contract.md",
                    "start": 10,
                    "end": 20,
                    "snippet": "위약금 관련 조항",
                }
            ],
            "system_prompt": "=== 참고 문서 ===\n\n위약금 관련 조항",
        }
    ]

    payload = build_context_debug_payload(
        base_system_prompt="BASE SYSTEM PROMPT",
        context_results=context_results,
    )

    assert payload["fragment_count"] == 1
    assert payload["fragments"][0]["type"] == "rag_context"
    assert payload["final_system_prompt"]
    assert "BASE SYSTEM PROMPT" in payload["final_system_prompt"]
    assert "위약금 관련 조항" in payload["final_system_prompt"]


def test_system_event_payload_preserves_multi_provider_contract_fields():
    emitter = SystemEventEmitter(
        McpEventPolicy(
            verbose_json=True,
            redact_headers=True,
            max_payload_chars=4000,
            persist_system_logs=True,
            visible_band_limit=20,
            raw_bytes_limit=4096,
        ),
        channel="mcp_test",
    )

    event = emitter.info(
        phase="tool_call",
        title="Before tool call",
        content="Calling search_docs_rag.",
        request_id="turn-20260408-000000-000001",
        provider="internal_docs",
        provider_display_name="Internal Docs",
        tool="search_docs_rag",
        selection_reason="keyword rule matched",
        selection_rank=1,
        candidate_summary=["internal_docs.search_docs_rag"],
        raw={"headers": {"authorization": "secret-token"}},
    )
    payload = event.to_sse_payload()

    assert payload["event_type"] == "system_log"
    assert payload["kind"] == "system_log"
    assert payload["channel"] == "mcp_test"
    assert payload["phase"] == "tool_call"
    assert payload["provider"] == "internal_docs"
    assert payload["provider_id"] == "internal_docs"
    assert payload["provider_display_name"] == "Internal Docs"
    assert payload["tool"] == "search_docs_rag"
    assert payload["selection_reason"] == "keyword rule matched"
    assert payload["selection_rank"] == 1
    assert payload["candidate_summary"] == ["internal_docs.search_docs_rag"]
    assert payload["request_id"] == "turn-20260408-000000-000001"
    assert payload["repeat_count"] == 1
    assert payload["suppressed_count"] == 0
    assert payload["meta"]["persist"] is True
    assert payload["raw"]["headers"]["authorization"] == "[REDACTED]"


def test_system_event_guard_raw_preview_applied_per_event():
    """각 이벤트는 독립적으로 value 500자 제한 preview를 받는다."""
    policy = McpEventPolicy(
        verbose_json=True,
        redact_headers=True,
        max_payload_chars=4000,
        persist_system_logs=True,
        visible_band_limit=20,
        raw_bytes_limit=4096,
    )
    emitter = SystemEventEmitter(policy, channel="mcp_test")
    guard = SystemEventGuard(policy, request_id="turn-20260408-000000-000002")

    event1 = emitter.info(
        phase="tool_call",
        title="Short payload",
        content="Should pass through unchanged.",
        request_id="turn-20260408-000000-000002",
        provider="internal_docs",
        provider_display_name="Internal Docs",
        tool="search_docs_rag",
        raw={"payload": "x" * 10},
    )
    event2 = emitter.info(
        phase="tool_result",
        title="Long payload",
        content="Should be truncated per-value.",
        request_id="turn-20260408-000000-000002",
        provider="internal_docs",
        provider_display_name="Internal Docs",
        tool="search_docs_rag",
        raw={"payload": "y" * 600},
    )

    guard.accept(event1)
    second_emitted = guard.accept(event2)
    flushed = guard.flush()

    # event1이 emit됨 (event2 accept 시점에 pending에서 방출)
    assert len(second_emitted) == 1
    assert second_emitted[0].raw == {"payload": "x" * 10}

    # event2는 flush에서 나옴: value 500자 제한 적용
    assert len(flushed) == 1
    assert flushed[0].raw is not None
    truncated_value = flushed[0].raw["payload"]
    assert truncated_value.endswith("...(생략)")
    assert len(truncated_value) < 600 + len("...(생략)")


def test_build_raw_preview_short_values_kept_verbatim():
    """500자 이하 value는 원본 Python 값 그대로 유지된다."""
    raw = {"a": "hello", "b": [1, 2, 3]}
    result = _build_raw_preview(raw, 500)
    assert result is raw  # identity 보장


def test_build_raw_preview_long_value_truncated():
    """500자 초과 value는 s[:500] + '...(생략)' 문자열로 교체된다."""
    long_val = "z" * 600
    raw = {"key": long_val, "other": "short"}
    result = _build_raw_preview(raw, 500)

    assert result is not raw
    assert result["other"] == "short"
    truncated = result["key"]
    assert isinstance(truncated, str)
    assert truncated.endswith("...(생략)")
    # dumps("z"*600) 의 앞 500자를 잘라내고 suffix 추가
    import json

    serialized = json.dumps(long_val, ensure_ascii=False)
    assert truncated == serialized[:500] + "...(생략)"


def test_build_raw_preview_non_dict():
    """dict가 아닌 값도 500자 제한이 적용된다."""
    short_list = [1, 2, 3]
    assert _build_raw_preview(short_list, 500) is short_list  # identity

    long_str = "a" * 600
    result = _build_raw_preview(long_str, 500)
    assert isinstance(result, str)
    assert result.endswith("...(생략)")


def test_system_event_guard_normal_mode_policy_no_raw_budget_side_effects():
    """raw_bytes_limit 값에 무관하게 rawSuppressed/rawTruncated 메타는 더 이상 생성되지 않는다."""
    policy = McpEventPolicy(
        verbose_json=True,
        redact_headers=True,
        max_payload_chars=4000,
        persist_system_logs=True,
        visible_band_limit=20,
        raw_bytes_limit=0,
    )
    emitter = SystemEventEmitter(policy, channel="mcp_test")
    guard = SystemEventGuard(policy, request_id="turn-20260408-000000-000006")

    guard.accept(
        emitter.info(
            phase="tool_result",
            title="Normal mode raw guard",
            content="No budget suppression metadata should appear.",
            request_id="turn-20260408-000000-000006",
            provider="internal_docs",
            provider_display_name="Internal Docs",
            tool="search_docs_rag",
            raw={"payload": "f" * 10},
        )
    )
    flushed = guard.flush()

    assert len(flushed) == 1
    assert "rawSuppressed" not in flushed[0].meta
    assert "rawTruncated" not in flushed[0].meta
    assert flushed[0].raw == {"payload": "f" * 10}
