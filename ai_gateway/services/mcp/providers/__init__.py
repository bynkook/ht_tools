"""
Provider adapters for MCP-backed integrations.
"""

from ..config import (
    DOC_SEARCH_PROVIDER_ID,
    DOC_SEARCH_PROVIDER_NAME,
    DOC_SEARCH_PROVIDER_ORIGIN_TYPE,
    DOC_SEARCH_PROVIDER_TRANSPORT,
)
from ..provider_manifest import McpProviderManifest
from .internal_docs import INTERNAL_DOCS_NORMALIZER_REF, INTERNAL_DOCS_POLICY_REF, InternalDocsProvider

INTERNAL_DOCS_PROVIDER_MANIFEST = McpProviderManifest(
    provider_id=DOC_SEARCH_PROVIDER_ID,
    display_name=DOC_SEARCH_PROVIDER_NAME,
    origin_type=DOC_SEARCH_PROVIDER_ORIGIN_TYPE,
    transport_type=DOC_SEARCH_PROVIDER_TRANSPORT,
    adapter_class=InternalDocsProvider,
    normalizer_ref=INTERNAL_DOCS_NORMALIZER_REF,
    policy_ref=INTERNAL_DOCS_POLICY_REF,
)

_PROVIDER_MANIFESTS = {
    INTERNAL_DOCS_PROVIDER_MANIFEST.provider_id: INTERNAL_DOCS_PROVIDER_MANIFEST,
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
    "McpProviderManifest",
    "get_provider_manifest",
    "list_provider_manifests",
    "require_provider_manifest",
]