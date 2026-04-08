"""
Shared planner core for normalization and provider/tool decision building.
"""

from typing import TYPE_CHECKING, Any

from ..config import DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF, DOC_SEARCH_PROVIDER_ID
from .catalog import CompiledActivationCatalog, require_activation_catalog
from .models import PlannerDecision, PlannerDecisionProvenance, PlannerToolPlan
from .normalization import parse_at_mentions, split_mention_target, strip_at_mentions

if TYPE_CHECKING:
    from ..test_mode.scenario_loader import ScenarioLoader


class SharedPlannerCore:
    def __init__(
        self,
        *,
        default_provider_id: str = DOC_SEARCH_PROVIDER_ID,
        activation_rule_ref: str = DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
        activation_catalog: CompiledActivationCatalog | None = None,
    ):
        self._default_provider_id = default_provider_id
        self._activation_rule_ref = activation_rule_ref
        self._activation_catalog = activation_catalog or require_activation_catalog(activation_rule_ref)

    def plan(
        self,
        user_text: str,
        *,
        active_category: str | None = None,
        rag_enabled: bool = False,
        scenario_loader: "ScenarioLoader | None" = None,
        enable_scenarios: bool = False,
    ) -> PlannerDecision:
        stripped_text = user_text.strip()
        if not stripped_text or stripped_text.startswith("/mcp"):
            return PlannerDecision(route="chat_only", clean_query=stripped_text)

        mentions = parse_at_mentions(user_text)
        if mentions:
            return self._build_manual_mentions_decision(user_text, mentions, active_category)

        if enable_scenarios and scenario_loader is not None:
            scenario = scenario_loader.match(user_text)
            if scenario is not None:
                return self._build_scenario_decision(stripped_text, active_category, scenario)

        matches = self._activation_catalog.match(user_text, active_category=active_category)
        if matches:
            return self._build_catalog_decision(stripped_text, active_category, matches)

        if rag_enabled:
            return PlannerDecision(
                route="rag_search",
                clean_query=stripped_text,
                plans=(
                    PlannerToolPlan(
                        provider=self._default_provider_id,
                        action="search_docs_rag",
                        params=self._build_rag_params(stripped_text, active_category, max_docs=10),
                        provenance=self._build_provenance(
                            provider=self._default_provider_id,
                            action="search_docs_rag",
                            normalized_query=stripped_text,
                            decision_source="rag_enabled",
                            matched_rule="rag_enabled_default",
                            active_category=active_category,
                            reason="RAG mode forced the default provider search path.",
                        ),
                    ),
                ),
            )

        return PlannerDecision(route="chat_only", clean_query=stripped_text)

    def _build_manual_mentions_decision(
        self,
        user_text: str,
        mentions: list[str],
        active_category: str | None,
    ) -> PlannerDecision:
        clean_query = strip_at_mentions(user_text)
        plans: list[PlannerToolPlan] = []
        candidate_summary = (f"{self._default_provider_id}.search_docs_rag",)
        for raw_target in mentions:
            category, filename_filter = split_mention_target(raw_target, active_category)
            params = {
                "query": clean_query or raw_target,
                "filename_filter": filename_filter,
                "max_docs": 10,
                "snippet_chars": 1500,
            }
            if category:
                params["category"] = category
            plans.append(
                PlannerToolPlan(
                    provider=self._default_provider_id,
                    action="search_docs_rag",
                    params=params,
                    provenance=self._build_provenance(
                        provider=self._default_provider_id,
                        action="search_docs_rag",
                        normalized_query=clean_query or raw_target,
                        decision_source="manual_mentions",
                        matched_rule="manual_mentions",
                        active_category=category,
                        mentions=tuple(mentions),
                        provider_candidates=candidate_summary,
                        reason='`@...` mention syntax routed the query to targeted document search.',
                    ),
                )
            )
        return PlannerDecision(
            route="manual_mentions",
            clean_query=clean_query,
            mentions=tuple(mentions),
            plans=tuple(plans),
        )

    def _build_scenario_decision(self, stripped_text: str, active_category: str | None, scenario: Any) -> PlannerDecision:
        scenario_plans = scenario.to_tool_plans(active_category=active_category)
        candidate_summary = tuple(f"{plan.provider}.{plan.action}" for plan in scenario_plans)
        plans = tuple(
            PlannerToolPlan(
                provider=plan.provider,
                action=plan.action,
                params=plan.params,
                provenance=self._build_provenance(
                    provider=plan.provider,
                    action=plan.action,
                    normalized_query=stripped_text,
                    decision_source="scenario",
                    matched_rule=f"scenario:{scenario.scenario_id}",
                    active_category=active_category,
                    provider_candidates=candidate_summary,
                    reason=scenario.description or "Scenario rule matched the user prompt.",
                    scenario_id=scenario.scenario_id,
                    scenario_description=scenario.description,
                ),
            )
            for plan in scenario_plans
        )
        return PlannerDecision(route="scenario", clean_query=stripped_text, plans=plans)

    def _build_catalog_decision(self, stripped_text: str, active_category: str | None, matches: tuple[Any, ...]) -> PlannerDecision:
        selected = matches[0]
        candidate_summary = tuple(f"{match.provider_id}.{match.action}" for match in matches)
        params = dict(selected.params)
        if selected.action == "search_docs_rag":
            params = self._build_rag_params(
                stripped_text,
                active_category if selected.use_active_category else None,
                **params,
            )
        plan = PlannerToolPlan(
            provider=selected.provider_id,
            action=selected.action,
            params=params,
            provenance=self._build_provenance(
                provider=selected.provider_id,
                action=selected.action,
                normalized_query=stripped_text,
                decision_source="keyword_rule",
                matched_rule=selected.rule_id,
                active_category=active_category,
                matched_keywords=selected.matched_keywords,
                provider_candidates=candidate_summary,
                reason=selected.description,
            ),
        )
        return PlannerDecision(route="catalog_match", clean_query=stripped_text, plans=(plan,))

    def _build_rag_params(
        self,
        query: str,
        active_category: str | None,
        *,
        max_docs: int = 5,
        snippet_chars: int = 1500,
    ) -> dict[str, object]:
        params: dict[str, object] = {
            "query": query,
            "max_docs": max_docs,
            "snippet_chars": snippet_chars,
        }
        if active_category:
            params["category"] = active_category
        return params

    def _build_provenance(
        self,
        *,
        provider: str,
        action: str,
        normalized_query: str,
        decision_source: str,
        matched_rule: str,
        active_category: str | None = None,
        mentions: tuple[str, ...] = (),
        matched_keywords: tuple[str, ...] = (),
        provider_candidates: tuple[str, ...] | None = None,
        reason: str | None = None,
        scenario_id: str | None = None,
        scenario_description: str | None = None,
    ) -> PlannerDecisionProvenance:
        return PlannerDecisionProvenance(
            decision_source=decision_source,
            matched_rule=matched_rule,
            normalized_query=normalized_query,
            provider_candidates=provider_candidates or (f"{provider}.{action}",),
            selected_provider=provider,
            selected_action=action,
            active_category=active_category,
            mentions=mentions,
            matched_keywords=matched_keywords,
            reason=reason,
            scenario_id=scenario_id,
            scenario_description=scenario_description,
        )


__all__ = ["SharedPlannerCore"]