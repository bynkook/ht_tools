from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.intent_router import route_chat_query
from services.mcp.shared_planner import SharedPlannerCore
from services.mcp.test_mode.planner import DeterministicToolPlanner


class StubScenarioLoader:
    def match(self, user_text: str):
        return None


def test_shared_planner_selects_same_doc_search_plan_used_by_test_mode_wrapper():
    shared_core = SharedPlannerCore()
    planner = DeterministicToolPlanner(StubScenarioLoader(), planner_core=shared_core)

    decision = shared_core.plan("표준계약서에서 위약금 관련 내용을 검색")
    plans = planner.plan("표준계약서에서 위약금 관련 내용을 검색")

    assert decision.route == "catalog_match"
    assert decision.plans[0].provider == "internal_docs"
    assert decision.plans[0].action == "search_docs_rag"
    assert plans[0].provider == decision.plans[0].provider
    assert plans[0].action == decision.plans[0].action
    assert plans[0].provenance.matched_rule == "doc_search_target + search_action"


def test_shared_planner_preserves_targeted_mentions_for_wrappers():
    shared_core = SharedPlannerCore()

    decision = shared_core.plan('@260330 품질 관련 내용 검색', active_category="회의록")
    route_decision = route_chat_query('@260330 품질 관련 내용 검색', rag_enabled=True)

    assert decision.route == "manual_mentions"
    assert decision.mentions == ("260330",)
    assert decision.plans[0].params["filename_filter"] == "260330"
    assert decision.plans[0].params["category"] == "회의록"
    assert route_decision.route == "manual_mentions"
    assert route_decision.mentions == ["260330"]


def test_shared_planner_keeps_normal_wrapper_rag_toggle_behavior():
    shared_core = SharedPlannerCore()

    decision = shared_core.plan("오늘 날씨 어때?", rag_enabled=True)
    route_decision = route_chat_query("오늘 날씨 어때?", rag_enabled=True)

    assert decision.route == "rag_search"
    assert decision.plans[0].provider == "internal_docs"
    assert decision.plans[0].action == "search_docs_rag"
    assert route_decision.route == "rag_search"