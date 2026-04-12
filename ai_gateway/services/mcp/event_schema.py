"""
Shared system event schema for MCP runtime activity.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha1
from json import dumps
from typing import Any, Literal

EventLevel = Literal["info", "debug", "warn", "error"]

SENSITIVE_KEYWORDS = (
    "authorization",
    "token",
    "secret",
    "password",
    "cookie",
    "api_key",
    "apikey",
    "client_key",
    "x-openapi-token",
    "x-fabrix-client",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def redact_sensitive_data(value: Any, *, redact_headers: bool) -> Any:
    if not redact_headers:
        return value

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(str(key)):
                sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = redact_sensitive_data(item, redact_headers=redact_headers)
        return sanitized

    if isinstance(value, list):
        return [redact_sensitive_data(item, redact_headers=redact_headers) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item, redact_headers=redact_headers) for item in value)

    return value


def truncate_event_raw(value: Any, *, max_chars: int) -> Any:
    if value is None:
        return None

    try:
        serialized = dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        serialized = str(value)

    if len(serialized) <= max_chars:
        return value

    return {
        "truncated": True,
        "preview": serialized[:max_chars],
        "original_length": len(serialized),
    }


def build_event_fingerprint(
    *,
    level: str,
    phase: str,
    provider: str | None,
    tool: str | None,
    request_id: str,
    content: str,
) -> str:
    digest_source = "|".join(
        [
            level,
            phase,
            provider or "",
            tool or "",
            request_id,
            content.strip(),
        ]
    )
    return sha1(digest_source.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SystemEvent:
    kind: str
    level: EventLevel
    channel: str
    phase: str
    title: str
    content: str
    request_id: str
    provider: str | None = None
    provider_id: str | None = None
    provider_display_name: str | None = None
    tool: str | None = None
    selection_reason: str | None = None
    selection_rank: int | None = None
    candidate_summary: Any = None
    partial_failure: Any = None
    raw: Any = None
    meta: dict[str, Any] = field(default_factory=dict)
    fingerprint: str | None = None
    repeat_count: int = 1
    suppressed_count: int = 0
    timestamp: str = field(default_factory=_utc_now)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    def to_sse_payload(self) -> dict[str, Any]:
        return {
            "event_type": "system_log",
            **self.to_payload(),
        }


__all__ = [
    "EventLevel",
    "SystemEvent",
    "build_event_fingerprint",
    "redact_sensitive_data",
    "truncate_event_raw",
]