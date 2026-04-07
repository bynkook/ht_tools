"""
System event emitter helpers for MCP runtime work.
"""

from typing import Any

from .config import McpEventPolicy
from .event_schema import (
    EventLevel,
    SystemEvent,
    build_event_fingerprint,
    redact_sensitive_data,
    truncate_event_raw,
)


class SystemEventEmitter:
    def __init__(self, policy: McpEventPolicy, *, channel: str = "mcp"):
        self._policy = policy
        self._channel = channel

    def emit(
        self,
        *,
        level: EventLevel,
        phase: str,
        title: str,
        content: str,
        request_id: str,
        provider: str | None = None,
        tool: str | None = None,
        raw: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> SystemEvent:
        normalized_raw = None
        if self._policy.verbose_json:
            sanitized_raw = redact_sensitive_data(
                raw,
                redact_headers=self._policy.redact_headers,
            )
            normalized_raw = truncate_event_raw(
                sanitized_raw,
                max_chars=self._policy.max_payload_chars,
            )
        return SystemEvent(
            kind="system_log",
            level=level,
            channel=self._channel,
            phase=phase,
            title=title,
            content=content,
            request_id=request_id,
            provider=provider,
            tool=tool,
            raw=normalized_raw,
            meta={
                "persist": self._policy.persist_system_logs,
                **(meta or {}),
            },
            fingerprint=build_event_fingerprint(
                level=level,
                phase=phase,
                provider=provider,
                tool=tool,
                request_id=request_id,
                content=content,
            ),
        )

    def info(self, **kwargs: Any) -> SystemEvent:
        return self.emit(level="info", **kwargs)

    def debug(self, **kwargs: Any) -> SystemEvent:
        return self.emit(level="debug", **kwargs)

    def warn(self, **kwargs: Any) -> SystemEvent:
        return self.emit(level="warn", **kwargs)

    def error(self, **kwargs: Any) -> SystemEvent:
        return self.emit(level="error", **kwargs)


__all__ = ["SystemEventEmitter"]
