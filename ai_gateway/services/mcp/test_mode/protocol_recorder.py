"""
Protocol recorder helpers for MCP Test Mode and future runtime logging.
"""

from typing import Any

from ..event_emitter import SystemEventEmitter
from ..event_schema import SystemEvent


class ProtocolRecorder:
    def __init__(
        self,
        emitter: SystemEventEmitter,
        *,
        request_id: str,
        provider: str,
    ):
        self._emitter = emitter
        self._request_id = request_id
        self._provider = provider
        self._events: list[SystemEvent] = []

    def _record(self, event: SystemEvent) -> SystemEvent:
        self._events.append(event)
        return event

    def provider_connect_start(self, content: str = "Connecting to MCP provider.") -> SystemEvent:
        return self._record(
            self._emitter.info(
                phase="provider_connect",
                title="Provider connect start",
                content=content,
                request_id=self._request_id,
                provider=self._provider,
            )
        )

    def provider_connect_end(self, content: str = "Provider connection established.") -> SystemEvent:
        return self._record(
            self._emitter.info(
                phase="provider_connect",
                title="Provider connect end",
                content=content,
                request_id=self._request_id,
                provider=self._provider,
            )
        )

    def capability_discovery_start(self) -> SystemEvent:
        return self._record(
            self._emitter.info(
                phase="capability_discovery",
                title="Capability discovery start",
                content="Listing tools, resources, and prompts.",
                request_id=self._request_id,
                provider=self._provider,
            )
        )

    def capability_discovery_end(self, *, raw: Any) -> SystemEvent:
        return self._record(
            self._emitter.info(
                phase="capability_discovery",
                title="Capability discovery end",
                content="Capability discovery completed.",
                request_id=self._request_id,
                provider=self._provider,
                raw=raw,
            )
        )

    def tool_decision(self, *, content: str, raw: Any = None) -> SystemEvent:
        return self._record(
            self._emitter.info(
                phase="planning",
                title="Tool decision",
                content=content,
                request_id=self._request_id,
                provider=self._provider,
                raw=raw,
            )
        )

    def before_tool_call(self, *, tool: str, raw: Any) -> SystemEvent:
        return self._record(
            self._emitter.debug(
                phase="tool_call",
                title="Before tool call",
                content=f"Calling {tool}.",
                request_id=self._request_id,
                provider=self._provider,
                tool=tool,
                raw=raw,
            )
        )

    def after_tool_call(self, *, tool: str, raw: Any) -> SystemEvent:
        return self._record(
            self._emitter.debug(
                phase="tool_call",
                title="After tool call",
                content=f"{tool} completed.",
                request_id=self._request_id,
                provider=self._provider,
                tool=tool,
                raw=raw,
            )
        )

    def context_aggregated(self, *, raw: Any) -> SystemEvent:
        return self._record(
            self._emitter.info(
                phase="context_merge",
                title="Context aggregated",
                content="Final MCP context assembled for the current turn.",
                request_id=self._request_id,
                provider=self._provider,
                raw=raw,
            )
        )

    def llm_bypassed(self) -> SystemEvent:
        return self._record(
            self._emitter.info(
                phase="llm_bypass",
                title="LLM bypassed",
                content="External LLM call was intentionally skipped in MCP_TEST_MODE.",
                request_id=self._request_id,
                provider=self._provider,
            )
        )

    def runtime_finished(self, content: str = "Runtime finished.") -> SystemEvent:
        return self._record(
            self._emitter.info(
                phase="runtime",
                title="Runtime finished",
                content=content,
                request_id=self._request_id,
                provider=self._provider,
            )
        )

    def warning(self, *, phase: str, title: str, content: str, raw: Any = None, tool: str | None = None) -> SystemEvent:
        return self._record(
            self._emitter.warn(
                phase=phase,
                title=title,
                content=content,
                request_id=self._request_id,
                provider=self._provider,
                tool=tool,
                raw=raw,
            )
        )

    def error(self, *, phase: str, title: str, content: str, raw: Any = None, tool: str | None = None) -> SystemEvent:
        return self._record(
            self._emitter.error(
                phase=phase,
                title=title,
                content=content,
                request_id=self._request_id,
                provider=self._provider,
                tool=tool,
                raw=raw,
            )
        )

    def snapshot(self) -> list[SystemEvent]:
        return list(self._events)

    @property
    def request_id(self) -> str:
        return self._request_id


__all__ = ["ProtocolRecorder"]
