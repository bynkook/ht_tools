from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import (
    DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
    DOC_SEARCH_PROVIDER_ID,
    load_doc_search_server_config,
    load_mcp_settings,
    load_provider_config,
)


@patch.dict("os.environ", {}, clear=True)
def test_load_mcp_settings_reads_nested_host_and_provider_namespaces():
    settings = load_mcp_settings(
        {
            "mcp": {
                "host": {
                    "test_mode": True,
                    "test_mode_verbose_json": False,
                    "test_mode_scenario_path": "ai_gateway/services/mcp/test_mode/scenarios/default.json",
                },
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8101/mcp",
                        "transport": "streamable_http",
                        "display_name": "Internal Docs",
                        "origin_type": "local",
                    }
                },
            }
        }
    )

    assert settings.host.test_mode is True
    assert settings.host.test_mode_verbose_json is False
    assert settings.doc_server.base_url == "http://127.0.0.1:8101/mcp"
    assert settings.require_provider("internal_docs").display_name == "Internal Docs"
    assert settings.require_provider("internal_docs").origin_type == "local"
    assert settings.require_provider("internal_docs").activation_rule_ref == DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF


@patch.dict("os.environ", {}, clear=True)
def test_load_mcp_settings_preserves_legacy_host_and_doc_server_aliases():
    settings = load_mcp_settings(
        {
            "mcp_host": {
                "test_mode": True,
                "test_mode_store_system_logs": False,
            },
            "doc_server": {
                "base_url": "http://127.0.0.1:8102/mcp",
                "kind": "remote",
            },
        }
    )

    assert settings.host.test_mode is True
    assert settings.host.test_mode_store_system_logs is False
    assert settings.doc_server.base_url == "http://127.0.0.1:8102/mcp"
    assert settings.doc_server.transport == "streamable_http"
    assert settings.doc_server.activation_rule_ref == DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF


@patch.dict("os.environ", {}, clear=True)
def test_enabled_non_default_provider_requires_base_url_under_new_namespace():
    with pytest.raises(ValueError, match="missing base_url"):
        load_mcp_settings(
            {
                "mcp": {
                    "providers": {
                        "legal_cases": {
                            "enabled": True,
                            "transport": "streamable_http",
                        }
                    }
                }
            }
        )


@patch.dict("os.environ", {}, clear=True)
def test_load_provider_config_reads_specific_provider_by_id():
    config = load_provider_config(
        DOC_SEARCH_PROVIDER_ID,
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8103/mcp",
                        "transport": "streamable_http",
                        "display_name": "Docs Provider",
                    }
                }
            }
        },
    )

    assert config.provider_id == DOC_SEARCH_PROVIDER_ID
    assert config.base_url == "http://127.0.0.1:8103/mcp"
    assert config.display_name == "Docs Provider"
    assert config.activation_rule_ref == DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF


@patch.dict("os.environ", {}, clear=True)
def test_load_doc_search_server_config_remains_compatibility_alias():
    config = load_doc_search_server_config(
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8104/mcp",
                        "transport": "streamable_http",
                    }
                }
            }
        }
    )

    assert config == load_provider_config(
        DOC_SEARCH_PROVIDER_ID,
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8104/mcp",
                        "transport": "streamable_http",
                    }
                }
            }
        },
    )