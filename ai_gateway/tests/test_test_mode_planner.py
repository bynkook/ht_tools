from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.test_mode.planner import DeterministicToolPlanner


class StubScenarioLoader:
    def match(self, user_text: str):
        return None


class ScenarioMatch:
    scenario_id = "fixture-search"
    description = "fixture override"

    def to_tool_plans(self, *, active_category=None):
        params = {"query": "fixture query", "max_docs": 10, "snippet_chars": 1500}
        if active_category:
            params["category"] = active_category
        return [
            type(
                "ScenarioPlan",
                (),
                {
                    "provider": "internal_docs",
                    "action": "search_docs_rag",
                    "params": params,
                },
            )()
        ]


class ScenarioLoaderWithMatch:
    def match(self, user_text: str):
        return ScenarioMatch()


def create_planner(
    *,
    scenario_loader=None,
    enable_scenario_overrides: bool = False,
) -> DeterministicToolPlanner:
    return DeterministicToolPlanner(
        scenario_loader or StubScenarioLoader(),
        enable_scenario_overrides=enable_scenario_overrides,
    )


def test_doc_search_prompt_routes_to_search_tool():
    planner = create_planner()

    plans = planner.plan("위약금 관련 내용을 검색")

    assert len(plans) == 1
    assert plans[0].provider == "internal_docs"
    assert plans[0].action == "search_docs_rag"
    assert plans[0].params["query"] == "위약금 관련 내용을 검색"
    assert plans[0].provenance.decision_source == "keyword_rule"
    assert plans[0].provenance.matched_rule == "doc_search_target + search_action"
    assert "관련" in plans[0].provenance.matched_keywords
    assert "내용" in plans[0].provenance.matched_keywords
    assert "검색" in plans[0].provenance.matched_keywords


def test_meeting_notes_folder_query_routes_to_search_tool_with_dynamic_provider_categories():
    planner = create_planner()

    plans = planner.plan(
        "회의록 폴더에서 가장 최근 회의록을 검색해서 주요 내용을 요약해줘",
        provider_categories={"internal_docs": ("회의록",)},
    )

    assert len(plans) == 1
    assert plans[0].provider == "internal_docs"
    assert plans[0].action == "search_docs_rag"
    assert plans[0].params["query"] == "회의록 폴더에서 가장 최근 회의록을 검색해서 주요 내용을 요약해줘"
    assert plans[0].params["category"] == "회의록"
    assert "회의록" in plans[0].provenance.matched_keywords
    assert "검색" in plans[0].provenance.matched_keywords


def test_dynamic_category_query_with_latest_summary_language_routes_to_search_tool():
    planner = create_planner()

    plans = planner.plan(
        "회의록 최신 주요 내용 알려줘",
        provider_categories={"internal_docs": ("회의록",)},
    )

    assert len(plans) == 1
    assert plans[0].action == "search_docs_rag"
    assert plans[0].params["category"] == "회의록"
    assert plans[0].params["max_docs"] == 10
    assert plans[0].params["snippet_chars"] == 1500
    assert "회의록" in plans[0].provenance.matched_keywords
    assert "최신" in plans[0].provenance.matched_keywords


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


def test_scenario_loader_is_not_used_by_default():
    planner = create_planner(scenario_loader=ScenarioLoaderWithMatch())

    decision = planner.decide("위약금 관련 내용을 검색", active_category="회의록")

    assert decision.route == "catalog_match"
    assert decision.plans[0].provenance.decision_source == "keyword_rule"


def test_scenario_loader_requires_explicit_override_flag():
    planner = create_planner(
        scenario_loader=ScenarioLoaderWithMatch(),
        enable_scenario_overrides=True,
    )

    decision = planner.decide("위약금 관련 내용을 검색", active_category="회의록")

    assert decision.route == "scenario"
    assert decision.plans[0].provenance.decision_source == "scenario"
    assert decision.plans[0].params["query"] == "fixture query"
