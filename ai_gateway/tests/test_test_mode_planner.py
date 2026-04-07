from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.test_mode.planner import DeterministicToolPlanner


class StubScenarioLoader:
    def match(self, user_text: str):
        return None


def create_planner() -> DeterministicToolPlanner:
    return DeterministicToolPlanner(StubScenarioLoader())


def test_doc_search_prompt_routes_to_search_tool():
    planner = create_planner()

    plans = planner.plan("표준계약서에서 위약금 관련 내용을 검색")

    assert len(plans) == 1
    assert plans[0].provider == "internal_docs"
    assert plans[0].action == "search_docs_rag"
    assert plans[0].params["query"] == "표준계약서에서 위약금 관련 내용을 검색"
    assert plans[0].provenance.decision_source == "keyword_rule"
    assert plans[0].provenance.matched_rule == "doc_search_target + search_action"
    assert "표준계약서" in plans[0].provenance.matched_keywords
    assert "검색" in plans[0].provenance.matched_keywords


def test_active_category_search_without_explicit_document_keyword_routes_to_search_tool():
    planner = create_planner()

    plans = planner.plan("위약금 관련 내용을 검색", active_category="test문서")

    assert len(plans) == 1
    assert plans[0].action == "search_docs_rag"
    assert plans[0].params["category"] == "test문서"
    assert plans[0].provenance.active_category == "test문서"


def test_category_listing_request_routes_to_category_tool():
    planner = create_planner()

    plans = planner.plan("문서 카테고리 목록 보여줘")

    assert len(plans) == 1
    assert plans[0].action == "list_categories_detail"
    assert plans[0].provenance.matched_rule == "category_listing_keywords"


def test_general_chat_prompt_does_not_route_to_tool():
    planner = create_planner()

    plans = planner.plan("오늘 날씨 어때?")

    assert plans == []


def test_manual_mentions_route_captures_decision_provenance():
    planner = create_planner()

    plans = planner.plan('@"test문서/standard-contract.md" 위약금 조항 찾아줘', active_category="기본문서")

    assert len(plans) == 1
    assert plans[0].action == "search_docs_rag"
    assert plans[0].provenance.decision_source == "manual_mentions"
    assert plans[0].provenance.matched_rule == "manual_mentions"
    assert plans[0].provenance.active_category == "test문서"
    assert plans[0].provenance.mentions == ("test문서/standard-contract.md",)
