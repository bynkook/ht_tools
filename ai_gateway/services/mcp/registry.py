"""
Minimal MCP provider registry for Phase 1.
"""

from contextlib import asynccontextmanager
import ipaddress
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from .config import DOC_SEARCH_PROVIDER_ID, McpServerConfig, McpSettings, load_mcp_settings, load_provider_config
from .providers import require_provider_manifest


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


def _ensure_manifest_matches_config(config: McpServerConfig) -> None:
    manifest = require_provider_manifest(config.provider_id)
    if config.transport != manifest.transport_type:
        raise ValueError(
            f"Configured transport does not match registered MCP provider manifest: {config.provider_id}"
        )


def list_provider_configs(settings: McpSettings | None = None) -> list[McpServerConfig]:
    current_settings = settings or load_mcp_settings()
    configs = current_settings.enabled_provider_configs()
    for config in configs:
        _ensure_manifest_matches_config(config)
    return configs


def get_provider_config(
    provider_id: str = DOC_SEARCH_PROVIDER_ID,
    *,
    settings: McpSettings | None = None,
) -> McpServerConfig:
    if settings is not None:
        config = settings.require_provider(provider_id)
    else:
        config = load_provider_config(provider_id)

    _ensure_manifest_matches_config(config)
    return config


@asynccontextmanager
async def connect_provider(
    provider_id: str = DOC_SEARCH_PROVIDER_ID,
    *,
    settings: McpSettings | None = None,
) -> AsyncIterator[Any]:
    config = get_provider_config(provider_id, settings=settings)
    manifest = require_provider_manifest(provider_id)
    _enforce_remote_policy(config, settings)
    async with manifest.connect_from_config(config) as provider:
        yield provider


__all__ = ["connect_provider", "get_provider_config", "list_provider_configs"]