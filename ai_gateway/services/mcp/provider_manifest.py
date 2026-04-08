"""
Provider manifest definitions for MCP adapter registration.
"""

from dataclasses import dataclass
from typing import Any

from .config import McpServerConfig


@dataclass(frozen=True)
class McpInstallProfile:
    profile_id: str
    distribution: str
    deployment_model: str
    update_strategy: str
    rollback_strategy: str


@dataclass(frozen=True)
class McpConnectionProfileSchema:
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...] = ()
    supports_auth: bool = False
    supports_env_overrides: bool = False


@dataclass(frozen=True)
class McpCapabilityPolicy:
    manual_commands: tuple[str, ...] = ()
    supports_category_catalog: bool = False
    supports_document_read: bool = False
    supports_search: bool = False
    supports_rag_context: bool = False


@dataclass(frozen=True)
class McpHealthcheckDefinition:
    method: str
    timeout_seconds: int = 10
    startup_required: bool = False


@dataclass(frozen=True)
class McpProviderManifest:
    provider_id: str
    display_name: str
    origin_type: str
    transport_type: str
    adapter_class: type[Any]
    normalizer_ref: str | None = None
    policy_ref: str | None = None
    install_profile: McpInstallProfile | None = None
    connection_profile_schema: McpConnectionProfileSchema | None = None
    capability_policy: McpCapabilityPolicy | None = None
    healthcheck_definition: McpHealthcheckDefinition | None = None

    def connect_from_config(self, config: McpServerConfig):
        return self.adapter_class.connect_from_config(config)


__all__ = [
    "McpCapabilityPolicy",
    "McpConnectionProfileSchema",
    "McpHealthcheckDefinition",
    "McpInstallProfile",
    "McpProviderManifest",
]
