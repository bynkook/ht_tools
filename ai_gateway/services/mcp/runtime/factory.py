"""
Runtime factory for FabriX Chat mode selection.
"""

from fastapi import Request

from ..config import McpSettings, build_mcp_event_policy
from ..event_emitter import SystemEventEmitter
from ..host import GenericMcpHost
from .base import BaseChatRuntime
from .normal_runtime import NormalChatRuntime
from .test_mode_runtime import TestModeChatRuntime
from .upstream import FabrixUpstreamClient


class ChatRuntimeFactory:
    def __init__(self, *, request: Request, mcp_settings: McpSettings):
        self.request = request
        self.mcp_settings = mcp_settings

    def create(self) -> BaseChatRuntime:
        mcp_host = GenericMcpHost(self.mcp_settings)
        if self.mcp_settings.host.test_mode:
            event_policy = build_mcp_event_policy(self.mcp_settings.host)
            return TestModeChatRuntime(
                request=self.request,
                mcp_host=mcp_host,
                settings=self.mcp_settings.host,
                event_policy=event_policy,
                event_emitter=SystemEventEmitter(event_policy, channel="mcp_test"),
            )
        return NormalChatRuntime(
            request=self.request,
            mcp_host=mcp_host,
            upstream_client=FabrixUpstreamClient(self.request),
        )


__all__ = ["ChatRuntimeFactory"]
