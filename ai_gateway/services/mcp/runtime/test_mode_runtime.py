"""
MCP Test Mode runtime implementation.
"""

import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

from fastapi import HTTPException

from ..config import McpEventPolicy, McpHostSettings
from ..event_emitter import SystemEventEmitter
from ..event_guard import SystemEventGuard
from ..host import GenericMcpHost, build_context_debug_payload, normalize_context_result
from ..shared_planner.models import PlannerDecision, PlannerToolPlan
from ..shared_planner.result_chaining import (
    chain_document_text,
    should_chain_doc_to_lexguard,
)
from ..test_mode import (
    DeterministicToolPlanner,
    ProtocolRecorder,
    ScenarioLoader,
    ToolPlan,
)
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
        self._event_policy = event_policy or McpEventPolicy(
            verbose_json=settings.test_mode_verbose_json,
            redact_headers=settings.test_mode_redact_headers,
            max_payload_chars=settings.test_mode_max_payload_chars,
            persist_system_logs=settings.test_mode_store_system_logs,
            visible_band_limit=settings.test_mode_visible_band_limit,
            raw_bytes_limit=settings.test_mode_raw_bytes_limit,
        )
        self._planner = planner or DeterministicToolPlanner(
            ScenarioLoader.from_settings(settings),
            provider_configs=mcp_host.settings.providers,
            default_provider_id=mcp_host.default_provider_id,
            enable_scenario_overrides=settings.test_mode_enable_scenario_override,
            host_settings=settings,
        )
        self._event_emitter = event_emitter or SystemEventEmitter(
            self._event_policy, channel="mcp_test"
        )

    async def stream_chat(self, runtime_input: ChatRuntimeInput) -> AsyncIterator[str]:
        request_id = self._build_request_id()
        active_category = (
            runtime_input.mcp_context.active_category
            if runtime_input.mcp_context
            else None
        )
        rag_enabled = (
            runtime_input.mcp_context.rag_enabled
            if runtime_input.mcp_context
            else False
        )
        provider_id = (
            runtime_input.mcp_context.provider_id if runtime_input.mcp_context else None
        )
        provider_categories = await self.mcp_host.build_planner_provider_categories()
        decision = self._planner.decide(
            runtime_input.contents[-1],
            active_category=active_category,
            rag_enabled=rag_enabled,
            provider_id=provider_id,
            provider_categories=provider_categories or None,
        )
        await self.mcp_host.validate_planner_decision(decision)
        recorder = ProtocolRecorder(
            self._event_emitter,
            request_id=request_id,
            provider=self._select_primary_provider(decision, provider_id),
        )
        return self._event_generator(
            runtime_input=runtime_input,
            recorder=recorder,
            decision=decision,
            selected_provider=provider_id,
        )

    async def _event_generator(
        self,
        *,
        runtime_input: ChatRuntimeInput,
        recorder: ProtocolRecorder,
        decision: PlannerDecision,
        selected_provider: str | None,
    ) -> AsyncIterator[str]:
        guard = SystemEventGuard(self._event_policy, request_id=recorder.request_id)
        recorder_event_details = self._build_provider_event_details(recorder.provider)
        plans = list(decision.plans)
        current_plan: ToolPlan | None = None
        results: list[dict[str, Any]] = []

        try:
            for provider_id in self._iter_discovery_providers(
                decision, selected_provider
            ):
                provider_event_details = self._build_provider_event_details(provider_id)
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.provider_connect_start(
                        "Connecting to MCP provider for Test Mode.",
                        provider=provider_id,
                        event_details=provider_event_details,
                    ),
                ):
                    yield payload
                capabilities = await self.mcp_host.discover_provider_capabilities(
                    provider_id=provider_id
                )
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.provider_connect_end(
                        "Provider connection established for Test Mode.",
                        provider=provider_id,
                        event_details=provider_event_details,
                    ),
                ):
                    yield payload
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.capability_discovery_start(
                        provider=provider_id,
                        event_details=provider_event_details,
                    ),
                ):
                    yield payload
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.capability_discovery_end(
                        raw=capabilities,
                        provider=provider_id,
                        event_details=provider_event_details,
                    ),
                ):
                    yield payload

            if not plans:
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.tool_decision(
                        content="No tool selected in test mode.",
                        raw={
                            "route": decision.route,
                            "contents": runtime_input.contents[-1],
                        },
                        event_details=recorder_event_details,
                    ),
                ):
                    yield payload
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.llm_bypassed(event_details=recorder_event_details),
                ):
                    yield payload
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.runtime_finished(event_details=recorder_event_details),
                ):
                    yield payload
                for payload in self._serialize_guard_flush(guard):
                    yield payload
                yield self._serialize_assistant_final(
                    build_synthetic_assistant_summary(plans=plans, results=[]),
                )
                yield self._serialize_stream_end("test_mode_complete")
                return

            for index, plan in enumerate(plans, start=1):
                current_plan = plan

                # Result chaining: if previous plan was doc_search and current needs document_text,
                # inject the document text from previous result.
                effective_plan = plan
                if index > 1 and results:
                    prev_plan = plans[index - 2]  # index is 1-based, plans is 0-based
                    prev_result = results[-1]
                    if should_chain_doc_to_lexguard(prev_plan.action, plan.action):
                        chained_params = chain_document_text(plan.params, prev_result)
                        # Create updated plan with chained params (PlannerToolPlan is frozen)
                        effective_plan = PlannerToolPlan(
                            provider=plan.provider,
                            action=plan.action,
                            params=chained_params,
                            provenance=plan.provenance,
                        )
                        current_plan = effective_plan

                plan_event_details = self._build_plan_event_details(
                    effective_plan, selection_rank=index
                )
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.tool_decision(
                        content=f"Selected {effective_plan.provider}.{effective_plan.action} via {effective_plan.provenance.decision_source}.",
                        raw=effective_plan.provenance.to_payload(),
                        provider=effective_plan.provider,
                        event_details=plan_event_details,
                    ),
                ):
                    yield payload
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.before_tool_call(
                        tool=effective_plan.action,
                        raw={"arguments": effective_plan.params},
                        provider=effective_plan.provider,
                        event_details=plan_event_details,
                    ),
                ):
                    yield payload
                result = await self._execute_plan(effective_plan)
                results.append(result)
                for payload in self._serialize_guarded_event(
                    guard,
                    recorder.after_tool_call(
                        tool=effective_plan.action,
                        raw=result["raw_result"],
                        provider=effective_plan.provider,
                        event_details=plan_event_details,
                    ),
                ):
                    yield payload
                current_plan = None

            context_summary = self._build_context_summary(
                runtime_input.system_prompt,
                [result["context_result"] for result in results],
            )
            for payload in self._serialize_guarded_event(
                guard,
                recorder.context_aggregated(
                    raw=context_summary, event_details=recorder_event_details
                ),
            ):
                yield payload
            for payload in self._serialize_guarded_event(
                guard,
                recorder.llm_bypassed(event_details=recorder_event_details),
            ):
                yield payload
            for payload in self._serialize_guarded_event(
                guard,
                recorder.runtime_finished(event_details=recorder_event_details),
            ):
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
            error_provider = (
                current_plan.provider if current_plan is not None else recorder.provider
            )
            error_event_details = self._build_error_event_details(
                current_plan=current_plan,
                completed_count=len(results),
                total_plans=len(plans),
            )
            for payload in self._serialize_guarded_event(
                guard,
                recorder.error(
                    phase="runtime",
                    title="Runtime error",
                    content=str(error.detail),
                    raw={"status_code": error.status_code},
                    tool=current_plan.action if current_plan is not None else None,
                    provider=error_provider,
                    event_details=error_event_details,
                ),
            ):
                yield payload
            for payload in self._serialize_guard_flush(guard):
                yield payload
            yield self._serialize_assistant_final(
                "[MCP-TEST] Test Mode runtime이 오류로 종료되었습니다.",
            )
            yield self._serialize_stream_end("error")
        except Exception as error:
            error_provider = (
                current_plan.provider if current_plan is not None else recorder.provider
            )
            error_event_details = self._build_error_event_details(
                current_plan=current_plan,
                completed_count=len(results),
                total_plans=len(plans),
            )
            for payload in self._serialize_guarded_event(
                guard,
                recorder.error(
                    phase="runtime",
                    title="Runtime error",
                    content=str(error),
                    raw={"type": type(error).__name__},
                    tool=current_plan.action if current_plan is not None else None,
                    provider=error_provider,
                    event_details=error_event_details,
                ),
            ):
                yield payload
            for payload in self._serialize_guard_flush(guard):
                yield payload
            yield self._serialize_assistant_final(
                "[MCP-TEST] Test Mode runtime이 오류로 종료되었습니다.",
            )
            yield self._serialize_stream_end("error")

    async def _execute_plan(self, plan: ToolPlan) -> dict[str, Any]:
        raw_result = await self.mcp_host.execute_tool_action(
            action=plan.action,
            arguments=plan.params,
            provider_id=plan.provider,
        )
        return {
            "raw_result": raw_result,
            "context_result": normalize_context_result(
                action=plan.action,
                arguments=plan.params,
                raw_result=raw_result,
                doc_search_settings=self._settings.doc_search,
                test_mode=True,
            ),
        }

    def _build_context_summary(
        self, base_system_prompt: str | None, context_results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return build_context_debug_payload(
            base_system_prompt=base_system_prompt,
            context_results=context_results,
        )

    def _select_primary_provider(
        self, decision: PlannerDecision, selected_provider: str | None = None
    ) -> str:
        if decision.plans:
            return decision.plans[0].provider
        return selected_provider or self.mcp_host.default_provider_id

    def _iter_discovery_providers(
        self, decision: PlannerDecision, selected_provider: str | None = None
    ) -> tuple[str, ...]:
        ordered_providers = [plan.provider for plan in decision.plans] or [
            selected_provider or self.mcp_host.default_provider_id
        ]
        seen: set[str] = set()
        resolved: list[str] = []
        for provider_id in ordered_providers:
            if provider_id in seen:
                continue
            seen.add(provider_id)
            resolved.append(provider_id)
        return tuple(resolved)

    def _provider_display_name(self, provider_id: str) -> str:
        settings = getattr(self.mcp_host, "settings", None)
        if settings is None or not hasattr(settings, "require_provider"):
            return provider_id
        try:
            provider_config = settings.require_provider(provider_id)
        except ValueError:
            return provider_id
        return provider_config.display_name

    def _build_provider_event_details(self, provider_id: str) -> dict[str, Any]:
        return {
            "provider_display_name": self._provider_display_name(provider_id),
        }

    def _build_plan_event_details(
        self, plan: ToolPlan, *, selection_rank: int
    ) -> dict[str, Any]:
        candidate_summary = (
            list(plan.provenance.provider_candidates)
            if plan.provenance.provider_candidates
            else None
        )
        return {
            **self._build_provider_event_details(plan.provider),
            "selection_reason": plan.provenance.reason
            or plan.provenance.decision_source,
            "selection_rank": selection_rank,
            "candidate_summary": candidate_summary,
        }

    def _build_error_event_details(
        self,
        *,
        current_plan: ToolPlan | None,
        completed_count: int,
        total_plans: int,
    ) -> dict[str, Any]:
        if current_plan is None:
            return {}
        remaining_plans = max(total_plans - completed_count - 1, 0)
        return {
            **self._build_plan_event_details(
                current_plan, selection_rank=completed_count + 1
            ),
            "partial_failure": {
                "completedCount": completed_count,
                "remainingPlans": remaining_plans,
                "failedProvider": current_plan.provider,
                "failedAction": current_plan.action,
            },
        }

    def _serialize_guarded_event(self, guard: SystemEventGuard, event) -> list[str]:
        return [
            self._serialize_system_event(system_event)
            for system_event in guard.accept(event)
        ]

    def _serialize_guard_flush(self, guard: SystemEventGuard) -> list[str]:
        return [
            self._serialize_system_event(system_event) for system_event in guard.flush()
        ]

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

    def _serialize_sse(self, payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def _build_request_id(self) -> str:
        return datetime.now(timezone.utc).strftime("turn-%Y%m%d-%H%M%S-%f")


__all__ = ["TestModeChatRuntime"]
