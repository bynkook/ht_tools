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
) -> str | None:
    """Convert a lexguard tool result dict into a system prompt string.

    lexguard-mcp tools return structured JSON like:
      legal_qa_tool / precedent_lookup_tool / law_article_tool:
        {"results": {"laws": [...], "precedents": [...], ...}, "summary": "..."}
      document_issue_tool:
        {"issues": [...], "summary": "...", "risk_level": "..."}

    Returns a formatted system prompt string, or None if the result is empty.
    """
    if not raw_result:
        return None

    # document_issue_tool returns issues + summary
    if action == "document_issue_tool":
        issues = raw_result.get("issues", [])
        summary = raw_result.get("summary", "")
        risk_level = raw_result.get("risk_level", "")

        if not issues and not summary:
            return None

        blocks: list[str] = []
        if risk_level:
            blocks.append(f"⚠️ 위험도: {risk_level}")
        if summary:
            blocks.append(f"📋 검토 요약:\n{summary}")
        if issues:
            issue_lines = []
            for i, issue in enumerate(issues, 1):
                title = issue.get("title") or issue.get("clause") or f"이슈 {i}"
                desc = issue.get("description") or issue.get("content") or ""
                recommendation = issue.get("recommendation") or ""
                line = f"{i}. **{title}**"
                if desc:
                    line += f"\n   - {desc}"
                if recommendation:
                    line += f"\n   - 권고: {recommendation}"
                issue_lines.append(line)
            blocks.append("🔍 발견된 문제점:\n" + "\n".join(issue_lines))

        joined = "\n\n".join(blocks)
        return (
            "당신은 법률 문서 검토 전문가 어시스턴트입니다.\n"
            "아래 계약서/문서 법적 검토 결과를 바탕으로 사용자에게 설명하세요.\n\n"
            f"=== 법적 검토 결과 ===\n\n{joined}\n\n===================="
        )

    # legal_qa_tool, law_article_tool, precedent_lookup_tool, etc.
    # These return {"results": {...}, "summary": "..."}
    results = raw_result.get("results", {})
    summary = raw_result.get("summary", "")

    if not results and not summary:
        # Try raw_text fallback (JSON parse failed)
        raw_text = raw_result.get("raw_text", "")
        if raw_text:
            return (
                "당신은 법률 전문가 어시스턴트입니다.\n"
                "아래 법률 검색 결과를 바탕으로 사용자의 질문에 답하세요.\n\n"
                f"=== 법률 검색 결과 ===\n\n{raw_text}\n\n===================="
            )
        return None

    blocks = []
    if summary:
        blocks.append(f"📋 요약:\n{summary}")

    if isinstance(results, dict):
        laws = results.get("laws", [])
        precedents = results.get("precedents", [])
        interpretations = results.get("interpretations", [])
        articles = results.get("articles", [])

        if laws:
            law_lines = []
            for law in laws[:5]:
                name = law.get("law_name") or law.get("name") or ""
                article = law.get("article") or law.get("article_no") or ""
                content = law.get("content") or law.get("text") or ""
                line = f"• {name}"
                if article:
                    line += f" 제{article}조"
                if content:
                    line += f": {content[:200]}"
                law_lines.append(line)
            blocks.append("⚖️ 관련 법령:\n" + "\n".join(law_lines))

        if articles:
            article_lines = []
            for art in articles[:5]:
                name = art.get("law_name") or art.get("name") or ""
                article = art.get("article") or art.get("article_no") or ""
                content = art.get("content") or art.get("text") or ""
                line = f"• {name}"
                if article:
                    line += f" 제{article}조"
                if content:
                    line += f": {content[:200]}"
                article_lines.append(line)
            blocks.append("📜 관련 조문:\n" + "\n".join(article_lines))

        if precedents:
            precedent_lines = []
            for prec in precedents[:5]:
                case_no = prec.get("case_no") or prec.get("case_number") or ""
                court = prec.get("court") or ""
                summary_text = prec.get("summary") or prec.get("content") or ""
                line = f"• {court} {case_no}".strip()
                if summary_text:
                    line += f": {summary_text[:200]}"
                precedent_lines.append(line)
            blocks.append("🏛️ 관련 판례:\n" + "\n".join(precedent_lines))

        if interpretations:
            interp_lines = [
                f"• {interp.get('content') or interp.get('text') or str(interp)}"
                for interp in interpretations[:3]
            ]
            blocks.append("📖 유권해석:\n" + "\n".join(interp_lines))

    if not blocks:
        return None

    joined = "\n\n".join(blocks)
    return (
        "당신은 법률 전문가 어시스턴트입니다.\n"
        "아래 법률 검색 결과를 바탕으로 사용자의 질문에 정확하게 답하세요.\n"
        "검색 결과에 없는 내용은 '제공된 정보에서 찾을 수 없습니다'라고 솔직하게 답하세요.\n\n"
        f"=== 법률 검색 결과 ===\n\n{joined}\n\n===================="
    )


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
