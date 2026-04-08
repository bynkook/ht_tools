"""
Deterministic tool planner for MCP Test Mode.
"""

from ..config import DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF, DOC_SEARCH_PROVIDER_ID, McpHostSettings, McpServerConfig
from ..shared_planner.core import SharedPlannerCore
from ..shared_planner.models import PlannerDecision, PlannerDecisionProvenance, PlannerToolPlan
from .scenario_loader import ScenarioLoader

ToolDecision = PlannerDecision
ToolDecisionProvenance = PlannerDecisionProvenance
ToolPlan = PlannerToolPlan


class DeterministicToolPlanner:
    def __init__(
        self,
        scenario_loader: ScenarioLoader,
        planner_core: SharedPlannerCore | None = None,
        provider_configs: dict[str, McpServerConfig] | None = None,
        default_provider_id: str = DOC_SEARCH_PROVIDER_ID,
        enable_scenario_overrides: bool = False,
        host_settings: McpHostSettings | None = None,
    ):
        self._scenario_loader = scenario_loader
        self._default_provider_id = default_provider_id
        self._enable_scenario_overrides = enable_scenario_overrides
        activation_rule_refs = tuple(
            dict.fromkeys(
                config.activation_rule_ref or DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF
                for config in (provider_configs or {}).values()
                if config.enabled
            )
        )
        self._planner_core = planner_core or SharedPlannerCore(
            default_provider_id=default_provider_id,
            activation_rule_ref=activation_rule_refs[0] if activation_rule_refs else DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
            activation_rule_refs=activation_rule_refs or None,
            doc_search_settings=host_settings.doc_search if host_settings is not None else None,
        )

    def decide(
        self,
        user_text: str,
        active_category: str | None = None,
        *,
        rag_enabled: bool = False,
        provider_id: str | None = None,
        provider_categories: dict[str, tuple[str, ...]] | None = None,
    ) -> ToolDecision:
        return self._planner_core.plan(
            user_text,
            active_category=active_category,
            rag_enabled=rag_enabled,
            scenario_loader=self._scenario_loader,
            enable_scenarios=self._enable_scenario_overrides,
            provider_hint=provider_id,
            provider_categories=provider_categories,
        )

    def plan(
        self,
        user_text: str,
        active_category: str | None = None,
        *,
        rag_enabled: bool = False,
        provider_id: str | None = None,
        provider_categories: dict[str, tuple[str, ...]] | None = None,
    ) -> list[ToolPlan]:
        return list(
            self.decide(
                user_text,
                active_category=active_category,
                rag_enabled=rag_enabled,
                provider_id=provider_id,
                provider_categories=provider_categories,
            ).plans
        )


__all__ = ["DeterministicToolPlanner", "ToolDecision", "ToolDecisionProvenance", "ToolPlan"]
