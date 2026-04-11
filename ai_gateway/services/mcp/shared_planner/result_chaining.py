"""
Result chaining utilities for sequential MCP pipeline execution.

Design principle:
- Whether to call lexguard is decided at planning time by the activation catalog
  (lexguard.default.json keyword rules), not at execution time.
- Result chaining passes doc_search/read_doc output as document_text to the
  next tool (document_issue_tool) when the planner has already scheduled both.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_document_text_from_result(result: dict[str, Any]) -> str | None:
    """Extract document text from a doc_search (search_docs_rag) or read_doc result.

    For search_docs_rag:
      raw_result contains:
        - files: list of matching files
        - snippets: list of {filename, snippet, start, end, ...}

    For read_doc:
      raw_result contains:
        - content: full document text string
        - filename: document filename
        - category: optional category name

    Returns the full document text (or concatenated snippet texts), or None if empty.
    """
    raw_result = result.get("raw_result")
    if not isinstance(raw_result, dict):
        return None

    # read_doc returns full content directly
    content = raw_result.get("content", "")
    if content and isinstance(content, str):
        return content.strip() or None

    # Try snippets first (search_docs_rag common case)
    snippets = raw_result.get("snippets", [])
    if snippets:
        texts = []
        for snippet in snippets:
            snippet_text = snippet.get("snippet", "")
            if snippet_text:
                texts.append(snippet_text)
        if texts:
            return "\n\n---\n\n".join(texts)

    # Fallback to files if no snippets
    files = raw_result.get("files", [])
    if files:
        texts = []
        for file_info in files:
            content = file_info.get("content", "")
            if content:
                texts.append(content)
        if texts:
            return "\n\n---\n\n".join(texts)

    return None


def should_chain_doc_to_lexguard(
    current_action: str,
    next_action: str,
) -> bool:
    """Determine if result chaining should occur from doc_search/read_doc to lexguard.

    Chaining conditions:
    1. Current action is doc_search (search_docs_rag) or full-document read (read_doc)
    2. Next action requires document_text (document_issue_tool)

    Note: Legal-relatedness is NOT checked here. That's determined by the
    original user query at planning time, not at execution time.
    """
    if current_action not in {"search_docs_rag", "read_doc"}:
        return False

    if next_action != "document_issue_tool":
        return False

    return True


def chain_document_text(
    next_plan_params: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """Inject document_text from doc_search result into next plan's params.

    Returns a new params dict with document_text populated from the result.
    """
    document_text = extract_document_text_from_result(result)
    if document_text is None:
        logger.debug(
            "chain_document_text: no document_text extracted from result; "
            "returning original params"
        )
        return next_plan_params

    updated_params = dict(next_plan_params)
    updated_params["document_text"] = document_text
    return updated_params


__all__ = [
    "chain_document_text",
    "extract_document_text_from_result",
    "should_chain_doc_to_lexguard",
]
