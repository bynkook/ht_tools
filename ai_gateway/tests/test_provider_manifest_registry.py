from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import DOC_SEARCH_PROVIDER_ID, load_mcp_settings
from services.mcp.providers import INTERNAL_DOCS_PROVIDER_MANIFEST, require_provider_manifest
from services.mcp.registry import get_provider_config, list_provider_configs
from services.mcp.providers.internal_docs import INTERNAL_DOCS_NORMALIZER_REF, INTERNAL_DOCS_POLICY_REF


@patch.dict("os.environ", {}, clear=True)
def test_internal_docs_manifest_is_registered_in_provider_catalog():
    manifest = require_provider_manifest(DOC_SEARCH_PROVIDER_ID)

    assert manifest == INTERNAL_DOCS_PROVIDER_MANIFEST
    assert manifest.provider_id == DOC_SEARCH_PROVIDER_ID
    assert manifest.transport_type == "streamable_http"
    assert manifest.normalizer_ref == INTERNAL_DOCS_NORMALIZER_REF
    assert manifest.policy_ref == INTERNAL_DOCS_POLICY_REF


@patch.dict("os.environ", {}, clear=True)
def test_registry_reads_enabled_provider_configs_through_manifest_catalog():
    settings = load_mcp_settings(
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8102/mcp",
                        "transport": "streamable_http",
                    }
                }
            }
        }
    )

    config = get_provider_config(settings=settings)

    assert config.provider_id == DOC_SEARCH_PROVIDER_ID
    assert list_provider_configs(settings=settings)[0].base_url == "http://127.0.0.1:8102/mcp"


@patch.dict("os.environ", {}, clear=True)
def test_registry_fails_fast_when_enabled_provider_has_no_registered_manifest():
    settings = load_mcp_settings(
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8102/mcp",
                        "transport": "streamable_http",
                    },
                    "legal_cases": {
                        "base_url": "http://127.0.0.1:8202/mcp",
                        "transport": "streamable_http",
                    },
                }
            }
        }
    )

    with pytest.raises(ValueError, match="manifest is not registered"):
        list_provider_configs(settings=settings)