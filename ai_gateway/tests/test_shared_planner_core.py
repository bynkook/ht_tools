from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.intent_router import route_chat_query
from services.mcp.shared_planner import ActivationRuleMatchResult, SharedPlannerCore
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


def test_shared_planner_routes_meeting_notes_folder_query_using_dynamic_provider_categories():
    shared_core = SharedPlannerCore()

    decision = shared_core.plan(
        "회의록 폴더에서 가장 최근 회의록을 검색해서 주요 내용을 요약해줘",
        provider_categories={"internal_docs": ("회의록",)},
    )

    assert decision.route == "catalog_match"
    assert decision.plans[0].provider == "internal_docs"
    assert decision.plans[0].action == "search_docs_rag"
    assert decision.plans[0].params["category"] == "회의록"


def test_shared_planner_emits_one_plan_per_matching_provider_for_multi_provider_queries():
    activation_catalog = SimpleNamespace(
        match=lambda *args, **kwargs: (
            ActivationRuleMatchResult(
                rule_ref="internal_docs.default",
                provider_id="internal_docs",
                rule_id="docs-search",
                action="search_docs_rag",
                intent_label="docs-search",
                description="docs search",
                priority=10,
                matched_keywords=("위약금", "검색"),
                matched_categories=(),
                params={"max_docs": 5, "snippet_chars": 1500},
                use_active_category=True,
            ),
            ActivationRuleMatchResult(
                rule_ref="legal_cases.default",
                provider_id="legal_cases",
                rule_id="legal-search",
                action="search_docs_rag",
                intent_label="legal-search",
                description="legal search",
                priority=20,
                matched_keywords=("위약금", "검색"),
                matched_categories=(),
                params={"max_docs": 3, "snippet_chars": 1200},
                use_active_category=False,
            ),
        )
    )
    shared_core = SharedPlannerCore(activation_catalog=activation_catalog)

    decision = shared_core.plan("위약금 관련 내용을 검색", active_category="계약문서")

    assert decision.route == "catalog_match"
    assert [(plan.provider, plan.action) for plan in decision.plans] == [
        ("internal_docs", "search_docs_rag"),
        ("legal_cases", "search_docs_rag"),
    ]
    assert decision.plans[0].params["category"] == "계약문서"
    assert "category" not in decision.plans[1].params
