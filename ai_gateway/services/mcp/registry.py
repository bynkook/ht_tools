"""
Minimal MCP provider registry for Phase 1.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from .config import DOC_SEARCH_PROVIDER_ID, McpServerConfig, load_doc_search_server_config
from .providers import InternalDocsProvider


def list_provider_configs() -> list[McpServerConfig]:
    return [load_doc_search_server_config()]


def get_provider_config(provider_id: str = DOC_SEARCH_PROVIDER_ID) -> McpServerConfig:
    if provider_id != DOC_SEARCH_PROVIDER_ID:
        raise ValueError(f"Unknown MCP provider: {provider_id}")
    return load_doc_search_server_config()


@asynccontextmanager
async def connect_provider(
    provider_id: str = DOC_SEARCH_PROVIDER_ID,
) -> AsyncIterator[InternalDocsProvider]:
    if provider_id != DOC_SEARCH_PROVIDER_ID:
        raise ValueError(f"Unknown MCP provider: {provider_id}")
    async with InternalDocsProvider.connect_from_settings() as provider:
        yield provider


__all__ = ["connect_provider", "get_provider_config", "list_provider_configs"]
