"""
Backend-side guardrails for request-scoped MCP system logs.
"""

from dataclasses import replace
from json import dumps
from typing import Any

from .config import McpEventPolicy
from .event_schema import SystemEvent, build_event_fingerprint


class SystemEventGuard:
    def __init__(self, policy: McpEventPolicy, *, request_id: str, channel: str = "mcp_test"):
        self._policy = policy
        self._request_id = request_id
        self._channel = channel
        self._pending_event: SystemEvent | None = None
        self._visible_count = 0
        self._suppressed_count = 0
        self._raw_suppressed_count = 0
        self._raw_bytes_used = 0
        self._last_context: dict[str, Any] = {
            "provider": None,
            "provider_id": None,
            "provider_display_name": None,
            "tool": None,
            "timestamp": None,
        }

    def accept(self, event: SystemEvent) -> list[SystemEvent]:
        emitted: list[SystemEvent] = []
        guarded_event = self._apply_raw_budget(event)
        self._remember_context(guarded_event)

        if self._pending_event is not None and self._pending_event.fingerprint == guarded_event.fingerprint:
            self._pending_event = replace(
                self._pending_event,
                repeat_count=self._pending_event.repeat_count + guarded_event.repeat_count,
                raw=guarded_event.raw if guarded_event.raw is not None else self._pending_event.raw,
                timestamp=guarded_event.timestamp,
            )
            return emitted

        if self._pending_event is not None:
            emitted.append(self._pending_event)

        if self._visible_count >= self._policy.visible_band_limit:
            self._suppressed_count += 1
            self._pending_event = None
            return emitted

        self._pending_event = guarded_event
        self._visible_count += 1
        return emitted

    def flush(self) -> list[SystemEvent]:
        emitted: list[SystemEvent] = []
        if self._pending_event is not None:
            emitted.append(self._pending_event)
            self._pending_event = None

        if self._raw_suppressed_count > 0:
            emitted.append(
                self._build_summary_event(
                    title="Raw payload limit reached",
                    content=f"추가 raw payload **{self._raw_suppressed_count}건** 이 생략되었습니다.",
                    raw_suppressed_count=self._raw_suppressed_count,
                )
            )

        if self._suppressed_count > 0:
            emitted.append(
                self._build_summary_event(
                    title="System log limit reached",
                    content=f"추가 system log **{self._suppressed_count}건** 이 생략되었습니다.",
                    suppressed_count=self._suppressed_count,
                )
            )

        return emitted

    def _remember_context(self, event: SystemEvent) -> None:
        self._last_context = {
            "provider": event.provider,
            "provider_id": event.provider_id,
            "provider_display_name": event.provider_display_name,
            "tool": event.tool,
            "timestamp": event.timestamp,
        }

    def _apply_raw_budget(self, event: SystemEvent) -> SystemEvent:
        if event.raw is None:
            return event

        raw_bytes = self._serialized_size(event.raw)
        if self._raw_bytes_used + raw_bytes <= self._policy.raw_bytes_limit:
            self._raw_bytes_used += raw_bytes
            return event

        self._raw_suppressed_count += 1
        return replace(
            event,
            raw=None,
            meta={
                **event.meta,
                "rawSuppressed": True,
            },
        )

    def _build_summary_event(
        self,
        *,
        title: str,
        content: str,
        suppressed_count: int = 0,
        raw_suppressed_count: int = 0,
    ) -> SystemEvent:
        provider_id = self._last_context["provider_id"] or self._last_context["provider"]
        return SystemEvent(
            kind="system_log",
            level="info",
            channel=self._channel,
            phase="log_guard",
            title=title,
            content=content,
            request_id=self._request_id,
            provider=provider_id,
            provider_id=provider_id,
            provider_display_name=self._last_context["provider_display_name"],
            tool=self._last_context["tool"],
            meta={
                "persist": self._policy.persist_system_logs,
                "rawSuppressedCount": raw_suppressed_count,
            },
            fingerprint=build_event_fingerprint(
                level="info",
                phase="log_guard",
                provider=provider_id,
                tool=self._last_context["tool"],
                request_id=self._request_id,
                content=content,
            ),
            suppressed_count=suppressed_count,
            timestamp=self._last_context["timestamp"],
        )

    @staticmethod
    def _serialized_size(value: Any) -> int:
        try:
            return len(dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        except TypeError:
            return len(str(value).encode("utf-8"))


__all__ = ["SystemEventGuard"]