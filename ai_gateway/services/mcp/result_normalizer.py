"""
Helpers for normalizing FastMCP tool results.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def tool_result_to_dict(result: Any) -> dict[str, Any]:
    """Convert a FastMCP tool result to plain structured JSON."""
    if result.structured_content is not None:
        return result.structured_content

    raw = "\n".join(block.text for block in result.content if hasattr(block, "text"))
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning(
            "tool_result_to_dict: failed to parse tool result as JSON: %s", exc
        )
        return {"raw_text": raw}


def tool_result_to_text(result: Any) -> str:
    """Convert a FastMCP tool result to plain text for UX rendering."""
    if result.data is not None:
        return str(result.data)

    return "\n".join(block.text for block in result.content if hasattr(block, "text"))


def tool_result_to_content_text(result: Any) -> str | None:
    """Extract writing instruction text from MCP tool result content array.

    lexguard tools place writing instructions (response format guides) in the
    content[] array as plain text blocks, separate from the structuredContent
    which contains the actual tool result data.

    Response structure from lexguard (e.g. document_issue_tool, legal_qa_tool):
      content[0]: writing instruction text  ← this function extracts these
      content[1]: optional error notice
      content[-1]: structured JSON echo (same data as structuredContent)

    JSON blocks (starting with '{' or '[') are excluded so that only the
    human-readable instruction text is returned.

    Returns None if no instruction text exists (e.g. result is already a dict,
    or content contains only JSON blocks).
    """
    blocks = getattr(result, "content", None)
    if not blocks:
        return None

    instruction_texts = []
    for block in blocks:
        if not hasattr(block, "text") or not block.text:
            continue
        stripped = block.text.strip()
        # JSON blocks are the structured data echo — skip them
        if stripped.startswith("{") or stripped.startswith("["):
            continue
        instruction_texts.append(stripped)

    if not instruction_texts:
        return None
    return "\n\n".join(instruction_texts)


__all__ = ["tool_result_to_content_text", "tool_result_to_dict", "tool_result_to_text"]
