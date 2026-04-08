"""
Scenario loader for deterministic MCP Test Mode override fixtures.
"""

from dataclasses import dataclass, field
from json import load
from pathlib import Path
from typing import Any

from ..config import McpHostSettings


@dataclass(frozen=True)
class ScenarioToolPlanDefinition:
    provider: str
    action: str
    params: dict[str, Any] = field(default_factory=dict)
    use_active_category: bool = False


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_id: str
    description: str
    contains_any: tuple[str, ...] = ()
    starts_with_any: tuple[str, ...] = ()
    plans: tuple[ScenarioToolPlanDefinition, ...] = ()

    def matches(self, user_text: str) -> bool:
        lowered_text = user_text.strip().lower()
        if not lowered_text:
            return False

        if self.starts_with_any and any(lowered_text.startswith(prefix) for prefix in self.starts_with_any):
            return True

        if self.contains_any and any(keyword in lowered_text for keyword in self.contains_any):
            return True

        return False

    def to_tool_plans(self, *, active_category: str | None) -> tuple[ScenarioToolPlanDefinition, ...]:
        resolved_plans: list[ScenarioToolPlanDefinition] = []
        for plan in self.plans:
            params = dict(plan.params)
            if plan.use_active_category and active_category and "category" not in params:
                params["category"] = active_category
            resolved_plans.append(
                ScenarioToolPlanDefinition(
                    provider=plan.provider,
                    action=plan.action,
                    params=params,
                    use_active_category=plan.use_active_category,
                )
            )
        return tuple(resolved_plans)


class ScenarioLoader:
    def __init__(self, scenario_path: Path):
        self._scenario_path = scenario_path
        self._cached_scenarios: tuple[ScenarioDefinition, ...] | None = None

    @classmethod
    def from_settings(cls, settings: McpHostSettings) -> "ScenarioLoader":
        return cls(settings.test_mode_scenario_path)

    def load(self) -> tuple[ScenarioDefinition, ...]:
        if self._cached_scenarios is not None:
            return self._cached_scenarios

        with open(self._scenario_path, "r", encoding="utf-8") as handle:
            raw_data = load(handle)

        raw_scenarios = raw_data.get("scenarios", []) if isinstance(raw_data, dict) else []
        scenarios: list[ScenarioDefinition] = []
        for index, item in enumerate(raw_scenarios):
            match_config = item.get("match", {})
            plans = tuple(
                ScenarioToolPlanDefinition(
                    provider=plan["provider"],
                    action=plan["action"],
                    params=plan.get("params", {}),
                    use_active_category=plan.get("use_active_category", False),
                )
                for plan in item.get("plans", [])
            )
            scenarios.append(
                ScenarioDefinition(
                    scenario_id=item.get("id", f"scenario-{index + 1}"),
                    description=item.get("description", ""),
                    contains_any=tuple(keyword.lower() for keyword in match_config.get("contains_any", [])),
                    starts_with_any=tuple(keyword.lower() for keyword in match_config.get("starts_with_any", [])),
                    plans=plans,
                )
            )

        self._cached_scenarios = tuple(scenarios)
        return self._cached_scenarios

    def match(self, user_text: str) -> ScenarioDefinition | None:
        for scenario in self.load():
            if scenario.matches(user_text):
                return scenario
        return None


__all__ = ["ScenarioDefinition", "ScenarioLoader", "ScenarioToolPlanDefinition"]
