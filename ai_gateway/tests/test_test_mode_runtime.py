from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

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
