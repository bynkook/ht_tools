"""
Provider manifest definitions for MCP adapter registration.
"""

from dataclasses import dataclass
from typing import Any

from .config import McpServerConfig


@dataclass(frozen=True)
class McpProviderManifest:
    provider_id: str
    display_name: str
    origin_type: str
    transport_type: str
    adapter_class: type[Any]
    normalizer_ref: str | None = None
    policy_ref: str | None = None

    def connect_from_config(self, config: McpServerConfig):
        return self.adapter_class.connect_from_config(config)


__all__ = ["McpProviderManifest"]