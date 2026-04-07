"""
Normal FabriX Chat runtime implementation.
"""

from typing import AsyncIterator

from ..context_merge import merge_system_prompts
from .base import BaseChatRuntime, ChatRuntimeInput
from .upstream import FabrixUpstreamClient


class NormalChatRuntime(BaseChatRuntime):
    def __init__(self, *, request, mcp_host, upstream_client: FabrixUpstreamClient):
        super().__init__(request=request, mcp_host=mcp_host)
        self._upstream_client = upstream_client

    async def stream_chat(self, runtime_input: ChatRuntimeInput) -> AsyncIterator[str]:
        system_prompt = runtime_input.system_prompt
        if runtime_input.mcp_context is not None:
            resolution = await self.mcp_host.build_chat_resolution(
                user_text=runtime_input.contents[-1],
                active_category=runtime_input.mcp_context.active_category,
                rag_enabled=runtime_input.mcp_context.rag_enabled,
            )
            system_prompt = merge_system_prompts(system_prompt, resolution.system_prompt)

        return await self._upstream_client.stream_chat(
            model_ids=runtime_input.model_ids,
            contents=runtime_input.contents,
            is_stream=runtime_input.is_stream,
            system_prompt=system_prompt,
            llm_config=runtime_input.llm_config,
        )


__all__ = ["NormalChatRuntime"]
