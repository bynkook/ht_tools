"""
MCP provider and host configuration helpers.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import os

import toml

from .doc_search_policy import DEFAULT_DOC_SEARCH_SETTINGS, McpDocSearchSettings

logger = logging.getLogger(__name__)

DOC_SEARCH_PROVIDER_ID = "internal_docs"
DOC_SEARCH_PROVIDER_NAME = "fastmcp-doc-search"
DOC_SEARCH_PROVIDER_TRANSPORT = "streamable_http"
DOC_SEARCH_PROVIDER_ORIGIN_TYPE = "local"
DEFAULT_DOC_SERVER_URL = "http://127.0.0.1:8002/mcp"
DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF = "internal_docs.default"
DEFAULT_TEST_MODE_SCENARIO_PATH = (
    "ai_gateway/services/mcp/test_mode/scenarios/default.json"
)

BASE_DIR = Path(__file__).resolve().parents[3]
SECRETS_PATH = BASE_DIR / "secrets.toml"


@dataclass(frozen=True)
class McpServerConfig:
    provider_id: str
    display_name: str
    transport: str
    base_url: str
    kind: str = "remote"
    enabled: bool = True
    origin_type: str = "remote"
    activation_rule_ref: str | None = None
    install_profile: str | None = None
    connection_profile: str | None = None

    @property
    def server_id(self) -> str:
        return self.provider_id

    @property
    def name(self) -> str:
        return self.display_name


@dataclass(frozen=True)
class McpHostSettings:
    test_mode: bool
    test_mode_verbose_json: bool
    test_mode_scenario_path: Path
    test_mode_enable_scenario_override: bool
    test_mode_discovery_on_startup: bool
    test_mode_store_system_logs: bool
    test_mode_max_payload_chars: int
    test_mode_visible_band_limit: int
    test_mode_raw_bytes_limit: int
    test_mode_redact_headers: bool
    test_mode_allow_remote_mcp: bool
    doc_search: McpDocSearchSettings


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
    host: McpHostSettings
    providers: dict[str, McpServerConfig]

    def get_provider(self, provider_id: str) -> McpServerConfig | None:
        provider = self.providers.get(provider_id)
        if provider is None or not provider.enabled:
            return None
        return provider

    def require_provider(self, provider_id: str) -> McpServerConfig:
        provider = self.providers.get(provider_id)
        if provider is None:
            raise ValueError(f"Unknown MCP provider: {provider_id}")
        if not provider.enabled:
            raise ValueError(f"Disabled MCP provider: {provider_id}")
        return provider

    def enabled_provider_configs(self) -> list[McpServerConfig]:
        return [provider for provider in self.providers.values() if provider.enabled]


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
    except (TypeError, ValueError) as exc:
        logger.warning(
            "MCP config: failed to parse int value %r (using default %r): %s",
            value,
            default,
            exc,
        )
        return default


def _parse_non_negative_int(value: str | int | None, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else default
    except (TypeError, ValueError) as exc:
        logger.warning(
            "MCP config: failed to parse int value %r (using default %r): %s",
            value,
            default,
            exc,
        )
        return default


def _resolve_scenario_path(raw_path: str) -> Path:
    scenario_path = Path(raw_path)
    if not scenario_path.is_absolute():
        scenario_path = BASE_DIR / scenario_path
    return scenario_path.resolve()


def _coerce_section(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _clean_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mcp_root(secrets: dict) -> dict:
    return _coerce_section(secrets.get("mcp"))


def _host_section(secrets: dict) -> dict:
    host_section = _coerce_section(_mcp_root(secrets).get("host"))
    if host_section:
        return host_section
    return _coerce_section(secrets.get("mcp_host"))


def _doc_search_section(host_config: dict) -> dict:
    return _coerce_section(host_config.get("doc_search"))


def _provider_sections(secrets: dict) -> dict:
    return _coerce_section(_mcp_root(secrets).get("providers"))


def _legacy_internal_docs_section(secrets: dict) -> dict:
    legacy_doc_server = _coerce_section(secrets.get("doc_server"))
    return {
        "display_name": DOC_SEARCH_PROVIDER_NAME,
        "transport": DOC_SEARCH_PROVIDER_TRANSPORT,
        "base_url": legacy_doc_server.get("base_url", DEFAULT_DOC_SERVER_URL),
        "kind": legacy_doc_server.get("kind", "remote"),
        "enabled": legacy_doc_server.get("enabled", True),
        "origin_type": legacy_doc_server.get(
            "origin_type", DOC_SEARCH_PROVIDER_ORIGIN_TYPE
        ),
        "activation_rule_ref": legacy_doc_server.get(
            "activation_rule_ref", DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF
        ),
        "install_profile": legacy_doc_server.get("install_profile"),
        "connection_profile": legacy_doc_server.get("connection_profile"),
    }


@lru_cache(maxsize=1)
def load_secrets() -> dict:
    with open(SECRETS_PATH, "r", encoding="utf-8") as handle:
        return toml.load(handle)


def _build_provider_config(
    provider_id: str, raw_config: dict, *, legacy_alias: dict | None = None
) -> McpServerConfig:
    merged = dict(legacy_alias or {})
    merged.update(_coerce_section(raw_config))

    enabled = _parse_bool(merged.get("enabled"), True)
    display_name = _clean_optional_text(
        merged.get("display_name") or merged.get("name")
    )
    transport = _clean_optional_text(merged.get("transport"))
    base_url = _clean_optional_text(merged.get("base_url"))
    kind = _clean_optional_text(merged.get("kind")) or "remote"
    origin_type = _clean_optional_text(merged.get("origin_type"))
    activation_rule_ref = _clean_optional_text(merged.get("activation_rule_ref"))
    install_profile = _clean_optional_text(merged.get("install_profile"))
    connection_profile = _clean_optional_text(merged.get("connection_profile"))

    if provider_id == DOC_SEARCH_PROVIDER_ID:
        display_name = display_name or DOC_SEARCH_PROVIDER_NAME
        transport = transport or DOC_SEARCH_PROVIDER_TRANSPORT
        base_url = base_url or DEFAULT_DOC_SERVER_URL
        origin_type = origin_type or DOC_SEARCH_PROVIDER_ORIGIN_TYPE
        activation_rule_ref = (
            activation_rule_ref or DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF
        )
    else:
        display_name = display_name or provider_id
        origin_type = origin_type or kind

    if enabled and not transport:
        raise ValueError(f"Enabled MCP provider '{provider_id}' is missing transport")
    if enabled and not base_url:
        raise ValueError(f"Enabled MCP provider '{provider_id}' is missing base_url")

    return McpServerConfig(
        provider_id=provider_id,
        display_name=display_name,
        transport=transport or "",
        base_url=base_url or "",
        kind=kind,
        enabled=enabled,
        origin_type=origin_type,
        activation_rule_ref=activation_rule_ref,
        install_profile=install_profile,
        connection_profile=connection_profile,
    )


def load_provider_configs(secrets: dict | None = None) -> dict[str, McpServerConfig]:
    current_secrets = load_secrets() if secrets is None else secrets
    provider_sections = _provider_sections(current_secrets)
    provider_configs: dict[str, McpServerConfig] = {}

    for provider_id, raw_config in provider_sections.items():
        if not isinstance(raw_config, dict):
            raise ValueError(f"MCP provider '{provider_id}' settings must be an object")
        legacy_alias = (
            _legacy_internal_docs_section(current_secrets)
            if provider_id == DOC_SEARCH_PROVIDER_ID
            else None
        )
        provider_configs[provider_id] = _build_provider_config(
            provider_id,
            raw_config,
            legacy_alias=legacy_alias,
        )

    if DOC_SEARCH_PROVIDER_ID not in provider_configs:
        provider_configs[DOC_SEARCH_PROVIDER_ID] = _build_provider_config(
            DOC_SEARCH_PROVIDER_ID,
            {},
            legacy_alias=_legacy_internal_docs_section(current_secrets),
        )

    return provider_configs


def load_provider_config(
    provider_id: str, secrets: dict | None = None
) -> McpServerConfig:
    provider_configs = load_provider_configs(secrets)
    if provider_id not in provider_configs:
        raise ValueError(f"Unknown MCP provider: {provider_id}")
    return provider_configs[provider_id]


def load_doc_search_server_config(secrets: dict | None = None) -> McpServerConfig:
    return load_provider_config(DOC_SEARCH_PROVIDER_ID, secrets)


def load_mcp_host_settings(secrets: dict | None = None) -> McpHostSettings:
    current_secrets = load_secrets() if secrets is None else secrets
    host_config = _host_section(current_secrets)
    doc_search_config = _doc_search_section(host_config)

    scenario_path = os.getenv(
        "MCP_TEST_MODE_SCENARIO_PATH",
        host_config.get("test_mode_scenario_path", DEFAULT_TEST_MODE_SCENARIO_PATH),
    )
    return McpHostSettings(
        test_mode=_parse_bool(
            os.getenv("MCP_TEST_MODE"), _parse_bool(host_config.get("test_mode"), False)
        ),
        test_mode_verbose_json=_parse_bool(
            os.getenv("MCP_TEST_MODE_VERBOSE_JSON"),
            _parse_bool(host_config.get("test_mode_verbose_json"), True),
        ),
        test_mode_scenario_path=_resolve_scenario_path(scenario_path),
        test_mode_enable_scenario_override=_parse_bool(
            os.getenv("MCP_TEST_MODE_ENABLE_SCENARIO_OVERRIDE"),
            _parse_bool(host_config.get("test_mode_enable_scenario_override"), False),
        ),
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
            _parse_int(host_config.get("test_mode_visible_band_limit"), 50),
        ),
        test_mode_raw_bytes_limit=_parse_int(
            os.getenv("MCP_TEST_MODE_RAW_BYTES_LIMIT"),
            _parse_int(host_config.get("test_mode_raw_bytes_limit"), 4096),
        ),
        test_mode_redact_headers=_parse_bool(
            os.getenv("MCP_TEST_MODE_REDACT_HEADERS"),
            _parse_bool(host_config.get("test_mode_redact_headers"), True),
        ),
        test_mode_allow_remote_mcp=_parse_bool(
            os.getenv("MCP_TEST_MODE_ALLOW_REMOTE_MCP"),
            _parse_bool(host_config.get("test_mode_allow_remote_mcp"), False),
        ),
        doc_search=McpDocSearchSettings(
            max_docs=_parse_int(
                doc_search_config.get("max_docs"), DEFAULT_DOC_SEARCH_SETTINGS.max_docs
            ),
            snippet_chars=_parse_int(
                doc_search_config.get("snippet_chars"),
                DEFAULT_DOC_SEARCH_SETTINGS.snippet_chars,
            ),
            unscoped_fanout_enabled=_parse_bool(
                doc_search_config.get("unscoped_fanout_enabled"),
                DEFAULT_DOC_SEARCH_SETTINGS.unscoped_fanout_enabled,
            ),
            unscoped_fanout_per_category_docs=_parse_int(
                doc_search_config.get("unscoped_fanout_per_category_docs"),
                DEFAULT_DOC_SEARCH_SETTINGS.unscoped_fanout_per_category_docs,
            ),
            unscoped_fanout_category_limit=_parse_non_negative_int(
                doc_search_config.get("unscoped_fanout_category_limit"),
                DEFAULT_DOC_SEARCH_SETTINGS.unscoped_fanout_category_limit,
            ),
            prompt_max_per_doc=_parse_int(
                doc_search_config.get("prompt_max_per_doc"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_max_per_doc,
            ),
            prompt_compact_max_total=_parse_int(
                doc_search_config.get("prompt_compact_max_total"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_compact_max_total,
            ),
            prompt_compact_max_total_chars=_parse_int(
                doc_search_config.get("prompt_compact_max_total_chars"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_compact_max_total_chars,
            ),
            prompt_default_max_total=_parse_int(
                doc_search_config.get("prompt_default_max_total"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_default_max_total,
            ),
            prompt_default_max_total_chars=_parse_int(
                doc_search_config.get("prompt_default_max_total_chars"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_default_max_total_chars,
            ),
            prompt_expand_max_total=_parse_int(
                doc_search_config.get("prompt_expand_max_total"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_expand_max_total,
            ),
            prompt_expand_max_total_chars=_parse_int(
                doc_search_config.get("prompt_expand_max_total_chars"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_expand_max_total_chars,
            ),
            prompt_file_filter_max_per_doc=_parse_int(
                doc_search_config.get("prompt_file_filter_max_per_doc"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_file_filter_max_per_doc,
            ),
            prompt_file_filter_max_total=_parse_int(
                doc_search_config.get("prompt_file_filter_max_total"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_file_filter_max_total,
            ),
            prompt_file_filter_max_total_chars=_parse_int(
                doc_search_config.get("prompt_file_filter_max_total_chars"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_file_filter_max_total_chars,
            ),
            prompt_file_fallback_max_files=_parse_int(
                doc_search_config.get("prompt_file_fallback_max_files"),
                DEFAULT_DOC_SEARCH_SETTINGS.prompt_file_fallback_max_files,
            ),
        ),
    )


def load_mcp_settings(secrets: dict | None = None) -> McpSettings:
    current_secrets = load_secrets() if secrets is None else secrets
    return McpSettings(
        host=load_mcp_host_settings(current_secrets),
        providers=load_provider_configs(current_secrets),
    )


def build_mcp_event_policy(
    host_settings: McpHostSettings | None = None,
) -> McpEventPolicy:
    resolved_host_settings = host_settings or load_mcp_settings().host
    return McpEventPolicy(
        verbose_json=resolved_host_settings.test_mode_verbose_json,
        redact_headers=resolved_host_settings.test_mode_redact_headers,
        max_payload_chars=resolved_host_settings.test_mode_max_payload_chars,
        persist_system_logs=resolved_host_settings.test_mode_store_system_logs,
        visible_band_limit=resolved_host_settings.test_mode_visible_band_limit,
        raw_bytes_limit=resolved_host_settings.test_mode_raw_bytes_limit,
    )


__all__ = [
    "DEFAULT_INTERNAL_DOCS_ACTIVATION_RULE_REF",
    "DOC_SEARCH_PROVIDER_ID",
    "DOC_SEARCH_PROVIDER_NAME",
    "DOC_SEARCH_PROVIDER_ORIGIN_TYPE",
    "DOC_SEARCH_PROVIDER_TRANSPORT",
    "McpEventPolicy",
    "McpHostSettings",
    "McpServerConfig",
    "McpSettings",
    "build_mcp_event_policy",
    "load_doc_search_server_config",
    "load_mcp_host_settings",
    "load_mcp_settings",
    "load_provider_config",
    "load_provider_configs",
]
