"""
Provider adapters for MCP-backed integrations.
"""

from ..config import (
    DOC_SEARCH_PROVIDER_ID,
    DOC_SEARCH_PROVIDER_NAME,
    DOC_SEARCH_PROVIDER_ORIGIN_TYPE,
    DOC_SEARCH_PROVIDER_TRANSPORT,
)
from ..provider_manifest import (
    McpCapabilityPolicy,
    McpConnectionProfileSchema,
    McpHealthcheckDefinition,
    McpInstallProfile,
    McpProviderManifest,
)
from .internal_docs import (
    INTERNAL_DOCS_NORMALIZER_REF,
    INTERNAL_DOCS_POLICY_REF,
    InternalDocsProvider,
)
from .lexguard import (
    LEXGUARD_NORMALIZER_REF,
    LEXGUARD_POLICY_REF,
    LEXGUARD_PROVIDER_ID,
    LEXGUARD_PROVIDER_NAME,
    LEXGUARD_PROVIDER_ORIGIN_TYPE,
    LEXGUARD_PROVIDER_TRANSPORT,
    LexguardProvider,
)

INTERNAL_DOCS_PROVIDER_MANIFEST = McpProviderManifest(
    provider_id=DOC_SEARCH_PROVIDER_ID,
    display_name=DOC_SEARCH_PROVIDER_NAME,
    origin_type=DOC_SEARCH_PROVIDER_ORIGIN_TYPE,
    transport_type=DOC_SEARCH_PROVIDER_TRANSPORT,
    adapter_class=InternalDocsProvider,
    normalizer_ref=INTERNAL_DOCS_NORMALIZER_REF,
    policy_ref=INTERNAL_DOCS_POLICY_REF,
    install_profile=McpInstallProfile(
        profile_id="internal_docs.offline_copy_injection",
        distribution="upstream_snapshot",
        deployment_model="copy_to_server",
        update_strategy="replace_snapshot_and_rewire_adapter",
        rollback_strategy="restore_previous_snapshot_and_config",
    ),
    connection_profile_schema=McpConnectionProfileSchema(
        required_fields=("base_url", "transport"),
        optional_fields=(
            "kind",
            "origin_type",
            "activation_rule_ref",
            "install_profile",
            "connection_profile",
        ),
    ),
    capability_policy=McpCapabilityPolicy(
        manual_commands=("list", "search", "read"),
        supports_category_catalog=True,
        supports_document_read=True,
        supports_search=True,
        supports_rag_context=True,
    ),
    healthcheck_definition=McpHealthcheckDefinition(
        method="list_capabilities",
        timeout_seconds=10,
        startup_required=False,
    ),
)

LEXGUARD_PROVIDER_MANIFEST = McpProviderManifest(
    provider_id=LEXGUARD_PROVIDER_ID,
    display_name=LEXGUARD_PROVIDER_NAME,
    origin_type=LEXGUARD_PROVIDER_ORIGIN_TYPE,
    transport_type=LEXGUARD_PROVIDER_TRANSPORT,
    adapter_class=LexguardProvider,
    normalizer_ref=LEXGUARD_NORMALIZER_REF,
    policy_ref=LEXGUARD_POLICY_REF,
    install_profile=McpInstallProfile(
        profile_id="lexguard.external_venv_server",
        distribution="git_clone",
        deployment_model="external_folder_separate_venv",
        update_strategy="git_pull_and_restart",
        rollback_strategy="git_checkout_previous_tag_and_restart",
    ),
    connection_profile_schema=McpConnectionProfileSchema(
        required_fields=("base_url", "transport"),
        optional_fields=("kind", "origin_type", "activation_rule_ref"),
    ),
    capability_policy=McpCapabilityPolicy(
        manual_commands=(),
        supports_category_catalog=False,
        supports_document_read=False,
        supports_search=True,
        supports_rag_context=True,
    ),
    healthcheck_definition=McpHealthcheckDefinition(
        method="health_check",
        timeout_seconds=10,
        startup_required=False,
    ),
)

_PROVIDER_MANIFESTS = {
    INTERNAL_DOCS_PROVIDER_MANIFEST.provider_id: INTERNAL_DOCS_PROVIDER_MANIFEST,
    LEXGUARD_PROVIDER_MANIFEST.provider_id: LEXGUARD_PROVIDER_MANIFEST,
}


def list_provider_manifests() -> list[McpProviderManifest]:
    return list(_PROVIDER_MANIFESTS.values())


def get_provider_manifest(provider_id: str) -> McpProviderManifest | None:
    return _PROVIDER_MANIFESTS.get(provider_id)


def require_provider_manifest(provider_id: str) -> McpProviderManifest:
    manifest = get_provider_manifest(provider_id)
    if manifest is None:
        raise ValueError(f"MCP provider manifest is not registered: {provider_id}")
    return manifest


__all__ = [
    "InternalDocsProvider",
    "INTERNAL_DOCS_PROVIDER_MANIFEST",
    "LexguardProvider",
    "LEXGUARD_PROVIDER_MANIFEST",
    "McpProviderManifest",
    "get_provider_manifest",
    "list_provider_manifests",
    "require_provider_manifest",
]
