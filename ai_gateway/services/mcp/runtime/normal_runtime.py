"""
Normal FabriX Chat runtime implementation.
"""

import json
from datetime import datetime, timezone
from typing import AsyncIterator

from ..config import McpEventPolicy
from ..context_merge import merge_system_prompts
from ..event_emitter import SystemEventEmitter
from ..host import render_context_result_system_prompt
from .base import BaseChatRuntime, ChatRuntimeInput
from .upstream import FabrixUpstreamClient

# Minimal event policy for normal mode: no verbose JSON, no persistence overhead.
_NORMAL_EVENT_POLICY = McpEventPolicy(
    verbose_json=False,
    redact_headers=True,
    max_payload_chars=0,
    persist_system_logs=False,
    visible_band_limit=0,
    raw_bytes_limit=0,
)


class NormalChatRuntime(BaseChatRuntime):
    def __init__(self, *, request, mcp_host, upstream_client: FabrixUpstreamClient):
        super().__init__(request=request, mcp_host=mcp_host)
        self._upstream_client = upstream_client
        self._event_emitter = SystemEventEmitter(_NORMAL_EVENT_POLICY, channel="mcp")

    async def stream_chat(self, runtime_input: ChatRuntimeInput) -> AsyncIterator[str]:
        system_prompt = runtime_input.system_prompt
        resolution = None

        if runtime_input.mcp_context is not None:
            resolution = await self.mcp_host.build_chat_resolution(
                user_text=runtime_input.contents[-1],
                active_category=runtime_input.mcp_context.active_category,
                rag_enabled=runtime_input.mcp_context.rag_enabled,
                provider_id=runtime_input.mcp_context.provider_id,
            )
            system_prompt = merge_system_prompts(
                system_prompt, resolution.system_prompt
            )
            for context_result in getattr(resolution, "context_results", ()):
                rendered_prompt = render_context_result_system_prompt(context_result)
                if rendered_prompt == context_result.get("system_prompt"):
                    continue
                system_prompt = merge_system_prompts(system_prompt, rendered_prompt)

        upstream = await self._upstream_client.stream_chat(
            model_ids=runtime_input.model_ids,
            contents=runtime_input.contents,
            is_stream=runtime_input.is_stream,
            system_prompt=system_prompt,
            llm_config=runtime_input.llm_config,
        )

        return self._wrap_with_mcp_event(upstream, resolution)

    async def _wrap_with_mcp_event(
        self,
        upstream: AsyncIterator[str],
        resolution,
    ) -> AsyncIterator[str]:
        # Emit one "MCP activated" system event per unique activated provider,
        # only when MCP successfully contributed context (success-only, no debug detail).
        if resolution is not None and resolution.activated:
            request_id = datetime.now(timezone.utc).strftime("normal-%Y%m%d-%H%M%S-%f")
            activated_providers = self._collect_activated_providers(resolution)
            for provider_id in activated_providers:
                display_name = self._provider_display_name(provider_id)
                event = self._event_emitter.info(
                    phase="mcp_activated",
                    title="MCP 활성화됨",
                    content=f"[MCP] {display_name} 활성화됨",
                    request_id=request_id,
                    provider=provider_id,
                    provider_id=provider_id,
                    provider_display_name=display_name,
                )
                yield f"data: {json.dumps(event.to_sse_payload(), ensure_ascii=False)}\n\n"

        try:
            async for chunk in upstream:
                yield chunk
        except Exception as error:
            # Emit SSE error event so clients see the failure before stream closes
            error_event = self._event_emitter.error(
                phase="upstream_stream",
                title="스트리밍 오류",
                content=f"[MCP] 업스트림 스트리밍 중 오류 발생: {error}",
                request_id=datetime.now(timezone.utc).strftime(
                    "error-%Y%m%d-%H%M%S-%f"
                ),
            )
            yield f"data: {json.dumps(error_event.to_sse_payload(), ensure_ascii=False)}\n\n"
            raise

    def _collect_activated_providers(self, resolution) -> list[str]:
        """Return unique provider IDs that participated in the resolution, in plan order."""
        if resolution.decision is None or not resolution.decision.plans:
            return []
        seen: set[str] = set()
        providers: list[str] = []
        for plan in resolution.decision.plans:
            if plan.provider and plan.provider not in seen:
                seen.add(plan.provider)
                providers.append(plan.provider)
        return providers

    def _provider_display_name(self, provider_id: str) -> str:
        """Resolve provider_id to its configured display_name, falling back to provider_id."""
        settings = getattr(self.mcp_host, "settings", None)
        if settings is None or not hasattr(settings, "require_provider"):
            return provider_id
        try:
            provider_config = settings.require_provider(provider_id)
        except ValueError:
            return provider_id
        return provider_config.display_name


__all__ = ["NormalChatRuntime"]
