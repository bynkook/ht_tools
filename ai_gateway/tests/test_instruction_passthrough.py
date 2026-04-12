"""Tests for lexguard writing-instruction passthrough to LLM system prompt.

Covers:
- tool_result_to_content_text(): content[] → instruction text extraction
- render_legal_context_system_prompt(): instruction_text prepended correctly
- normalize_context_result(): instruction_text stored in context_result for lexguard tools
"""

import json
from types import SimpleNamespace
from typing import Any

import pytest

from ai_gateway.services.mcp.host import (
    normalize_context_result,
    render_context_result_system_prompt,
)
from ai_gateway.services.mcp.rag_context import render_legal_context_system_prompt
from ai_gateway.services.mcp.result_normalizer import tool_result_to_content_text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

INSTRUCTION_TEXT = "답변 형식 (A 타입): 반드시 하이픈(-)으로 시작하세요."
NOTICE_TEXT = "⚠️ 법령/판례 API 키 설정이 필요합니다."
JSON_BLOB = json.dumps({"success": True, "answer": "test"}, ensure_ascii=False)

LEGAL_SUCCESS_RESULT = {
    "success": True,
    "query": "근로계약서 검토",
    "answer": "계약서에 문제가 없습니다.",
}


def _make_content_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text)


def _make_mock_tool_result(
    content_texts: list[str], structured_content: dict | None = None
) -> SimpleNamespace:
    """Simulate a fastmcp CallToolResult object."""
    return SimpleNamespace(
        content=[_make_content_block(t) for t in content_texts],
        structured_content=structured_content,
    )


# ---------------------------------------------------------------------------
# tool_result_to_content_text()
# ---------------------------------------------------------------------------


class TestToolResultToContentText:
    def test_extracts_instruction_only_skipping_json(self):
        """Instruction text returned; JSON blob at end excluded."""
        result = _make_mock_tool_result([INSTRUCTION_TEXT, JSON_BLOB])
        extracted = tool_result_to_content_text(result)
        assert extracted == INSTRUCTION_TEXT

    def test_extracts_instruction_and_notice_skipping_json(self):
        """Both instruction and notice returned; JSON blob excluded."""
        result = _make_mock_tool_result([INSTRUCTION_TEXT, NOTICE_TEXT, JSON_BLOB])
        extracted = tool_result_to_content_text(result)
        assert extracted == f"{INSTRUCTION_TEXT}\n\n{NOTICE_TEXT}"

    def test_returns_none_when_only_json(self):
        """Only JSON blob in content → None (no instruction text)."""
        result = _make_mock_tool_result([JSON_BLOB])
        assert tool_result_to_content_text(result) is None

    def test_returns_none_when_content_empty(self):
        """Empty content list → None."""
        result = _make_mock_tool_result([])
        assert tool_result_to_content_text(result) is None

    def test_returns_none_when_no_content_attr(self):
        """Object with no content attr → None."""
        result = SimpleNamespace()
        assert tool_result_to_content_text(result) is None

    def test_returns_none_for_dict_input(self):
        """Plain dict has no content attr → None (already-coerced result)."""
        assert tool_result_to_content_text({"success": True}) is None

    def test_skips_list_json_blob(self):
        """JSON array blob also excluded."""
        list_blob = json.dumps([{"a": 1}], ensure_ascii=False)
        result = _make_mock_tool_result([INSTRUCTION_TEXT, list_blob])
        assert tool_result_to_content_text(result) == INSTRUCTION_TEXT

    def test_strips_whitespace_from_blocks(self):
        """Whitespace around blocks stripped."""
        result = _make_mock_tool_result([f"  {INSTRUCTION_TEXT}  ", JSON_BLOB])
        assert tool_result_to_content_text(result) == INSTRUCTION_TEXT


# ---------------------------------------------------------------------------
# render_legal_context_system_prompt()
# ---------------------------------------------------------------------------


class TestRenderLegalContextSystemPrompt:
    def _base_prompt(self, raw_result: dict) -> str:
        raw_json = json.dumps(raw_result, ensure_ascii=False)
        return (
            "당신은 법률 전문가 어시스턴트입니다.\n"
            "아래 법률 검색 결과(JSON)를 바탕으로 사용자의 질문에 정확하게 답하세요.\n"
            "검색 결과에 없는 내용은 '제공된 정보에서 찾을 수 없습니다'라고 솔직하게 답하세요.\n\n"
            f"=== 법률 검색 결과 ===\n\n{raw_json}\n\n===================="
        )

    def test_instruction_prepended_in_normal_mode(self):
        """instruction_text prepended before base prompt."""
        result = render_legal_context_system_prompt(
            LEGAL_SUCCESS_RESULT,
            instruction_text=INSTRUCTION_TEXT,
        )
        expected = f"{INSTRUCTION_TEXT}\n\n{self._base_prompt(LEGAL_SUCCESS_RESULT)}"
        assert result == expected

    def test_no_instruction_normal_mode_unchanged(self):
        """instruction_text=None → identical to previous behavior."""
        result = render_legal_context_system_prompt(LEGAL_SUCCESS_RESULT)
        assert result == self._base_prompt(LEGAL_SUCCESS_RESULT)

    def test_instruction_prepended_in_test_mode(self):
        """instruction_text prepended in test_mode too."""
        raw_json = json.dumps(LEGAL_SUCCESS_RESULT, ensure_ascii=False)
        result = render_legal_context_system_prompt(
            LEGAL_SUCCESS_RESULT,
            instruction_text=INSTRUCTION_TEXT,
            test_mode=True,
        )
        base = f"=== [TEST] 법률 검색 결과 ===\n\n{raw_json}\n\n===================="
        assert result == f"{INSTRUCTION_TEXT}\n\n{base}"

    def test_no_instruction_test_mode_unchanged(self):
        """instruction_text=None in test_mode → identical to previous behavior."""
        raw_json = json.dumps(LEGAL_SUCCESS_RESULT, ensure_ascii=False)
        result = render_legal_context_system_prompt(
            LEGAL_SUCCESS_RESULT, test_mode=True
        )
        assert (
            result
            == f"=== [TEST] 법률 검색 결과 ===\n\n{raw_json}\n\n===================="
        )

    def test_error_result_returns_none_in_normal_mode(self):
        """Transport error → None regardless of instruction_text."""
        error_result = {
            "success": False,
            "error_code": "API_ERROR_TIMEOUT",
            "error": "timeout",
        }
        assert (
            render_legal_context_system_prompt(
                error_result, instruction_text=INSTRUCTION_TEXT
            )
            is None
        )

    def test_tool_failure_returns_none_in_normal_mode(self):
        """Tool failure (success=False) → None regardless of instruction_text."""
        failure = {"success": False, "error": "invalid input"}
        assert (
            render_legal_context_system_prompt(
                failure, instruction_text=INSTRUCTION_TEXT
            )
            is None
        )

    def test_error_result_in_test_mode_includes_instruction(self):
        """Test mode error → instruction still prepended."""
        error_result = {
            "success": False,
            "error_code": "API_ERROR_TIMEOUT",
            "error": "timeout",
        }
        raw_json = json.dumps(error_result, ensure_ascii=False)
        result = render_legal_context_system_prompt(
            error_result, instruction_text=INSTRUCTION_TEXT, test_mode=True
        )
        base = (
            f"=== [TEST] 법률 MCP 오류 응답 ===\n\n{raw_json}\n\n===================="
        )
        assert result == f"{INSTRUCTION_TEXT}\n\n{base}"


# ---------------------------------------------------------------------------
# normalize_context_result() — instruction_text field
# ---------------------------------------------------------------------------


class TestNormalizeContextResultInstructionText:
    def test_dict_raw_result_yields_none_instruction(self):
        """Plain dict raw_result (already coerced) → instruction_text=None."""
        ctx = normalize_context_result(
            action="legal_qa_tool",
            arguments={"query": "test"},
            raw_result=LEGAL_SUCCESS_RESULT,
        )
        assert ctx["instruction_text"] is None

    def test_mock_tool_result_with_instruction_extracted(self):
        """CallToolResult mock with instruction in content[] → instruction_text set."""
        mock_result = _make_mock_tool_result(
            [INSTRUCTION_TEXT, JSON_BLOB],
            structured_content=LEGAL_SUCCESS_RESULT,
        )
        ctx = normalize_context_result(
            action="legal_qa_tool",
            arguments={"query": "test"},
            raw_result=mock_result,
        )
        assert ctx["instruction_text"] == INSTRUCTION_TEXT
        assert ctx["structured_result"] == LEGAL_SUCCESS_RESULT

    def test_mock_tool_result_no_instruction_yields_none(self):
        """CallToolResult mock with only JSON content → instruction_text=None."""
        mock_result = _make_mock_tool_result(
            [JSON_BLOB],
            structured_content=LEGAL_SUCCESS_RESULT,
        )
        ctx = normalize_context_result(
            action="legal_qa_tool",
            arguments={"query": "test"},
            raw_result=mock_result,
        )
        assert ctx["instruction_text"] is None

    def test_non_lexguard_action_has_no_instruction_text_key(self):
        """Non-lexguard tools (read_doc, search_docs_rag) don't get instruction_text."""
        ctx = normalize_context_result(
            action="read_doc",
            arguments={"filename": "test.pdf"},
            raw_result={"content": "문서 내용"},
        )
        assert "instruction_text" not in ctx

    def test_document_issue_tool_extracts_instruction(self):
        """document_issue_tool also gets instruction_text extracted."""
        mock_result = _make_mock_tool_result(
            [INSTRUCTION_TEXT, JSON_BLOB],
            structured_content={"success": True, "document_analysis": {}},
        )
        ctx = normalize_context_result(
            action="document_issue_tool",
            arguments={},
            raw_result=mock_result,
        )
        assert ctx["instruction_text"] == INSTRUCTION_TEXT
        assert ctx["action"] == "document_issue_tool"


# ---------------------------------------------------------------------------
# render_context_result_system_prompt() — end-to-end with instruction_text
# ---------------------------------------------------------------------------


class TestRenderContextResultSystemPromptWithInstruction:
    def test_instruction_text_passed_through_to_render(self):
        """instruction_text in context_result flows into the rendered system prompt."""
        raw_json = json.dumps(LEGAL_SUCCESS_RESULT, ensure_ascii=False)
        context_result = {
            "action": "legal_qa_tool",
            "structured_result": LEGAL_SUCCESS_RESULT,
            "system_prompt": None,
            "instruction_text": INSTRUCTION_TEXT,
        }
        rendered = render_context_result_system_prompt(context_result)
        assert rendered is not None
        assert rendered.startswith(INSTRUCTION_TEXT)
        assert raw_json in rendered

    def test_no_instruction_text_renders_without_prefix(self):
        """instruction_text=None → rendered prompt has no prefix."""
        context_result = {
            "action": "legal_qa_tool",
            "structured_result": LEGAL_SUCCESS_RESULT,
            "system_prompt": None,
            "instruction_text": None,
        }
        rendered = render_context_result_system_prompt(context_result)
        assert rendered is not None
        assert not rendered.startswith(INSTRUCTION_TEXT)
        assert rendered.startswith("당신은 법률 전문가 어시스턴트입니다.")
