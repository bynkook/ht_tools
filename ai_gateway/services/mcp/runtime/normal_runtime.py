"""
Normal FabriX Chat runtime implementation.
"""

import json
from datetime import datetime, timezone
from typing import AsyncIterator

from ..config import McpEventPolicy
from ..context_merge import merge_system_prompts
from ..event_emitter import SystemEventEmitter
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
        # Emit a single "MCP activated" system event before the upstream stream
        # when MCP successfully contributed context (success-only, no partial info).
        if resolution is not None and resolution.activated:
            request_id = datetime.now(timezone.utc).strftime("normal-%Y%m%d-%H%M%S-%f")
            provider_id = (
                resolution.decision.plans[0].provider
                if resolution.decision and resolution.decision.plans
                else None
            )
            event = self._event_emitter.info(
                phase="mcp_activated",
                title="MCP context applied",
                content=f"route={resolution.route}",
                request_id=request_id,
                provider=provider_id,
                provider_id=provider_id,
            )
            yield f"data: {json.dumps(event.to_sse_payload(), ensure_ascii=False)}\n\n"

        async for chunk in upstream:
            yield chunk


__all__ = ["NormalChatRuntime"]
