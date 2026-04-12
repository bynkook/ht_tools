"""
Backend-side guardrails for request-scoped MCP system logs.
"""

from dataclasses import replace
from json import dumps
from typing import Any

from .config import McpEventPolicy
from .event_schema import SystemEvent, build_event_fingerprint

RAW_VALUE_PREVIEW_CHARS = 500


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
        self._last_context: dict[str, Any] = {
            "provider": None,
            "provider_id": None,
            "provider_display_name": None,
            "tool": None,
            "timestamp": None,
        }

    def accept(self, event: SystemEvent) -> list[SystemEvent]:
        emitted: list[SystemEvent] = []
        guarded_event = self._apply_raw_preview(event)
        self._remember_context(guarded_event)

        if (
            self._pending_event is not None
            and self._pending_event.fingerprint == guarded_event.fingerprint
        ):
            self._pending_event = replace(
                self._pending_event,
                repeat_count=self._pending_event.repeat_count
                + guarded_event.repeat_count,
                raw=guarded_event.raw
                if guarded_event.raw is not None
                else self._pending_event.raw,
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

    def _apply_raw_preview(self, event: SystemEvent) -> SystemEvent:
        if event.raw is None:
            return event
        preview = _build_raw_preview(event.raw, RAW_VALUE_PREVIEW_CHARS)
        if preview is event.raw:
            return event
        return replace(event, raw=preview)

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


def _build_raw_preview(raw: Any, max_chars: int) -> Any:
    """이벤트별 독립적으로 dict의 각 value를 max_chars 문자로 제한한다.

    - dict가 아닌 경우: str로 변환 후 제한
    - 모든 value가 제한 이내이면 원본 객체를 그대로 반환 (identity 보장)
    """
    if not isinstance(raw, dict):
        s = dumps(raw, ensure_ascii=False)
        if len(s) <= max_chars:
            return raw
        return s[:max_chars] + "...(생략)"

    truncated = False
    result: dict[str, Any] = {}
    for k, v in raw.items():
        s = dumps(v, ensure_ascii=False)
        if len(s) > max_chars:
            result[k] = s[:max_chars] + "...(생략)"
            truncated = True
        else:
            result[k] = v

    return result if truncated else raw


__all__ = ["SystemEventGuard"]
