"""
Result chaining utilities for sequential MCP pipeline execution.

Design principle:
- Whether to call lexguard is decided at planning time by the activation catalog
  (lexguard.default.json keyword rules), not at execution time.
- Result chaining passes doc_search/read_doc output as document_text to the
  next tool (document_issue_tool) when the planner has already scheduled both.
- When full_read_mode=True is set on a search_docs_rag plan, the execution loop
  extracts the TOP1 filename and inserts a read_doc plan dynamically before
  document_issue_tool, so the full document text (not just snippets) is analysed.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_top_filename_from_rag_result(result: dict[str, Any]) -> str | None:
    """Extract the TOP1 filename from a search_docs_rag result.

    Used by the execution loop when full_read_mode=True is set on a
    search_docs_rag plan.  If a filename is available, the loop inserts a
    read_doc plan so the full document text reaches document_issue_tool instead
    of snippet fragments.

    Lookup order:
    1. snippets[0]["filename"]  — highest-ranked RAG chunk (most reliable)
    2. files[0]["filename"]     — file-level metadata fallback

    Returns the filename string, or None if no filename is available.
    """
    raw_result = result.get("raw_result")
    if not isinstance(raw_result, dict):
        return None

    snippets = raw_result.get("snippets", [])
    if snippets and isinstance(snippets[0], dict):
        filename = snippets[0].get("filename")
        if filename and isinstance(filename, str):
            return filename.strip() or None

    files = raw_result.get("files", [])
    if files and isinstance(files[0], dict):
        filename = files[0].get("filename")
        if filename and isinstance(filename, str):
            return filename.strip() or None

    return None


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
    "extract_top_filename_from_rag_result",
    "should_chain_doc_to_lexguard",
]
