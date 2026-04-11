"""
Shared RAG prompt-building helpers for MCP-backed document context.
"""

import json
from typing import Any

from fastapi import HTTPException
from .doc_search_policy import (
    DOC_SEARCH_FILE_FALLBACK_MAX_FILES,
    McpDocSearchSettings,
    build_doc_search_prompt_budget,
)


def _doc_key(item: dict[str, Any]) -> tuple[str | None, str]:
    return (item.get("category"), str(item.get("filename", "")))


def _select_prompt_snippets(
    snippets: list[dict[str, Any]],
    max_per_doc: int = 2,
    max_total: int = 6,
    max_total_chars: int = 4500,
    min_docs_covered: int = 4,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    doc_counts: dict[tuple[str | None, str], int] = {}
    total_chars = 0
    covered_docs: set[tuple[str | None, str]] = set()

    for snippet in snippets:
        if len(selected) >= max_total or len(covered_docs) >= min_docs_covered:
            break
        doc_key = _doc_key(snippet)
        filename = doc_key[1]
        if not filename or doc_key in covered_docs:
            continue
        snippet_text = str(snippet.get("snippet", "")).strip()
        if not snippet_text:
            continue
        next_total = total_chars + len(snippet_text)
        if selected and next_total > max_total_chars:
            continue

        selected.append(snippet)
        doc_counts[doc_key] = 1
        covered_docs.add(doc_key)
        total_chars = next_total

    for snippet in snippets:
        if len(selected) >= max_total:
            break
        doc_key = _doc_key(snippet)
        filename = doc_key[1]
        if not filename or doc_counts.get(doc_key, 0) >= max_per_doc:
            continue
        if any(
            _doc_key(selected_item) == doc_key
            and selected_item.get("start") == snippet.get("start")
            and selected_item.get("end") == snippet.get("end")
            for selected_item in selected
        ):
            continue

        snippet_text = str(snippet.get("snippet", "")).strip()
        if not snippet_text:
            continue

        next_total = total_chars + len(snippet_text)
        if selected and next_total > max_total_chars:
            continue

        selected.append(snippet)
        doc_counts[doc_key] = doc_counts.get(doc_key, 0) + 1
        total_chars = next_total

        if len(selected) >= max_total:
            break

    return selected


def build_rag_response(
    *,
    query: str,
    category: str | None,
    filename_filter: str | None,
    data: dict[str, Any],
    doc_search_settings: McpDocSearchSettings | None = None,
) -> dict[str, Any]:
    if data.get("error"):
        raise HTTPException(status_code=404, detail=data["error"])

    files = data.get("files", [])
    snippets = data.get("snippets", [])

    if not files and not snippets:
        no_result_prompt = (
            "당신은 사내 문서 기반 질문 답변 어시스턴트입니다.\n"
            "검색 결과 관련 문서를 찾을 수 없었습니다.\n"
            "일반 지식으로 답변하거나 사용자에게 더 구체적인 검색 키워드를 제안하세요.\n"
            "절대 /mcp read, /mcp list 같은 시스템 커맨드를 직접 출력하지 마세요."
        )
        return {
            "success": True,
            "files": [],
            "snippets": [],
            "query": query,
            "category": category,
            "system_prompt": no_result_prompt,
            "retrieval_meta": data.get("retrieval_meta"),
        }

    category_label = f" ({category})" if category else " (전체)"
    if snippets:
        budget = build_doc_search_prompt_budget(
            query,
            snippets,
            filename_filter=filename_filter,
            settings=doc_search_settings,
        )
        selected_snippets = _select_prompt_snippets(
            snippets,
            max_per_doc=budget.max_per_doc,
            max_total=budget.max_total,
            max_total_chars=budget.max_total_chars,
            min_docs_covered=budget.min_docs_covered,
        )
        doc_blocks = "\n\n---\n\n".join(
            (
                f"📄 파일: {snippet['filename']}"
                + (
                    f"\n🗂️ 카테고리: {snippet.get('category')}"
                    if snippet.get("category") and not category
                    else ""
                )
                + f"\n🔹 발췌 구간: {snippet.get('start', '-')}-{snippet.get('end', '-')}\n\n{snippet['snippet']}"
            )
            for snippet in selected_snippets
        )
    else:
        selected_snippets = []
        fallback_file_limit = (
            doc_search_settings.prompt_file_fallback_max_files
            if doc_search_settings is not None
            else DOC_SEARCH_FILE_FALLBACK_MAX_FILES
        )
        doc_blocks = "\n\n---\n\n".join(
            (
                f"📄 파일: {file_item['filename']}"
                + (
                    f"\n🗂️ 카테고리: {file_item.get('category')}"
                    if file_item.get("category") and not category
                    else ""
                )
                + f"\n\n{file_item['snippet']}"
            )
            for file_item in files[:fallback_file_limit]
        )

    system_prompt = (
        "당신은 사내 문서 기반 질문 답변 어시스턴트입니다.\n"
        f"아래 참고 문서{category_label}를 바탕으로 사용자의 질문에 답하세요.\n"
        "참고 문서에 없는 내용은 '제공된 문서에서 찾을 수 없습니다'라고 솔직하게 답하세요.\n\n"
        f"=== 참고 문서 ===\n\n{doc_blocks}\n\n=================="
    )

    return {
        "success": True,
        "files": files,
        "snippets": selected_snippets if snippets else [],
        "query": query,
        "category": category,
        "system_prompt": system_prompt,
        "retrieval_meta": data.get("retrieval_meta"),
    }


def build_legal_context_system_prompt(
    action: str,
    raw_result: dict[str, Any],
    *,
    test_mode: bool = False,
) -> str | None:
    """Convert a lexguard tool result dict into a system prompt string.

    Design contract (normal mode):
    - Transport/API failures  → raw_result contains "error_code" field → return None
    - Tool input errors       → raw_result has success=False + "error" field → return None
    - All other responses     → pass raw_result as-is via json.dumps to the LLM

    test_mode=True:
    - All responses (including errors) are serialized and returned so that
      the test mode UI can display the full MCP response for inspection.

    FabriX does not parse or reformat lexguard response content.
    The LLM receives the full structured result and interprets it directly.
    """
    if not raw_result:
        return None

    raw_json = json.dumps(raw_result, ensure_ascii=False)

    if not test_mode:
        # Transport/API layer failure: API auth error, timeout, HTML response, etc.
        # lexguard-mcp sets error_code (e.g. API_ERROR_AUTH, API_ERROR_TIMEOUT) in these cases.
        if raw_result.get("error_code"):
            return None

        # Tool-level input validation failure: e.g. unknown committee_type, law not found.
        # These have success=False + an "error" message string.
        # Nothing useful to pass to the LLM; the tool itself rejected the input.
        if raw_result.get("success") is False and raw_result.get("error"):
            return None

        return (
            "당신은 법률 전문가 어시스턴트입니다.\n"
            "아래 법률 검색 결과(JSON)를 바탕으로 사용자의 질문에 정확하게 답하세요.\n"
            "검색 결과에 없는 내용은 '제공된 정보에서 찾을 수 없습니다'라고 솔직하게 답하세요.\n\n"
            f"=== 법률 검색 결과 ===\n\n{raw_json}\n\n===================="
        )

    # test_mode: always show full response including errors
    is_error = bool(raw_result.get("error_code")) or (
        raw_result.get("success") is False and raw_result.get("error")
    )
    section_header = (
        "[TEST] 법률 MCP 오류 응답" if is_error else "[TEST] 법률 검색 결과"
    )
    return f"=== {section_header} ===\n\n{raw_json}\n\n===================="


# Lexguard action names that produce legal context (not RAG doc search)
LEXGUARD_LEGAL_ACTIONS = frozenset(
    [
        "legal_qa_tool",
        "law_article_tool",
        "precedent_lookup_tool",
        "document_issue_tool",
        "law_comparison_tool",
        "interpretation_tool",
        "administrative_appeal_tool",
        "constitutional_decision_tool",
        "committee_decision_tool",
        "special_administrative_appeal_tool",
        "local_ordinance_tool",
        "administrative_rule_tool",
    ]
)


__all__ = [
    "build_legal_context_system_prompt",
    "build_rag_response",
    "LEXGUARD_LEGAL_ACTIONS",
]
