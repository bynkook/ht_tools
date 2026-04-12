from pathlib import Path
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import (
    DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF,
    DOC_SEARCH_PROVIDER_ID,
    build_mcp_event_policy,
    load_doc_search_server_config,
    load_mcp_settings,
    load_provider_config,
)
from services.mcp.doc_search_policy import DEFAULT_DOC_SEARCH_SETTINGS


@patch.dict("os.environ", {}, clear=True)
def test_load_mcp_settings_reads_nested_host_and_provider_namespaces():
    settings = load_mcp_settings(
        {
            "mcp": {
                "host": {
                    "test_mode": True,
                    "test_mode_verbose_json": False,
                    "test_mode_scenario_path": "ai_gateway/services/mcp/test_mode/scenarios/default.json",
                    "test_mode_enable_scenario_override": True,
                    "doc_search": {
                        "max_docs": 12,
                        "snippet_chars": 2000,
                        "unscoped_fanout_enabled": True,
                        "unscoped_fanout_per_category_docs": 4,
                        "unscoped_fanout_category_limit": 0,
                        "prompt_default_max_total": 11,
                        "prompt_file_fallback_max_files": 5,
                    },
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
    assert settings.host.test_mode_enable_scenario_override is True
    assert settings.host.doc_search.max_docs == 12
    assert settings.host.doc_search.snippet_chars == 2000
    assert settings.host.doc_search.unscoped_fanout_enabled is True
    assert settings.host.doc_search.unscoped_fanout_per_category_docs == 4
    assert settings.host.doc_search.unscoped_fanout_category_limit == 0
    assert settings.host.doc_search.prompt_default_max_total == 11
    assert settings.host.doc_search.prompt_file_fallback_max_files == 5
    assert settings.require_provider("internal_docs").base_url == "http://127.0.0.1:8101/mcp"
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
    assert settings.host.test_mode_enable_scenario_override is False
    assert settings.host.doc_search == DEFAULT_DOC_SEARCH_SETTINGS
    assert settings.require_provider("internal_docs").base_url == "http://127.0.0.1:8102/mcp"
    assert settings.require_provider("internal_docs").transport == "streamable_http"
    assert settings.require_provider("internal_docs").activation_rule_ref == DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF


@patch.dict("os.environ", {}, clear=True)
def test_load_mcp_settings_reads_legacy_doc_search_subsection_from_mcp_host_alias():
    settings = load_mcp_settings(
        {
            "mcp_host": {
                "test_mode": True,
                "doc_search": {
                    "max_docs": 14,
                    "snippet_chars": 1800,
                    "prompt_expand_max_total": 15,
                },
            },
            "doc_server": {
                "base_url": "http://127.0.0.1:8102/mcp",
                "kind": "remote",
            },
        }
    )

    assert settings.host.doc_search.max_docs == 14
    assert settings.host.doc_search.snippet_chars == 1800
    assert settings.host.doc_search.prompt_expand_max_total == 15


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


@patch.dict("os.environ", {}, clear=True)
def test_build_mcp_event_policy_reads_host_settings_contract():
    settings = load_mcp_settings(
        {
            "mcp": {
                "host": {
                    "test_mode": True,
                    "test_mode_verbose_json": False,
                    "test_mode_store_system_logs": False,
                    "test_mode_max_payload_chars": 1234,
                    "test_mode_visible_band_limit": 7,
                    "test_mode_raw_bytes_limit": 99,
                    "test_mode_redact_headers": True,
                },
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8105/mcp",
                        "transport": "streamable_http",
                    }
                },
            }
        }
    )

    event_policy = build_mcp_event_policy(settings.host)

    assert event_policy.verbose_json is False
    assert event_policy.persist_system_logs is False
    assert event_policy.max_payload_chars == 1234
    assert event_policy.visible_band_limit == 7
    assert event_policy.raw_bytes_limit == 99
