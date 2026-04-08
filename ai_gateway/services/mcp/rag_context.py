"""
Shared RAG prompt-building helpers for MCP-backed document context.
"""

from typing import Any

from fastapi import HTTPException
from .doc_search_policy import (
    DOC_SEARCH_FILE_FALLBACK_MAX_FILES,
    McpDocSearchSettings,
    build_doc_search_prompt_budget,
)


def _select_prompt_snippets(
    snippets: list[dict[str, Any]],
    max_per_doc: int = 2,
    max_total: int = 6,
    max_total_chars: int = 4500,
    min_docs_covered: int = 4,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    doc_counts: dict[str, int] = {}
    total_chars = 0
    covered_docs: set[str] = set()

    for snippet in snippets:
        if len(selected) >= max_total or len(covered_docs) >= min_docs_covered:
            break
        filename = snippet.get("filename", "")
        if not filename or filename in covered_docs:
            continue
        snippet_text = str(snippet.get("snippet", "")).strip()
        if not snippet_text:
            continue
        next_total = total_chars + len(snippet_text)
        if selected and next_total > max_total_chars:
            continue

        selected.append(snippet)
        doc_counts[filename] = 1
        covered_docs.add(filename)
        total_chars = next_total

    for snippet in snippets:
        if len(selected) >= max_total:
            break
        filename = snippet.get("filename", "")
        if not filename or doc_counts.get(filename, 0) >= max_per_doc:
            continue
        if any(
            selected_item.get("filename") == filename
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
        doc_counts[filename] = doc_counts.get(filename, 0) + 1
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
            f"📄 파일: {snippet['filename']}\n🔹 발췌 구간: {snippet.get('start', '-')}-{snippet.get('end', '-')}\n\n{snippet['snippet']}"
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
            f"📄 파일: {file_item['filename']}\n\n{file_item['snippet']}"
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
    }


__all__ = ["build_rag_response"]
