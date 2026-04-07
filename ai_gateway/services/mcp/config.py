"""
MCP provider and host configuration helpers.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os

import toml

DOC_SEARCH_PROVIDER_ID = "internal_docs"
DOC_SEARCH_PROVIDER_NAME = "fastmcp-doc-search"
DOC_SEARCH_PROVIDER_TRANSPORT = "streamable_http"
DEFAULT_DOC_SERVER_URL = "http://127.0.0.1:8002/mcp"
DEFAULT_TEST_MODE_SCENARIO_PATH = "ai_gateway/services/mcp/test_mode/scenarios/default.json"

BASE_DIR = Path(__file__).resolve().parents[3]
SECRETS_PATH = BASE_DIR / "secrets.toml"


@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    name: str
    transport: str
    base_url: str
    kind: str = "remote"


@dataclass(frozen=True)
class McpHostSettings:
    test_mode: bool
    test_mode_verbose_json: bool
    test_mode_scenario_path: Path
    test_mode_discovery_on_startup: bool
    test_mode_store_system_logs: bool
    test_mode_max_payload_chars: int
    test_mode_visible_band_limit: int
    test_mode_raw_bytes_limit: int
    test_mode_redact_headers: bool
    test_mode_allow_remote_mcp: bool


@dataclass(frozen=True)
class McpEventPolicy:
    verbose_json: bool
    redact_headers: bool
    max_payload_chars: int
    persist_system_logs: bool
    visible_band_limit: int
    raw_bytes_limit: int


@dataclass(frozen=True)
class McpSettings:
    doc_server: McpServerConfig
    host: McpHostSettings


def _parse_bool(value: str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | int | None, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _resolve_scenario_path(raw_path: str) -> Path:
    scenario_path = Path(raw_path)
    if not scenario_path.is_absolute():
        scenario_path = BASE_DIR / scenario_path
    return scenario_path.resolve()


@lru_cache(maxsize=1)
def load_secrets() -> dict:
    with open(SECRETS_PATH, "r", encoding="utf-8") as handle:
        return toml.load(handle)


def load_doc_search_server_config(secrets: dict | None = None) -> McpServerConfig:
    current_secrets = load_secrets() if secrets is None else secrets
    base_url = current_secrets.get("doc_server", {}).get("base_url", DEFAULT_DOC_SERVER_URL)
    return McpServerConfig(
        server_id=DOC_SEARCH_PROVIDER_ID,
        name=DOC_SEARCH_PROVIDER_NAME,
        transport=DOC_SEARCH_PROVIDER_TRANSPORT,
        base_url=base_url,
    )


def load_mcp_host_settings(secrets: dict | None = None) -> McpHostSettings:
    current_secrets = load_secrets() if secrets is None else secrets
    host_config = current_secrets.get("mcp_host", {})

    scenario_path = os.getenv(
        "MCP_TEST_MODE_SCENARIO_PATH",
        host_config.get("test_mode_scenario_path", DEFAULT_TEST_MODE_SCENARIO_PATH),
    )
    return McpHostSettings(
        test_mode=_parse_bool(os.getenv("MCP_TEST_MODE"), _parse_bool(host_config.get("test_mode"), False)),
        test_mode_verbose_json=_parse_bool(
            os.getenv("MCP_TEST_MODE_VERBOSE_JSON"),
            _parse_bool(host_config.get("test_mode_verbose_json"), True),
        ),
        test_mode_scenario_path=_resolve_scenario_path(scenario_path),
        test_mode_discovery_on_startup=_parse_bool(
            os.getenv("MCP_TEST_MODE_DISCOVERY_ON_STARTUP"),
            _parse_bool(host_config.get("test_mode_discovery_on_startup"), True),
        ),
        test_mode_store_system_logs=_parse_bool(
            os.getenv("MCP_TEST_MODE_STORE_SYSTEM_LOGS"),
            _parse_bool(host_config.get("test_mode_store_system_logs"), True),
        ),
        test_mode_max_payload_chars=_parse_int(
            os.getenv("MCP_TEST_MODE_MAX_PAYLOAD_CHARS"),
            _parse_int(host_config.get("test_mode_max_payload_chars"), 4000),
        ),
        test_mode_visible_band_limit=_parse_int(
            os.getenv("MCP_TEST_MODE_VISIBLE_BAND_LIMIT"),
            _parse_int(host_config.get("test_mode_visible_band_limit"), 20),
        ),
        test_mode_raw_bytes_limit=_parse_int(
            os.getenv("MCP_TEST_MODE_RAW_BYTES_LIMIT"),
            _parse_int(host_config.get("test_mode_raw_bytes_limit"), 16384),
        ),
        test_mode_redact_headers=_parse_bool(
            os.getenv("MCP_TEST_MODE_REDACT_HEADERS"),
            _parse_bool(host_config.get("test_mode_redact_headers"), True),
        ),
        test_mode_allow_remote_mcp=_parse_bool(
            os.getenv("MCP_TEST_MODE_ALLOW_REMOTE_MCP"),
            _parse_bool(host_config.get("test_mode_allow_remote_mcp"), True),
        ),
    )


def load_mcp_settings(secrets: dict | None = None) -> McpSettings:
    current_secrets = load_secrets() if secrets is None else secrets
    return McpSettings(
        doc_server=load_doc_search_server_config(current_secrets),
        host=load_mcp_host_settings(current_secrets),
    )


def build_mcp_event_policy(settings: McpHostSettings) -> McpEventPolicy:
    return McpEventPolicy(
        verbose_json=settings.test_mode_verbose_json,
        redact_headers=settings.test_mode_redact_headers,
        max_payload_chars=settings.test_mode_max_payload_chars,
        persist_system_logs=settings.test_mode_store_system_logs,
        visible_band_limit=settings.test_mode_visible_band_limit,
        raw_bytes_limit=settings.test_mode_raw_bytes_limit,
    )


__all__ = [
    "DEFAULT_DOC_SERVER_URL",
    "DEFAULT_TEST_MODE_SCENARIO_PATH",
    "DOC_SEARCH_PROVIDER_ID",
    "DOC_SEARCH_PROVIDER_NAME",
    "DOC_SEARCH_PROVIDER_TRANSPORT",
    "McpEventPolicy",
    "McpHostSettings",
    "McpServerConfig",
    "McpSettings",
    "build_mcp_event_policy",
    "load_doc_search_server_config",
    "load_mcp_host_settings",
    "load_mcp_settings",
    "load_secrets",
]
