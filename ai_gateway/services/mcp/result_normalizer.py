"""
Helpers for normalizing FastMCP tool results.
"""

import json
from typing import Any


def tool_result_to_dict(result: Any) -> dict[str, Any]:
    """Convert a FastMCP tool result to plain structured JSON."""
    if result.structured_content is not None:
        return result.structured_content

    raw = "\n".join(block.text for block in result.content if hasattr(block, "text"))
    return json.loads(raw) if raw else {}


def tool_result_to_text(result: Any) -> str:
    """Convert a FastMCP tool result to plain text for UX rendering."""
    if result.data is not None:
        return str(result.data)

    return "\n".join(block.text for block in result.content if hasattr(block, "text"))


__all__ = ["tool_result_to_dict", "tool_result_to_text"]
