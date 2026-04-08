"""
Shared text normalization helpers for MCP planner inputs.
"""

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


__all__ = [
    "AT_MENTION_PATTERN",
    "parse_at_mentions",
    "split_mention_target",
    "strip_at_mentions",
]