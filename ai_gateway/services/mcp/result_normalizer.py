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


__all__ = ["tool_result_to_dict", "tool_result_to_text"]
