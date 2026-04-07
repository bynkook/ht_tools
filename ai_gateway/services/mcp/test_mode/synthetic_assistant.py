"""
Synthetic assistant summaries for MCP Test Mode.
"""

from .planner import ToolPlan


def build_synthetic_assistant_summary(
    *,
    plans: list[ToolPlan],
    results: list[dict],
) -> str:
    if not plans:
        return "[MCP-TEST] 외부 LLM 호출을 생략했습니다. 선택된 MCP tool이 없습니다."

    lines = ["[MCP-TEST] 외부 LLM 호출 없이 MCP 결과를 수집했습니다.", ""]
    for index, plan in enumerate(plans, start=1):
        lines.append(f"{index}. `{plan.provider}.{plan.action}` 실행")
        result = results[index - 1] if index - 1 < len(results) else {}
        if plan.action == "search_docs_rag":
            snippets = result.get("snippets") or []
            lines.append(f"   - 관련 스니펫 {len(snippets)}개 수집")
        elif plan.action == "list_categories_detail":
            categories = result.get("categories") or []
            lines.append(f"   - 카테고리 {len(categories)}개 확인")
        elif plan.action == "list_docs_detail":
            files = result.get("files") or []
            lines.append(f"   - 문서 {len(files)}개 확인")
        elif plan.action == "read_doc":
            content = result.get("content") or ""
            lines.append(f"   - 문서 본문 {len(content)}자 로드")

    return "\n".join(lines)


__all__ = ["build_synthetic_assistant_summary"]
