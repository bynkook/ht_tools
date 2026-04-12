"""
Backend-side guardrails for request-scoped MCP system logs.
"""

from dataclasses import replace
from json import dumps
from typing import Any

from .config import McpEventPolicy
from .event_schema import SystemEvent, build_event_fingerprint


class SystemEventGuard:
    def __init__(
        self, policy: McpEventPolicy, *, request_id: str, channel: str = "mcp_test"
    ):
        self._policy = policy
        self._request_id = request_id
        self._channel = channel
        self._pending_event: SystemEvent | None = None
        self._visible_count = 0
        self._suppressed_count = 0
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
        self._remember_context(event)

        if (
            self._pending_event is not None
            and self._pending_event.fingerprint == event.fingerprint
        ):
            self._pending_event = replace(
                self._pending_event,
                repeat_count=self._pending_event.repeat_count + event.repeat_count,
                raw=event.raw if event.raw is not None else self._pending_event.raw,
                timestamp=event.timestamp,
            )
            return emitted

        if self._pending_event is not None:
            emitted.append(self._pending_event)

        if self._visible_count >= self._policy.visible_band_limit:
            self._suppressed_count += 1
            self._pending_event = None
            return emitted

        self._pending_event = event
        self._visible_count += 1
        return emitted

    def flush(self) -> list[SystemEvent]:
        emitted: list[SystemEvent] = []
        if self._pending_event is not None:
            emitted.append(self._pending_event)
            self._pending_event = None

        if self._suppressed_count > 0:
            emitted.append(
                self._build_summary_event(
                    title="System log limit reached",
                    content=f"추가 system log **{self._suppressed_count}건** 이 생략되었습니다.",
                    suppressed_count=self._suppressed_count,
                )
            )

        return emitted

    def _apply_raw_budget(self, event: SystemEvent) -> SystemEvent:
        """Apply per-request raw bytes budget to the event's raw field.

        If the raw value fits within the remaining budget, it is kept as-is.
        If the raw value exceeds the remaining budget but budget is not yet
        exhausted, it is truncated and meta flags are set.
        If the budget is already exhausted (no room left), raw is suppressed
        entirely and meta.rawSuppressed is set.

        When raw_bytes_limit == 0 the budget is unlimited and raw is never
        touched.
        """
        limit = self._policy.raw_bytes_limit
        if limit == 0 or event.raw is None:
            return event

        try:
            serialized = dumps(event.raw, ensure_ascii=False, sort_keys=True)
        except TypeError:
            serialized = str(event.raw)

        raw_size = len(serialized.encode("utf-8"))
        remaining = limit - self._raw_bytes_used

        if remaining <= 0:
            # Budget fully exhausted — suppress raw entirely
            updated_meta = {**event.meta, "rawSuppressed": True}
            return replace(event, raw=None, meta=updated_meta)

        if raw_size <= remaining:
            # Fits within budget — keep as-is, consume budget
            self._raw_bytes_used += raw_size
            return event

        # Exceeds remaining budget — truncate to fit
        preview_bytes = max(remaining - 32, 0)  # reserve room for wrapper keys
        preview = serialized[:preview_bytes]
        truncated_size = len(preview.encode("utf-8"))
        # Mark the entire remaining budget as consumed so subsequent raw
        # payloads are suppressed rather than getting a second truncation slice.
        self._raw_bytes_used += remaining

        updated_meta = {
            **event.meta,
            "rawTruncated": True,
            "rawOriginalBytes": raw_size,
            "rawTruncatedBytes": truncated_size,
        }
        truncated_raw = {
            "_truncated": True,
            "preview": preview,
        }
        return replace(event, raw=truncated_raw, meta=updated_meta)

    def _remember_context(self, event: SystemEvent) -> None:
        self._last_context = {
            "provider": event.provider,
            "provider_id": event.provider_id,
            "provider_display_name": event.provider_display_name,
            "tool": event.tool,
            "timestamp": event.timestamp,
        }

    def _build_summary_event(
        self,
        *,
        title: str,
        content: str,
        suppressed_count: int = 0,
    ) -> SystemEvent:
        provider_id = (
            self._last_context["provider_id"] or self._last_context["provider"]
        )
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


__all__ = ["SystemEventGuard"]
