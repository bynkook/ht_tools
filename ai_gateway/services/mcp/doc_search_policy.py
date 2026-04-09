"""
Shared doc-search defaults for retrieval requests and prompt assembly.
"""

from dataclasses import dataclass
from typing import Any, Mapping

_DOC_SEARCH_PROCEDURAL_KEYWORDS = ("절차", "단계", "방법", "순서", "비교", "차이", "예외", "주의")


@dataclass(frozen=True)
class DocSearchPromptBudget:
    max_per_doc: int
    max_total: int
    max_total_chars: int
    min_docs_covered: int


@dataclass(frozen=True)
class McpDocSearchSettings:
    max_docs: int = 10
    snippet_chars: int = 1500
    unscoped_fanout_enabled: bool = True
    unscoped_fanout_per_category_docs: int = 3
    unscoped_fanout_category_limit: int = 0
    prompt_max_per_doc: int = 3
    prompt_compact_max_total: int = 6
    prompt_compact_max_total_chars: int = 6000
    prompt_default_max_total: int = 9
    prompt_default_max_total_chars: int = 9000
    prompt_expand_max_total: int = 12
    prompt_expand_max_total_chars: int = 12000
    prompt_file_filter_max_per_doc: int = 12
    prompt_file_filter_max_total: int = 12
    prompt_file_filter_max_total_chars: int = 14000
    prompt_file_fallback_max_files: int = 4


DEFAULT_DOC_SEARCH_SETTINGS = McpDocSearchSettings()
DOC_SEARCH_DEFAULT_MAX_DOCS = DEFAULT_DOC_SEARCH_SETTINGS.max_docs
DOC_SEARCH_DEFAULT_SNIPPET_CHARS = DEFAULT_DOC_SEARCH_SETTINGS.snippet_chars
DOC_SEARCH_FILE_FALLBACK_MAX_FILES = DEFAULT_DOC_SEARCH_SETTINGS.prompt_file_fallback_max_files


def normalize_doc_search_rag_params(
    params: Mapping[str, Any] | None = None,
    *,
    query: str | None = None,
    category: str | None = None,
    filename_filter: str | None = None,
    settings: McpDocSearchSettings | None = None,
) -> dict[str, Any]:
    resolved_settings = settings or DEFAULT_DOC_SEARCH_SETTINGS
    normalized = dict(params or {})
    if query is not None:
        normalized["query"] = query
    if category:
        normalized["category"] = category
    if filename_filter:
        normalized["filename_filter"] = filename_filter

    max_docs = normalized.get("max_docs")
    snippet_chars = normalized.get("snippet_chars")
    normalized["max_docs"] = int(max_docs) if max_docs is not None else resolved_settings.max_docs
    normalized["snippet_chars"] = int(snippet_chars) if snippet_chars is not None else resolved_settings.snippet_chars
    return normalized


def build_doc_search_prompt_budget(
    query: str,
    snippets: list[dict[str, Any]],
    *,
    filename_filter: str | None = None,
    settings: McpDocSearchSettings | None = None,
) -> DocSearchPromptBudget:
    resolved_settings = settings or DEFAULT_DOC_SEARCH_SETTINGS
    if filename_filter:
        return DocSearchPromptBudget(
            max_per_doc=resolved_settings.prompt_file_filter_max_per_doc,
            max_total=resolved_settings.prompt_file_filter_max_total,
            max_total_chars=resolved_settings.prompt_file_filter_max_total_chars,
            min_docs_covered=1,
        )

    query_lower = query.lower()
    raw_tokens = [token for token in query.split() if token.strip()]
    expand_hint = any(keyword in query_lower for keyword in _DOC_SEARCH_PROCEDURAL_KEYWORDS)
    compact_hint = len(raw_tokens) <= 2 and len(query.strip()) <= 20 and not expand_hint
    unique_docs = len(
        {
            (snippet.get("category"), snippet.get("filename", ""))
            for snippet in snippets
            if snippet.get("filename")
        }
    )

    if compact_hint:
        max_total = resolved_settings.prompt_compact_max_total
        max_total_chars = resolved_settings.prompt_compact_max_total_chars
    elif expand_hint:
        max_total = resolved_settings.prompt_expand_max_total
        max_total_chars = resolved_settings.prompt_expand_max_total_chars
    else:
        max_total = resolved_settings.prompt_default_max_total
        max_total_chars = resolved_settings.prompt_default_max_total_chars

    return DocSearchPromptBudget(
        max_per_doc=resolved_settings.prompt_max_per_doc,
        max_total=max_total,
        max_total_chars=max_total_chars,
        min_docs_covered=min(unique_docs, max(3, min(6, max_total))),
    )


__all__ = [
    "DOC_SEARCH_DEFAULT_MAX_DOCS",
    "DOC_SEARCH_DEFAULT_SNIPPET_CHARS",
    "DOC_SEARCH_FILE_FALLBACK_MAX_FILES",
    "DEFAULT_DOC_SEARCH_SETTINGS",
    "DocSearchPromptBudget",
    "McpDocSearchSettings",
    "build_doc_search_prompt_budget",
    "normalize_doc_search_rag_params",
]
