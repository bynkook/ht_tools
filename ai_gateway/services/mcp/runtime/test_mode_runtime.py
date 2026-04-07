"""
MCP Test Mode runtime implementation.
"""

import json
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import HTTPException

from ..config import McpEventPolicy, McpHostSettings, build_mcp_event_policy
from ..event_emitter import SystemEventEmitter
from ..event_guard import SystemEventGuard
from ..host import GenericMcpHost, build_context_debug_payload, normalize_context_result
from ..test_mode import DeterministicToolPlanner, ProtocolRecorder, ScenarioLoader, ToolPlan
from ..test_mode.synthetic_assistant import build_synthetic_assistant_summary
from .base import BaseChatRuntime, ChatRuntimeInput


class TestModeChatRuntime(BaseChatRuntime):
    def __init__(
        self,
        *,
        request,
        mcp_host: GenericMcpHost,
        settings: McpHostSettings,
        event_policy: McpEventPolicy | None = None,
        planner: DeterministicToolPlanner | None = None,
        event_emitter: SystemEventEmitter | None = None,
    ):
        super().__init__(request=request, mcp_host=mcp_host)
        self._settings = settings
        self._event_policy = event_policy or build_mcp_event_policy(settings)
        self._planner = planner or DeterministicToolPlanner(ScenarioLoader.from_settings(settings))
        self._event_emitter = event_emitter or SystemEventEmitter(self._event_policy, channel="mcp_test")

    async def stream_chat(self, runtime_input: ChatRuntimeInput) -> AsyncIterator[str]:
        request_id = self._build_request_id()
        recorder = ProtocolRecorder(
            self._event_emitter,
            request_id=request_id,
            provider="internal_docs",
        )
        return self._event_generator(runtime_input=runtime_input, recorder=recorder)

    async def _event_generator(
        self,
        *,
        runtime_input: ChatRuntimeInput,
        recorder: ProtocolRecorder,
    ) -> AsyncIterator[str]:
        guard = SystemEventGuard(self._event_policy, request_id=recorder.request_id)
        for payload in self._serialize_guarded_event(
            guard,
            recorder.provider_connect_start("Connecting to MCP provider for Test Mode."),
        ):
            yield payload

        try:
            capabilities = await self.mcp_host.discover_provider_capabilities()
            for payload in self._serialize_guarded_event(
                guard,
                recorder.provider_connect_end("Provider connection established for Test Mode."),
            ):
                yield payload
            for payload in self._serialize_guarded_event(guard, recorder.capability_discovery_start()):
                yield payload
            for payload in self._serialize_guarded_event(
                guard,
                recorder.capability_discovery_end(raw=capabilities),
            ):
                yield payload

            active_category = runtime_input.mcp_context.active_category if runtime_input.mcp_context else None
            plans = self._planner.plan(
                runtime_input.contents[-1],
                active_category=active_category,
            )
            if not plans:
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.tool_decision(
                        content="No tool selected in test mode.",
                        raw={"contents": runtime_input.contents[-1]},
                    )
                ):
                    yield payload
                for payload in self._serialize_guarded_event(guard, recorder.llm_bypassed()):
                    yield payload
                for payload in self._serialize_guarded_event(guard, recorder.runtime_finished()):
                    yield payload
                for payload in self._serialize_guard_flush(guard):
                    yield payload
                yield self._serialize_assistant_final(
                    build_synthetic_assistant_summary(plans=plans, results=[]),
                )
                yield self._serialize_stream_end("test_mode_complete")
                return

            results: list[dict] = []
            for plan in plans:
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.tool_decision(
                        content=f"Selected {plan.provider}.{plan.action} via {plan.provenance.decision_source}.",
                        raw=plan.provenance.to_payload(),
                    )
                ):
                    yield payload
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.before_tool_call(tool=plan.action, raw={"arguments": plan.params})
                ):
                    yield payload
                result = await self._execute_plan(plan)
                results.append(result)
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.after_tool_call(tool=plan.action, raw=result["raw_result"]),
                ):
                    yield payload

            context_summary = self._build_context_summary(
                runtime_input.system_prompt,
                [result["context_result"] for result in results],
            )
            for payload in self._serialize_guarded_event(
                guard,
                recorder.context_aggregated(raw=context_summary),
            ):
                yield payload
            for payload in self._serialize_guarded_event(guard, recorder.llm_bypassed()):
                yield payload
            for payload in self._serialize_guarded_event(guard, recorder.runtime_finished()):
                yield payload
            for payload in self._serialize_guard_flush(guard):
                yield payload
            yield self._serialize_assistant_final(
                build_synthetic_assistant_summary(
                    plans=plans,
                    results=[result["raw_result"] for result in results],
                ),
            )
            yield self._serialize_stream_end("test_mode_complete")
        except HTTPException as error:
            for payload in self._serialize_guarded_event(
                guard,
                recorder.error(
                    phase="runtime",
                    title="Runtime error",
                    content=str(error.detail),
                    raw={"status_code": error.status_code},
                )
            ):
                yield payload
            for payload in self._serialize_guard_flush(guard):
                yield payload
            yield self._serialize_assistant_final(
                "[MCP-TEST] Test Mode runtime이 오류로 종료되었습니다.",
            )
            yield self._serialize_stream_end("error")
        except Exception as error:
            for payload in self._serialize_guarded_event(
                guard,
                recorder.error(
                    phase="runtime",
                    title="Runtime error",
                    content=str(error),
                    raw={"type": type(error).__name__},
                )
            ):
                yield payload
            for payload in self._serialize_guard_flush(guard):
                yield payload
            yield self._serialize_assistant_final(
                "[MCP-TEST] Test Mode runtime이 오류로 종료되었습니다.",
            )
            yield self._serialize_stream_end("error")

    async def _execute_plan(self, plan: ToolPlan) -> dict:
        raw_result = await self.mcp_host.execute_tool_action(
            action=plan.action,
            arguments=plan.params,
        )
        return {
            "raw_result": raw_result,
            "context_result": normalize_context_result(
                action=plan.action,
                arguments=plan.params,
                raw_result=raw_result,
            ),
        }

    def _build_context_summary(self, base_system_prompt: str | None, context_results: list[dict]) -> dict:
        return build_context_debug_payload(
            base_system_prompt=base_system_prompt,
            context_results=context_results,
        )

    def _serialize_guarded_event(self, guard: SystemEventGuard, event) -> list[str]:
        return [self._serialize_system_event(system_event) for system_event in guard.accept(event)]

    def _serialize_guard_flush(self, guard: SystemEventGuard) -> list[str]:
        return [self._serialize_system_event(system_event) for system_event in guard.flush()]

    def _serialize_system_event(self, event) -> str:
        return self._serialize_sse(event.to_sse_payload())

    def _serialize_assistant_final(self, content: str) -> str:
        return self._serialize_sse(
            {
                "event_type": "assistant_final",
                "content": content,
            }
        )

    def _serialize_stream_end(self, finish_reason: str) -> str:
        return self._serialize_sse(
            {
                "event_type": "stream_end",
                "finish_reason": finish_reason,
            }
        )

    def _serialize_sse(self, payload: dict) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def _build_request_id(self) -> str:
        return datetime.now(timezone.utc).strftime("turn-%Y%m%d-%H%M%S-%f")


__all__ = ["TestModeChatRuntime"]
