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

    decision = shared_core.plan("@260330 품질 관련 내용 검색", active_category="회의록")
    route_decision = route_chat_query("@260330 품질 관련 내용 검색", rag_enabled=True)

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


def test_planner_sets_full_read_mode_when_search_and_document_issue_co_match():
    """search_docs_rag + document_issue_tool 동시 매칭 시 full_read_mode=True가 설정돼야 한다."""
    # internal_docs + lexguard 두 provider 룰을 모두 로드해야
    # search_docs_rag(internal_docs)와 document_issue_tool(lexguard)가 동시에 매칭됨.
    shared_core = SharedPlannerCore(
        activation_rule_refs=["internal_docs.default", "lexguard.default"]
    )

    decision = shared_core.plan(
        "test문서 폴더에 표준계약서 문서의 부당특약 존재 가능성을 검토해라"
    )

    assert decision.route == "catalog_match"
    actions = [p.action for p in decision.plans]
    assert "search_docs_rag" in actions
    assert "document_issue_tool" in actions

    search_plan = next(p for p in decision.plans if p.action == "search_docs_rag")
    assert search_plan.params.get("full_read_mode") is True


def test_planner_does_not_set_full_read_mode_for_snippet_only_query():
    """search_docs_rag 단독 매칭 시 full_read_mode가 설정되지 않아야 한다."""
    shared_core = SharedPlannerCore(
        activation_rule_refs=["internal_docs.default", "lexguard.default"]
    )

    decision = shared_core.plan("계약서에서 위약금 조항 찾아줘")

    assert decision.route == "catalog_match"
    search_plans = [p for p in decision.plans if p.action == "search_docs_rag"]
    assert search_plans, "search_docs_rag plan이 있어야 합니다"
    for plan in search_plans:
        assert (
            "full_read_mode" not in plan.params
            or plan.params.get("full_read_mode") is not True
        )


def test_planner_document_issue_tool_no_plantime_error():
    """document_issue_tool이 플래닝 타임에 ValueError를 발생시켜서는 안 된다."""
    shared_core = SharedPlannerCore(
        activation_rule_refs=["internal_docs.default", "lexguard.default"]
    )

    # 이 쿼리는 search_docs_rag + document_issue_tool 동시 매칭 → 과거에 ValueError 발생
    decision = shared_core.plan("표준계약서의 부당특약을 검토해라")

    assert decision.route == "catalog_match"
    actions = [p.action for p in decision.plans]
    assert "document_issue_tool" in actions
