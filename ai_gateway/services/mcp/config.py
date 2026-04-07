"""
MCP provider configuration helpers.
"""

from dataclasses import dataclass
from pathlib import Path

import toml

DOC_SEARCH_PROVIDER_ID = "internal_docs"
DOC_SEARCH_PROVIDER_NAME = "fastmcp-doc-search"
DOC_SEARCH_PROVIDER_TRANSPORT = "streamable_http"
DEFAULT_DOC_SERVER_URL = "http://127.0.0.1:8002/mcp"

BASE_DIR = Path(__file__).resolve().parents[3]
SECRETS_PATH = BASE_DIR / "secrets.toml"


@dataclass(frozen=True)
class McpServerConfig:
    server_id: str
    name: str
    transport: str
    base_url: str
    kind: str = "remote"


def load_doc_search_server_config() -> McpServerConfig:
    with open(SECRETS_PATH, "r", encoding="utf-8") as handle:
        secrets = toml.load(handle)

    base_url = secrets.get("doc_server", {}).get("base_url", DEFAULT_DOC_SERVER_URL)
    return McpServerConfig(
        server_id=DOC_SEARCH_PROVIDER_ID,
        name=DOC_SEARCH_PROVIDER_NAME,
        transport=DOC_SEARCH_PROVIDER_TRANSPORT,
        base_url=base_url,
    )


__all__ = [
    "DEFAULT_DOC_SERVER_URL",
    "DOC_SEARCH_PROVIDER_ID",
    "DOC_SEARCH_PROVIDER_NAME",
    "DOC_SEARCH_PROVIDER_TRANSPORT",
    "McpServerConfig",
    "load_doc_search_server_config",
]
