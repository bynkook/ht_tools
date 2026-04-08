"""
Shared planner activation catalog models and common planner result models.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ActivationRuleMatch:
    all_of_groups: tuple[str, ...] = ()
    any_of_groups: tuple[str, ...] = ()
    active_category_any_of_groups: tuple[str, ...] = ()
    starts_with_any: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActivationRuleDefinition:
    rule_id: str
    provider_id: str
    action: str
    intent_label: str
    description: str
    keyword_groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    match: ActivationRuleMatch = field(default_factory=ActivationRuleMatch)
    params: dict[str, Any] = field(default_factory=dict)
    use_active_category: bool = False


@dataclass(frozen=True)
class ActivationRuleCatalog:
    rule_ref: str
    provider_id: str
    description: str
    rules: tuple[ActivationRuleDefinition, ...]


@dataclass(frozen=True)
class ActivationRuleMatchResult:
    rule_ref: str
    provider_id: str
    rule_id: str
    action: str
    intent_label: str
    description: str
    matched_keywords: tuple[str, ...]
    params: dict[str, Any]
    use_active_category: bool


@dataclass(frozen=True)
class PlannerDecisionProvenance:
    decision_source: str
    matched_rule: str
    normalized_query: str
    provider_candidates: tuple[str, ...]
    selected_provider: str
    selected_action: str
    active_category: str | None = None
    mentions: tuple[str, ...] = ()
    matched_keywords: tuple[str, ...] = ()
    reason: str | None = None
    scenario_id: str | None = None
    scenario_description: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "decision_source": self.decision_source,
            "matched_rule": self.matched_rule,
            "normalized_query": self.normalized_query,
            "provider_candidates": list(self.provider_candidates),
            "selected_provider": self.selected_provider,
            "selected_action": self.selected_action,
            "active_category": self.active_category,
            "mentions": list(self.mentions),
            "matched_keywords": list(self.matched_keywords),
            "reason": self.reason,
            "scenario_id": self.scenario_id,
            "scenario_description": self.scenario_description,
        }


@dataclass(frozen=True)
class PlannerToolPlan:
    provider: str
    action: str
    params: dict[str, Any]
    provenance: PlannerDecisionProvenance = field(
        default_factory=lambda: PlannerDecisionProvenance(
            decision_source="unknown",
            matched_rule="unknown",
            normalized_query="",
            provider_candidates=(),
            selected_provider="",
            selected_action="",
        )
    )


@dataclass(frozen=True)
class PlannerDecision:
    route: str
    clean_query: str
    mentions: tuple[str, ...] = ()
    plans: tuple[PlannerToolPlan, ...] = ()


__all__ = [
    "ActivationRuleCatalog",
    "ActivationRuleDefinition",
    "ActivationRuleMatch",
    "ActivationRuleMatchResult",
    "PlannerDecision",
    "PlannerDecisionProvenance",
    "PlannerToolPlan",
]