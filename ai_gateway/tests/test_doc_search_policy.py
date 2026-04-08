from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.doc_search_policy import (
    McpDocSearchSettings,
    build_doc_search_prompt_budget,
    normalize_doc_search_rag_params,
)


def test_normalize_doc_search_rag_params_uses_explicit_settings_defaults():
    settings = McpDocSearchSettings(max_docs=12, snippet_chars=2000)

    normalized = normalize_doc_search_rag_params(
        {"query": "회의록 요약"},
        settings=settings,
    )

    assert normalized["max_docs"] == 12
    assert normalized["snippet_chars"] == 2000


def test_build_doc_search_prompt_budget_uses_default_shape_settings():
    settings = McpDocSearchSettings(prompt_default_max_total=11, prompt_default_max_total_chars=11000)

    budget = build_doc_search_prompt_budget(
        "회의록 주요 내용을 알려줘",
        [{"filename": f"doc-{index}.md", "snippet": "x"} for index in range(20)],
        settings=settings,
    )

    assert budget.max_total == 11
    assert budget.max_total_chars == 11000
    assert budget.max_per_doc == settings.prompt_max_per_doc


def test_build_doc_search_prompt_budget_uses_file_filter_settings():
    settings = McpDocSearchSettings(
        prompt_file_filter_max_per_doc=7,
        prompt_file_filter_max_total=8,
        prompt_file_filter_max_total_chars=9000,
    )

    budget = build_doc_search_prompt_budget(
        "standard-contract.md 내용 정리",
        [{"filename": "standard-contract.md", "snippet": "x"}],
        filename_filter="standard-contract.md",
        settings=settings,
    )

    assert budget.max_per_doc == 7
    assert budget.max_total == 8
    assert budget.max_total_chars == 9000
    assert budget.min_docs_covered == 1
