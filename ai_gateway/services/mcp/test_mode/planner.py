"""
Deterministic tool planner for MCP Test Mode.
"""

from collections.abc import Callable

from ..config import DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF, DOC_SEARCH_PROVIDER_ID, McpServerConfig
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
        provider_config_resolver: Callable[[str], McpServerConfig] | None = None,
        default_provider_id: str = DOC_SEARCH_PROVIDER_ID,
    ):
        self._scenario_loader = scenario_loader
        self._provider_config_resolver = provider_config_resolver
        self._default_provider_id = default_provider_id
        self._planner_cache: dict[str, SharedPlannerCore] = {}
        self._planner_core = planner_core or SharedPlannerCore(default_provider_id=default_provider_id)
        self._planner_cache[default_provider_id] = self._planner_core

    def _planner_for_provider(self, provider_id: str | None) -> SharedPlannerCore:
        resolved_provider_id = provider_id or self._default_provider_id
        cached = self._planner_cache.get(resolved_provider_id)
        if cached is not None:
            return cached
        if self._provider_config_resolver is None:
            return self._planner_core
        provider_config = self._provider_config_resolver(resolved_provider_id)
        planner_core = SharedPlannerCore(
            default_provider_id=resolved_provider_id,
            activation_rule_ref=provider_config.activation_rule_ref or DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
        )
        self._planner_cache[resolved_provider_id] = planner_core
        return planner_core

    def decide(
        self,
        user_text: str,
        active_category: str | None = None,
        *,
        rag_enabled: bool = False,
        provider_id: str | None = None,
    ) -> ToolDecision:
        return self._planner_for_provider(provider_id).plan(
            user_text,
            active_category=active_category,
            rag_enabled=rag_enabled,
            scenario_loader=self._scenario_loader,
            enable_scenarios=True,
        )

    def plan(
        self,
        user_text: str,
        active_category: str | None = None,
        *,
        rag_enabled: bool = False,
        provider_id: str | None = None,
    ) -> list[ToolPlan]:
        return list(
            self.decide(
                user_text,
                active_category=active_category,
                rag_enabled=rag_enabled,
                provider_id=provider_id,
            ).plans
        )


__all__ = ["DeterministicToolPlanner", "ToolDecision", "ToolDecisionProvenance", "ToolPlan"]