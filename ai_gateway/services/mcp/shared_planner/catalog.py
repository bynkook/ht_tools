"""
Shared planner activation rule catalog loader and validator.
"""

from json import load
from pathlib import Path
from typing import Iterable

from ..providers import list_provider_manifests
from .models import (
    ActivationRuleCatalog,
    ActivationRuleDefinition,
    ActivationRuleMatch,
    ActivationRuleMatchResult,
)

RULES_DIR = Path(__file__).resolve().parent / "rules"


class ActivationCatalogError(ValueError):
    pass


class CompiledActivationCatalog:
    def __init__(self, catalog: ActivationRuleCatalog):
        self.catalog = catalog

    def match(self, user_text: str, active_category: str | None = None) -> tuple[ActivationRuleMatchResult, ...]:
        lowered_text = user_text.strip().lower()
        if not lowered_text:
            return ()

        matches: list[ActivationRuleMatchResult] = []
        for rule in self.catalog.rules:
            matched_keywords = _match_rule(rule, lowered_text, active_category)
            if matched_keywords is None:
                continue
            matches.append(
                ActivationRuleMatchResult(
                    rule_ref=self.catalog.rule_ref,
                    provider_id=rule.provider_id,
                    rule_id=rule.rule_id,
                    action=rule.action,
                    intent_label=rule.intent_label,
                    description=rule.description,
                    matched_keywords=matched_keywords,
                    params=dict(rule.params),
                    use_active_category=rule.use_active_category,
                )
            )
        return tuple(matches)


def _normalize_keywords(values: object, *, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, list):
        raise ActivationCatalogError(f"Activation catalog field '{field_name}' must be a list")
    normalized: list[str] = []
    for value in values:
        keyword = str(value).strip().lower()
        if not keyword:
            raise ActivationCatalogError(f"Activation catalog field '{field_name}' cannot contain blank keywords")
        normalized.append(keyword)
    return tuple(normalized)


def _normalize_match(match_config: object) -> ActivationRuleMatch:
    if match_config is None:
        return ActivationRuleMatch()
    if not isinstance(match_config, dict):
        raise ActivationCatalogError("Activation catalog match config must be an object")
    return ActivationRuleMatch(
        all_of_groups=_normalize_keywords(match_config.get("all_of_groups"), field_name="all_of_groups"),
        any_of_groups=_normalize_keywords(match_config.get("any_of_groups"), field_name="any_of_groups"),
        active_category_any_of_groups=_normalize_keywords(
            match_config.get("active_category_any_of_groups"),
            field_name="active_category_any_of_groups",
        ),
        starts_with_any=_normalize_keywords(match_config.get("starts_with_any"), field_name="starts_with_any"),
    )


def _normalize_keyword_groups(raw_groups: object) -> dict[str, tuple[str, ...]]:
    if raw_groups is None:
        return {}
    if not isinstance(raw_groups, dict):
        raise ActivationCatalogError("Activation catalog keyword_groups must be an object")

    normalized_groups: dict[str, tuple[str, ...]] = {}
    for group_name, keywords in raw_groups.items():
        normalized_name = str(group_name).strip()
        if not normalized_name:
            raise ActivationCatalogError("Activation catalog keyword group names cannot be blank")
        normalized_groups[normalized_name] = _normalize_keywords(keywords, field_name=f"keyword_groups.{normalized_name}")
    return normalized_groups


def _validate_group_refs(rule: ActivationRuleDefinition) -> None:
    declared_groups = set(rule.keyword_groups)
    referenced_groups = set(rule.match.all_of_groups) | set(rule.match.any_of_groups) | set(rule.match.active_category_any_of_groups)
    unknown_groups = referenced_groups - declared_groups
    if unknown_groups:
        names = ", ".join(sorted(unknown_groups))
        raise ActivationCatalogError(
            f"Activation catalog rule '{rule.rule_id}' references unknown keyword groups: {names}"
        )


def _build_rule(provider_id: str, raw_rule: object, *, index: int) -> ActivationRuleDefinition:
    if not isinstance(raw_rule, dict):
        raise ActivationCatalogError(f"Activation catalog rule #{index + 1} must be an object")

    rule_id = str(raw_rule.get("id", f"rule-{index + 1}")).strip()
    if not rule_id:
        raise ActivationCatalogError("Activation catalog rule id cannot be blank")

    action = str(raw_rule.get("action", "")).strip()
    if not action:
        raise ActivationCatalogError(f"Activation catalog rule '{rule_id}' is missing action")

    intent_label = str(raw_rule.get("intent_label", "")).strip()
    if not intent_label:
        raise ActivationCatalogError(f"Activation catalog rule '{rule_id}' is missing intent_label")

    rule = ActivationRuleDefinition(
        rule_id=rule_id,
        provider_id=provider_id,
        action=action,
        intent_label=intent_label,
        description=str(raw_rule.get("description", "")).strip(),
        keyword_groups=_normalize_keyword_groups(raw_rule.get("keyword_groups")),
        match=_normalize_match(raw_rule.get("match")),
        params=dict(raw_rule.get("params", {})) if isinstance(raw_rule.get("params"), dict) else {},
        use_active_category=bool(raw_rule.get("use_active_category", False)),
    )
    _validate_group_refs(rule)
    return rule


def _build_catalog(raw_data: object, *, source: Path, registered_provider_ids: set[str]) -> ActivationRuleCatalog:
    if not isinstance(raw_data, dict):
        raise ActivationCatalogError(f"Activation catalog must be an object: {source}")

    rule_ref = str(raw_data.get("rule_ref", "")).strip()
    if not rule_ref:
        raise ActivationCatalogError(f"Activation catalog is missing rule_ref: {source}")

    provider_id = str(raw_data.get("provider_id", "")).strip()
    if not provider_id:
        raise ActivationCatalogError(f"Activation catalog is missing provider_id: {source}")
    if provider_id not in registered_provider_ids:
        raise ActivationCatalogError(f"Activation catalog references unknown provider '{provider_id}': {source}")

    raw_rules = raw_data.get("rules", [])
    if not isinstance(raw_rules, list) or not raw_rules:
        raise ActivationCatalogError(f"Activation catalog must declare at least one rule: {source}")

    rules = tuple(_build_rule(provider_id, raw_rule, index=index) for index, raw_rule in enumerate(raw_rules))
    rule_ids = [rule.rule_id for rule in rules]
    if len(set(rule_ids)) != len(rule_ids):
        raise ActivationCatalogError(f"Activation catalog contains duplicate rule ids: {source}")

    return ActivationRuleCatalog(
        rule_ref=rule_ref,
        provider_id=provider_id,
        description=str(raw_data.get("description", "")).strip(),
        rules=rules,
    )


def _registered_provider_ids(provider_ids: Iterable[str] | None = None) -> set[str]:
    if provider_ids is not None:
        return {provider_id for provider_id in provider_ids}
    return {manifest.provider_id for manifest in list_provider_manifests()}


def load_activation_catalogs(
    *,
    rules_dir: Path | None = None,
    provider_ids: Iterable[str] | None = None,
) -> dict[str, CompiledActivationCatalog]:
    catalog_dir = rules_dir or RULES_DIR
    registered_provider_ids = _registered_provider_ids(provider_ids)
    catalogs: dict[str, CompiledActivationCatalog] = {}

    for path in sorted(catalog_dir.glob("*.json")):
        with open(path, "r", encoding="utf-8") as handle:
            raw_data = load(handle)
        catalog = _build_catalog(raw_data, source=path, registered_provider_ids=registered_provider_ids)
        if catalog.rule_ref in catalogs:
            raise ActivationCatalogError(f"Duplicate activation catalog rule_ref: {catalog.rule_ref}")
        catalogs[catalog.rule_ref] = CompiledActivationCatalog(catalog)

    return catalogs


def require_activation_catalog(
    rule_ref: str,
    *,
    rules_dir: Path | None = None,
    provider_ids: Iterable[str] | None = None,
) -> CompiledActivationCatalog:
    catalogs = load_activation_catalogs(rules_dir=rules_dir, provider_ids=provider_ids)
    if rule_ref not in catalogs:
        raise ActivationCatalogError(f"Activation catalog is not registered: {rule_ref}")
    return catalogs[rule_ref]


def _match_rule(
    rule: ActivationRuleDefinition,
    lowered_text: str,
    active_category: str | None,
) -> tuple[str, ...] | None:
    if rule.match.starts_with_any and not any(lowered_text.startswith(prefix) for prefix in rule.match.starts_with_any):
        return None

    matches_by_group = {
        group_name: tuple(keyword for keyword in keywords if keyword in lowered_text)
        for group_name, keywords in rule.keyword_groups.items()
    }

    if any(not matches_by_group[group_name] for group_name in rule.match.all_of_groups):
        return None

    positive_any_groups = tuple(
        matches_by_group[group_name]
        for group_name in rule.match.any_of_groups
        if matches_by_group[group_name]
    )
    positive_active_groups = tuple(
        matches_by_group[group_name]
        for group_name in rule.match.active_category_any_of_groups
        if active_category and matches_by_group[group_name]
    )

    if (rule.match.any_of_groups or rule.match.active_category_any_of_groups) and not (
        positive_any_groups or positive_active_groups
    ):
        return None

    matched_keywords: list[str] = []
    for group_name in rule.match.all_of_groups + rule.match.any_of_groups + rule.match.active_category_any_of_groups:
        for keyword in matches_by_group.get(group_name, ()):
            if keyword not in matched_keywords:
                matched_keywords.append(keyword)
    return tuple(matched_keywords)


__all__ = [
    "ActivationCatalogError",
    "CompiledActivationCatalog",
    "RULES_DIR",
    "load_activation_catalogs",
    "require_activation_catalog",
]