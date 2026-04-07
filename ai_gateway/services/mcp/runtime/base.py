"""
Base types for chat runtime strategies.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator

from fastapi import Request

from ..host import GenericMcpHost


@dataclass(frozen=True)
class McpContextInput:
    active_category: str | None
    rag_enabled: bool


@dataclass(frozen=True)
class ChatRuntimeInput:
    model_ids: list[str]
    contents: list[str]
    is_stream: bool
    system_prompt: str | None = None
    llm_config: dict[str, Any] | None = None
    mcp_context: McpContextInput | None = None


class BaseChatRuntime(ABC):
    def __init__(self, *, request: Request, mcp_host: GenericMcpHost):
        self.request = request
        self.mcp_host = mcp_host

    @abstractmethod
    async def stream_chat(self, runtime_input: ChatRuntimeInput) -> AsyncIterator[str]:
        """Return an SSE event iterator for the requested runtime."""


__all__ = ["BaseChatRuntime", "ChatRuntimeInput", "McpContextInput"]
