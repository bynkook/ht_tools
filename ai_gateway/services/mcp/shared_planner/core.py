"""
Shared planner core for normalization and provider/tool decision building.
"""

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from ..config import DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF, DOC_SEARCH_PROVIDER_ID
from ..doc_search_policy import (
    DEFAULT_DOC_SEARCH_SETTINGS,
    McpDocSearchSettings,
    normalize_doc_search_rag_params,
)
from .catalog import (
    CombinedActivationCatalog,
    CompiledActivationCatalog,
    build_combined_activation_catalog,
    require_activation_catalog,
)
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
        activation_rule_refs: Iterable[str] | None = None,
        activation_catalog: CompiledActivationCatalog
        | CombinedActivationCatalog
        | None = None,
        doc_search_settings: McpDocSearchSettings | None = None,
    ):
        self._default_provider_id = default_provider_id
        self._activation_rule_ref = activation_rule_ref
        self._doc_search_settings = doc_search_settings or DEFAULT_DOC_SEARCH_SETTINGS
        self._activation_catalog = (
            activation_catalog
            or self._resolve_activation_catalog(
                activation_rule_ref=activation_rule_ref,
                activation_rule_refs=activation_rule_refs,
            )
        )

    def plan(
        self,
        user_text: str,
        *,
        active_category: str | None = None,
        rag_enabled: bool = False,
        scenario_loader: "ScenarioLoader | None" = None,
        enable_scenarios: bool = False,
        provider_hint: str | None = None,
        provider_categories: dict[str, tuple[str, ...]] | None = None,
    ) -> PlannerDecision:
        stripped_text = user_text.strip()
        if not stripped_text or stripped_text.startswith("/mcp"):
            return PlannerDecision(route="chat_only", clean_query=stripped_text)

        mentions = parse_at_mentions(user_text)
        if mentions:
            return self._build_manual_mentions_decision(
                user_text, mentions, active_category, provider_hint
            )

        if enable_scenarios and scenario_loader is not None:
            scenario = scenario_loader.match(user_text)
            if scenario is not None:
                return self._build_scenario_decision(
                    stripped_text, active_category, scenario
                )

        matches = self._activation_catalog.match(
            user_text,
            active_category=active_category,
            provider_hint=provider_hint,
            provider_categories=provider_categories,
        )
        if matches:
            return self._build_catalog_decision(stripped_text, active_category, matches)

        if rag_enabled:
            selected_provider = provider_hint or self._default_provider_id
            return PlannerDecision(
                route="rag_search",
                clean_query=stripped_text,
                plans=(
                    PlannerToolPlan(
                        provider=selected_provider,
                        action="search_docs_rag",
                        params=self._build_rag_params(stripped_text, active_category),
                        provenance=self._build_provenance(
                            provider=selected_provider,
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
        provider_hint: str | None,
    ) -> PlannerDecision:
        clean_query = strip_at_mentions(user_text)
        plans: list[PlannerToolPlan] = []
        selected_provider = provider_hint or self._default_provider_id
        candidate_summary = (f"{selected_provider}.search_docs_rag",)
        for raw_target in mentions:
            category, filename_filter = split_mention_target(
                raw_target, active_category
            )
            params = normalize_doc_search_rag_params(
                query=clean_query or raw_target,
                category=category,
                filename_filter=filename_filter,
            )
            plans.append(
                PlannerToolPlan(
                    provider=selected_provider,
                    action="search_docs_rag",
                    params=params,
                    provenance=self._build_provenance(
                        provider=selected_provider,
                        action="search_docs_rag",
                        normalized_query=clean_query or raw_target,
                        decision_source="manual_mentions",
                        matched_rule="manual_mentions",
                        active_category=category,
                        mentions=tuple(mentions),
                        provider_candidates=candidate_summary,
                        reason="`@...` mention syntax routed the query to targeted document search.",
                    ),
                )
            )
        return PlannerDecision(
            route="manual_mentions",
            clean_query=clean_query,
            mentions=tuple(mentions),
            plans=tuple(plans),
        )

    def _resolve_activation_catalog(
        self,
        *,
        activation_rule_ref: str,
        activation_rule_refs: Iterable[str] | None,
    ) -> CompiledActivationCatalog | CombinedActivationCatalog:
        if activation_rule_refs is None:
            return require_activation_catalog(activation_rule_ref)
        normalized_rule_refs = tuple(
            rule_ref for rule_ref in activation_rule_refs if rule_ref
        )
        if not normalized_rule_refs:
            return require_activation_catalog(activation_rule_ref)
        if len(normalized_rule_refs) == 1:
            return require_activation_catalog(normalized_rule_refs[0])
        return build_combined_activation_catalog(normalized_rule_refs)

    def _build_scenario_decision(
        self, stripped_text: str, active_category: str | None, scenario: Any
    ) -> PlannerDecision:
        scenario_plans = scenario.to_tool_plans(active_category=active_category)
        candidate_summary = tuple(
            f"{plan.provider}.{plan.action}" for plan in scenario_plans
        )
        plans = tuple(
            PlannerToolPlan(
                provider=plan.provider,
                action=plan.action,
                params=normalize_doc_search_rag_params(
                    plan.params,
                    query=str(plan.params.get("query", stripped_text)),
                    category=plan.params.get("category"),
                    filename_filter=plan.params.get("filename_filter"),
                    settings=self._doc_search_settings,
                )
                if plan.action == "search_docs_rag"
                else plan.params,
                provenance=self._build_provenance(
                    provider=plan.provider,
                    action=plan.action,
                    normalized_query=stripped_text,
                    decision_source="scenario",
                    matched_rule=f"scenario:{scenario.scenario_id}",
                    active_category=active_category,
                    provider_candidates=candidate_summary,
                    reason=scenario.description
                    or "Scenario rule matched the user prompt.",
                    scenario_id=scenario.scenario_id,
                    scenario_description=scenario.description,
                ),
            )
            for plan in scenario_plans
        )
        return PlannerDecision(route="scenario", clean_query=stripped_text, plans=plans)

    def _build_catalog_decision(
        self, stripped_text: str, active_category: str | None, matches: tuple[Any, ...]
    ) -> PlannerDecision:
        candidate_summary = tuple(
            f"{match.provider_id}.{match.action}" for match in matches
        )
        plans: list[PlannerToolPlan] = []
        for selected in self._select_catalog_matches(matches):
            params = dict(selected.params)
            resolved_category = (
                active_category if selected.use_active_category else None
            )
            if resolved_category is None and len(selected.matched_categories) == 1:
                resolved_category = selected.matched_categories[0]
            if selected.action == "search_docs_rag":
                params = self._build_rag_params(
                    stripped_text,
                    resolved_category,
                    **params,
                )
            else:
                # Non-RAG actions: map user query to tool-specific parameter names.
                # document_issue_tool requires "document_text", not "query".
                params = self._map_tool_params(selected.action, stripped_text, params)
            plans.append(
                PlannerToolPlan(
                    provider=selected.provider_id,
                    action=selected.action,
                    params=params,
                    provenance=self._build_provenance(
                        provider=selected.provider_id,
                        action=selected.action,
                        normalized_query=stripped_text,
                        decision_source="keyword_rule",
                        matched_rule=selected.rule_id,
                        active_category=resolved_category,
                        matched_keywords=selected.matched_keywords,
                        provider_candidates=candidate_summary,
                        reason=selected.description,
                    ),
                )
            )
        return PlannerDecision(
            route="catalog_match", clean_query=stripped_text, plans=tuple(plans)
        )

    def _select_catalog_matches(self, matches: tuple[Any, ...]) -> tuple[Any, ...]:
        selected_matches: list[Any] = []
        seen_providers: set[str] = set()
        for match in matches:
            if match.provider_id in seen_providers:
                continue
            selected_matches.append(match)
            seen_providers.add(match.provider_id)

        # Ensure read_doc (doc fetch) precedes document_issue_tool (lexguard) for chaining.
        # The catalog sort puts lower priority values first, which may place document_issue_tool
        # (priority 55) before read_doc (priority 70). Reorder so the fetch always runs first.
        actions = [m.action for m in selected_matches]
        if "read_doc" in actions and "document_issue_tool" in actions:
            read_idx = actions.index("read_doc")
            issue_idx = actions.index("document_issue_tool")
            if (
                issue_idx < read_idx
                and read_idx < len(selected_matches)
                and issue_idx < len(selected_matches)
            ):
                selected_matches[read_idx], selected_matches[issue_idx] = (
                    selected_matches[issue_idx],
                    selected_matches[read_idx],
                )

        return tuple(selected_matches)

    def _build_rag_params(
        self,
        query: str,
        active_category: str | None,
        *,
        filename_filter: str | None = None,
        **params: object,
    ) -> dict[str, object]:
        return normalize_doc_search_rag_params(
            params,
            query=query,
            category=active_category,
            filename_filter=filename_filter,
            settings=self._doc_search_settings,
        )

    def _map_tool_params(
        self,
        action: str,
        user_query: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Map user query to tool-specific parameter names.

        Different MCP tools expect different parameter names:
        - document_issue_tool: requires "document_text" (full contract/document text),
          injected via result chaining from read_doc — must never be called standalone.
        - law_article_tool: requires "law_name" (statute name like "근로기준법")
        - read_doc: requires "filename" (document filename extracted from query)
        - Most other tools: accept "query"
        """
        result = dict(params)

        # Tools that require document_text instead of query.
        # document_text must be populated via result chaining (read_doc → document_issue_tool).
        # A standalone document_issue_tool plan without prior read_doc is a planner configuration
        # error — the activation rules must always pair them.
        if action == "document_issue_tool":
            if "document_text" not in result:
                raise ValueError(
                    "document_issue_tool requires 'document_text' but it was not provided. "
                    "The activation rule must chain read_doc before document_issue_tool so the "
                    "document content is available for result chaining."
                )
            return result

        # Tools that require law_name instead of query (not used via activation rules currently)
        if action == "law_article_tool":
            if "law_name" not in result:
                # law_article_tool expects a specific statute name.
                # The activation rule should be using legal_qa_tool instead for general queries.
                result["law_name"] = user_query
            return result

        # read_doc: extract filename from query text (looks for "name.ext" patterns)
        if action == "read_doc":
            if "filename" not in result:
                filename = self._extract_filename_from_query(user_query)
                if filename:
                    result["filename"] = filename
            return result

        # Default: most tools accept "query"
        if "query" not in result:
            result["query"] = user_query

        return result

    _FILENAME_PATTERN = re.compile(
        r"\b([\w가-힣\-]+\.(?:md|txt|pdf|docx|hwp|xlsx|csv|json))\b",
        re.IGNORECASE,
    )

    def _extract_filename_from_query(self, user_query: str) -> str | None:
        """Extract a filename (with extension) from the user query string.

        Looks for patterns like "표준계약서.md", "계약서test.md", etc.
        Returns the first match, or None if not found.

        Limitation: Filenames with spaces are not matched by this pattern.
        Use quoted @-mention syntax for such files: @"파일 이름.md"
        """
        match = self._FILENAME_PATTERN.search(user_query)
        return match.group(1) if match else None

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
