from pathlib import Path
import sys
import tempfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.shared_planner import ActivationCatalogError, load_activation_catalogs, require_activation_catalog


def test_internal_docs_activation_catalog_loads_successfully():
    catalog = require_activation_catalog("internal_docs.default")

    assert catalog.catalog.provider_id == "internal_docs"
    assert [rule.rule_id for rule in catalog.catalog.rules] == [
        "category_listing_keywords",
        "doc_search_target + search_action",
    ]


def test_internal_docs_activation_catalog_matches_category_listing_query():
    catalog = require_activation_catalog("internal_docs.default")

    matches = catalog.match("문서 카테고리 목록 보여줘")

    assert len(matches) == 2
    assert matches[0].rule_id == "category_listing_keywords"
    assert matches[0].action == "list_categories_detail"
    assert "카테고리" in matches[0].matched_keywords


def test_internal_docs_activation_catalog_matches_doc_search_query():
    catalog = require_activation_catalog("internal_docs.default")

    matches = catalog.match("표준계약서에서 위약금 관련 내용을 검색")

    doc_search = next(match for match in matches if match.rule_id == "doc_search_target + search_action")
    assert doc_search.action == "search_docs_rag"
    assert doc_search.params == {"max_docs": 5, "snippet_chars": 1500}
    assert "표준계약서" in doc_search.matched_keywords
    assert "검색" in doc_search.matched_keywords


def test_internal_docs_activation_catalog_uses_active_category_context_hint():
    catalog = require_activation_catalog("internal_docs.default")

    matches = catalog.match("위약금 관련 내용을 검색", active_category="test문서")

    doc_search = next(match for match in matches if match.rule_id == "doc_search_target + search_action")
    assert doc_search.use_active_category is True
    assert "위약금" in doc_search.matched_keywords
    assert "검색" in doc_search.matched_keywords


def test_activation_catalog_loader_fails_fast_for_unknown_provider_reference():
    with tempfile.TemporaryDirectory() as temp_dir:
        rules_dir = Path(temp_dir)
        invalid_catalog = rules_dir / "invalid.json"
        invalid_catalog.write_text(
            '{"rule_ref":"unknown.default","provider_id":"legal_cases","rules":[{"id":"rule-1","intent_label":"x","action":"y"}]}',
            encoding="utf-8",
        )

        with pytest.raises(ActivationCatalogError, match="unknown provider"):
            load_activation_catalogs(rules_dir=rules_dir)