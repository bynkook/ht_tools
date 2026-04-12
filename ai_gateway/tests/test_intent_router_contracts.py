from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.intent_router import (
    parse_at_mentions,
    route_chat_query,
    split_mention_target,
    strip_at_mentions,
)


def test_parse_at_mentions_supports_plain_quoted_and_category_targets():
    mentions = parse_at_mentions('@spec.md @"quoted file.md" @contracts/standard.md 질문')

    assert mentions == ["spec.md", "quoted file.md", "contracts/standard.md"]


def test_strip_at_mentions_removes_targets_and_collapses_extra_whitespace():
    stripped = strip_at_mentions('@"quoted file.md"  위약금  @contracts/standard.md  조항  찾아줘')

    assert stripped == "위약금 조항 찾아줘"


def test_route_chat_query_prioritizes_manual_mentions_over_rag_mode():
    decision = route_chat_query('@spec.md 위약금 조항 찾아줘', rag_enabled=True)

    assert decision.route == "manual_mentions"
    assert decision.clean_query == "위약금 조항 찾아줘"
    assert decision.mentions == ["spec.md"]


def test_route_chat_query_preserves_catalog_match_from_shared_planner():
    decision = route_chat_query("표준계약서에서 위약금 관련 내용을 검색", rag_enabled=False)

    assert decision.route == "catalog_match"
    assert decision.clean_query == "표준계약서에서 위약금 관련 내용을 검색"
    assert decision.mentions == []


def test_route_chat_query_uses_rag_search_when_no_catalog_match_exists():
    decision = route_chat_query("오늘 날씨 어때?", rag_enabled=True)

    assert decision.route == "rag_search"
    assert decision.clean_query == "오늘 날씨 어때?"
    assert decision.mentions == []


def test_route_chat_query_falls_back_to_chat_only_without_mentions_or_rag():
    decision = route_chat_query("오늘 날씨 어때?", rag_enabled=False)

    assert decision.route == "chat_only"
    assert decision.clean_query == "오늘 날씨 어때?"
    assert decision.mentions == []


def test_split_mention_target_prefers_explicit_category_path_over_active_category():
    category, filename = split_mention_target("contracts/standard.md", active_category="safety")

    assert category == "contracts"
    assert filename == "standard.md"


def test_split_mention_target_inherits_active_category_for_plain_filename():
    category, filename = split_mention_target("standard.md", active_category="contracts")

    assert category == "contracts"
    assert filename == "standard.md"
