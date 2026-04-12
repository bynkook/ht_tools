"""
Helpers for building and merging MCP-backed chat context.
"""

from typing import Any


def build_multi_file_system_prompt(resolved_mentions: list[dict[str, Any]]) -> str | None:
    blocks = []
    for resolved in resolved_mentions:
        filename = resolved.get("filename")
        snippets = resolved.get("snippets", [])
        for snippet in snippets:
            snippet_text = snippet.get("snippet")
            if not snippet_text:
                continue
            blocks.append(f"📄 **파일: {filename}**\n\n{snippet_text}")

    if not blocks:
        return None

    joined_blocks = "\n\n---\n\n".join(blocks)
    return (
        "당신은 사내 문서 기반 질문 답변 어시스턴트입니다.\n"
        "아래 참고 문서를 바탕으로 사용자의 질문에 답하세요.\n"
        "참고 문서에 없는 내용은 '제공된 문서에서 찾을 수 없습니다'라고 솔직하게 답하세요.\n\n"
        f"=== 참고 문서 ===\n\n{joined_blocks}\n\n=================="
    )


def merge_system_prompts(primary_prompt: str | None, secondary_prompt: str | None) -> str | None:
    if primary_prompt and secondary_prompt:
        return f"{primary_prompt.rstrip()}\n\n---\n\n{secondary_prompt.lstrip()}"
    return primary_prompt or secondary_prompt


__all__ = ["build_multi_file_system_prompt", "merge_system_prompts"]
