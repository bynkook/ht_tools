"""
Minimal routing helpers for FabriX Chat -> MCP decisions.
"""

from dataclasses import dataclass

from .shared_planner.core import SharedPlannerCore
from .shared_planner.normalization import parse_at_mentions, split_mention_target, strip_at_mentions

_DEFAULT_ROUTER_CORE = SharedPlannerCore()


@dataclass(frozen=True)
class IntentRouteDecision:
    route: str
    clean_query: str
    mentions: list[str]


def route_chat_query(
    user_text: str,
    rag_enabled: bool,
) -> IntentRouteDecision:
    decision = _DEFAULT_ROUTER_CORE.plan(user_text, rag_enabled=rag_enabled)
    return IntentRouteDecision(
        route=decision.route,
        clean_query=decision.clean_query,
        mentions=list(decision.mentions),
    )


__all__ = [
    "IntentRouteDecision",
    "parse_at_mentions",
    "route_chat_query",
    "split_mention_target",
    "strip_at_mentions",
]