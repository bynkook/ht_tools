"""
Minimal MCP provider registry for Phase 1.
"""

from contextlib import asynccontextmanager
import ipaddress
from typing import AsyncIterator
from urllib.parse import urlparse

from .config import DOC_SEARCH_PROVIDER_ID, McpServerConfig, McpSettings, load_doc_search_server_config
from .providers import InternalDocsProvider


def _is_loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return True
    if hostname in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _enforce_remote_policy(config: McpServerConfig, settings: McpSettings | None) -> None:
    if settings is None or settings.host.test_mode_allow_remote_mcp:
        return
    parsed = urlparse(config.base_url)
    if _is_loopback_host(parsed.hostname):
        return
    raise RuntimeError(f"Remote MCP provider is disabled by MCP_TEST_MODE_ALLOW_REMOTE_MCP: {config.base_url}")


def list_provider_configs(settings: McpSettings | None = None) -> list[McpServerConfig]:
    return [get_provider_config(settings=settings)]


def get_provider_config(
    provider_id: str = DOC_SEARCH_PROVIDER_ID,
    *,
    settings: McpSettings | None = None,
) -> McpServerConfig:
    if provider_id != DOC_SEARCH_PROVIDER_ID:
        raise ValueError(f"Unknown MCP provider: {provider_id}")
    return settings.doc_server if settings is not None else load_doc_search_server_config()


@asynccontextmanager
async def connect_provider(
    provider_id: str = DOC_SEARCH_PROVIDER_ID,
    *,
    settings: McpSettings | None = None,
) -> AsyncIterator[InternalDocsProvider]:
    if provider_id != DOC_SEARCH_PROVIDER_ID:
        raise ValueError(f"Unknown MCP provider: {provider_id}")
    config = get_provider_config(provider_id, settings=settings)
    _enforce_remote_policy(config, settings)
    async with InternalDocsProvider.connect_from_config(config) as provider:
        yield provider


__all__ = ["connect_provider", "get_provider_config", "list_provider_configs"]
