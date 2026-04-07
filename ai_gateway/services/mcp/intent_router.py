"""
Minimal routing helpers for FabriX Chat -> MCP decisions.
"""

from dataclasses import dataclass
import re

AT_MENTION_PATTERN = re.compile(r'@"([^"]+)"|@([^\s"@]+)')


def parse_at_mentions(text: str) -> list[str]:
    mentions: list[str] = []
    for match in AT_MENTION_PATTERN.finditer(text):
        raw = (match.group(1) or match.group(2) or "").strip()
        if raw:
            mentions.append(raw)
    return mentions


def strip_at_mentions(text: str) -> str:
    stripped = AT_MENTION_PATTERN.sub("", text)
    return re.sub(r"\s{2,}", " ", stripped).strip()


def split_mention_target(raw_target: str, active_category: str | None) -> tuple[str | None, str]:
    normalized = raw_target.strip()
    if "/" in normalized:
        category, filename = normalized.split("/", 1)
        return category.strip() or None, filename.strip()
    return active_category, normalized


@dataclass(frozen=True)
class IntentRouteDecision:
    route: str
    clean_query: str
    mentions: list[str]


def route_chat_query(
    user_text: str,
    rag_enabled: bool,
) -> IntentRouteDecision:
    mentions = parse_at_mentions(user_text)
    if mentions:
        return IntentRouteDecision(
            route="manual_mentions",
            clean_query=strip_at_mentions(user_text),
            mentions=mentions,
        )
    if rag_enabled:
        return IntentRouteDecision(
            route="rag_search",
            clean_query=user_text.strip(),
            mentions=[],
        )
    return IntentRouteDecision(
        route="chat_only",
        clean_query=user_text.strip(),
        mentions=[],
    )


__all__ = [
    "IntentRouteDecision",
    "parse_at_mentions",
    "route_chat_query",
    "split_mention_target",
    "strip_at_mentions",
]
