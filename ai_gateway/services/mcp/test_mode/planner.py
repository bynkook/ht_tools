"""
Deterministic tool planner for MCP Test Mode.
"""

from dataclasses import dataclass, field

from ..intent_router import parse_at_mentions, split_mention_target, strip_at_mentions
from .scenario_loader import ScenarioLoader

DOC_CATEGORY_KEYWORDS = ("카테고리", "category", "문서 목록")
DOC_SEARCH_TARGET_KEYWORDS = (
    "문서",
    "계약서",
    "표준계약서",
    "자료",
    "파일",
    "조항",
    "약관",
    "규정",
    "기준",
    "본문",
)
DOC_SEARCH_ACTION_KEYWORDS = (
    "검색",
    "찾",
    "조회",
    "확인",
    "알려",
    "보여",
    "look up",
    "search",
    "find",
)
DOC_SEARCH_CONTEXT_HINTS = (
    "관련",
    "내용",
    "조항",
    "항목",
    "본문",
    "위약금",
)


@dataclass(frozen=True)
class ToolDecisionProvenance:
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

    def to_payload(self) -> dict:
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
class ToolPlan:
    provider: str
    action: str
    params: dict
    provenance: ToolDecisionProvenance = field(
        default_factory=lambda: ToolDecisionProvenance(
            decision_source="unknown",
            matched_rule="unknown",
            normalized_query="",
            provider_candidates=(),
            selected_provider="",
            selected_action="",
        )
    )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _find_matched_keywords(text: str, keywords: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(keyword for keyword in keywords if keyword in text)


def _build_provenance(
    *,
    provider: str,
    action: str,
    normalized_query: str,
    decision_source: str,
    matched_rule: str,
    active_category: str | None = None,
    mentions: tuple[str, ...] = (),
    matched_keywords: tuple[str, ...] = (),
    reason: str | None = None,
    scenario_id: str | None = None,
    scenario_description: str | None = None,
) -> ToolDecisionProvenance:
    return ToolDecisionProvenance(
        decision_source=decision_source,
        matched_rule=matched_rule,
        normalized_query=normalized_query,
        provider_candidates=(f"{provider}.{action}",),
        selected_provider=provider,
        selected_action=action,
        active_category=active_category,
        mentions=mentions,
        matched_keywords=matched_keywords,
        reason=reason,
        scenario_id=scenario_id,
        scenario_description=scenario_description,
    )


def _build_search_docs_plan(
    user_text: str,
    active_category: str | None = None,
    *,
    provenance: ToolDecisionProvenance,
) -> ToolPlan:
    params = {
        "query": user_text,
        "max_docs": 5,
        "snippet_chars": 1500,
    }
    if active_category:
        params["category"] = active_category
    return ToolPlan(
        provider="internal_docs",
        action="search_docs_rag",
        params=params,
        provenance=provenance,
    )


def _is_category_listing_request(lowered_text: str) -> bool:
    return _contains_any(lowered_text, DOC_CATEGORY_KEYWORDS)


def _is_doc_search_request(lowered_text: str, active_category: str | None) -> bool:
    has_search_action = _contains_any(lowered_text, DOC_SEARCH_ACTION_KEYWORDS)
    if not has_search_action:
        return False

    has_doc_target = _contains_any(lowered_text, DOC_SEARCH_TARGET_KEYWORDS)
    if has_doc_target:
        return True

    if active_category and _contains_any(lowered_text, DOC_SEARCH_CONTEXT_HINTS):
        return True

    return False


class DeterministicToolPlanner:
    def __init__(self, scenario_loader: ScenarioLoader):
        self._scenario_loader = scenario_loader

    def plan(self, user_text: str, active_category: str | None = None) -> list[ToolPlan]:
        stripped_text = user_text.strip()
        if not stripped_text or stripped_text.startswith("/mcp"):
            return []

        mentions = parse_at_mentions(user_text)
        if mentions:
            clean_query = strip_at_mentions(user_text)
            plans: list[ToolPlan] = []
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
                    ToolPlan(
                        provider="internal_docs",
                        action="search_docs_rag",
                        params=params,
                        provenance=_build_provenance(
                            provider="internal_docs",
                            action="search_docs_rag",
                            normalized_query=clean_query or raw_target,
                            decision_source="manual_mentions",
                            matched_rule="manual_mentions",
                            active_category=category,
                            mentions=tuple(mentions),
                            reason='`@...` mention syntax routed the query to targeted document search.',
                        ),
                    )
                )
            return plans

        scenario = self._scenario_loader.match(user_text)
        if scenario is not None:
            return [
                ToolPlan(
                    provider=plan.provider,
                    action=plan.action,
                    params=plan.params,
                    provenance=_build_provenance(
                        provider=plan.provider,
                        action=plan.action,
                        normalized_query=stripped_text,
                        decision_source="scenario",
                        matched_rule=f"scenario:{scenario.scenario_id}",
                        active_category=active_category,
                        reason=scenario.description or "Scenario rule matched the user prompt.",
                        scenario_id=scenario.scenario_id,
                        scenario_description=scenario.description,
                    ),
                )
                for plan in scenario.to_tool_plans(active_category=active_category)
            ]

        lowered_text = stripped_text.lower()
        if _is_category_listing_request(lowered_text):
            matched_keywords = _find_matched_keywords(lowered_text, DOC_CATEGORY_KEYWORDS)
            return [
                ToolPlan(
                    provider="internal_docs",
                    action="list_categories_detail",
                    params={},
                    provenance=_build_provenance(
                        provider="internal_docs",
                        action="list_categories_detail",
                        normalized_query=stripped_text,
                        decision_source="keyword_rule",
                        matched_rule="category_listing_keywords",
                        active_category=active_category,
                        matched_keywords=matched_keywords,
                        reason="Category/listing keywords matched a documentation catalog request.",
                    ),
                )
            ]

        if _is_doc_search_request(lowered_text, active_category):
            matched_keywords = (
                _find_matched_keywords(lowered_text, DOC_SEARCH_TARGET_KEYWORDS)
                + _find_matched_keywords(lowered_text, DOC_SEARCH_ACTION_KEYWORDS)
                + _find_matched_keywords(lowered_text, DOC_SEARCH_CONTEXT_HINTS)
            )
            return [
                _build_search_docs_plan(
                    user_text,
                    active_category,
                    provenance=_build_provenance(
                        provider="internal_docs",
                        action="search_docs_rag",
                        normalized_query=stripped_text,
                        decision_source="keyword_rule",
                        matched_rule="doc_search_target + search_action",
                        active_category=active_category,
                        matched_keywords=matched_keywords,
                        reason="Document-target keywords and search-intent keywords matched the document search rule.",
                    ),
                )
            ]

        return []


__all__ = ["DeterministicToolPlanner", "ToolDecisionProvenance", "ToolPlan"]
