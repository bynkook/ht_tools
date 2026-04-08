from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import McpEventPolicy
from services.mcp.event_emitter import SystemEventEmitter
from services.mcp.event_guard import SystemEventGuard
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
            "files": [{"filename": "standard-contract.md", "snippet": "위약금 관련 조항"}],
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


def test_system_event_guard_marks_raw_suppression_with_multi_provider_context():
    policy = McpEventPolicy(
        verbose_json=True,
        redact_headers=True,
        max_payload_chars=4000,
        persist_system_logs=True,
        visible_band_limit=20,
        raw_bytes_limit=8,
    )
    emitter = SystemEventEmitter(policy, channel="mcp_test")
    guard = SystemEventGuard(policy, request_id="turn-20260408-000000-000002")

    guarded = guard.accept(
        emitter.info(
            phase="tool_call",
            title="After tool call",
            content="search_docs_rag completed.",
            request_id="turn-20260408-000000-000002",
            provider="internal_docs",
            provider_display_name="Internal Docs",
            tool="search_docs_rag",
            selection_reason="keyword rule matched",
            selection_rank=1,
            raw={"payload": "x" * 128},
        )
    )
    flushed = guard.flush()

    assert guarded == []
    assert len(flushed) == 2
    assert flushed[0].meta["rawSuppressed"] is True
    assert flushed[0].provider == "internal_docs"
    assert flushed[0].provider_id == "internal_docs"
    assert flushed[0].provider_display_name == "Internal Docs"
    assert flushed[0].tool == "search_docs_rag"
    assert flushed[1].phase == "log_guard"
    assert flushed[1].meta["persist"] is True
    assert flushed[1].meta["rawSuppressedCount"] == 1
    assert flushed[1].provider == "internal_docs"
    assert flushed[1].provider_id == "internal_docs"
    assert flushed[1].provider_display_name == "Internal Docs"
    assert flushed[1].tool == "search_docs_rag"