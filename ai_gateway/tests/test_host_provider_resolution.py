import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import load_mcp_settings
from services.mcp.host import GenericMcpHost


class FakeProvider:
    async def call_tool_dict(self, tool_name, tool_args):
        return {"tool_name": tool_name, "tool_args": tool_args}

    async def list_category_catalog(self):
        return [{"name": "회의록"}]

    async def execute_manual_command(self, **kwargs):
        return {"success": True, "content": f"manual:{kwargs['action']}", "kwargs": kwargs}


def _build_host() -> GenericMcpHost:
    settings = load_mcp_settings(
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    },
                    "legal_cases": {
                        "base_url": "http://127.0.0.1:8003/mcp",
                        "transport": "streamable_http",
                    },
                }
            }
        }
    )
    return GenericMcpHost(settings)


def test_host_defaults_to_internal_docs_provider_when_no_provider_override_is_given():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        observed["settings"] = settings
        yield FakeProvider()

    with patch("services.mcp.host.connect_provider", fake_connect_provider):
        result = asyncio.run(host.list_category_catalog())

    assert observed["provider_id"] == "internal_docs"
    assert observed["settings"] is host.settings
    assert result == [{"name": "회의록"}]


def test_host_forwards_explicit_provider_override_to_registry_connection():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        observed["settings"] = settings
        yield FakeProvider()

    with patch("services.mcp.host.connect_provider", fake_connect_provider):
        result = asyncio.run(
            host.execute_tool_action(
                action="search_docs_rag",
                arguments={"query": "품질 관련 내용"},
                provider_id="legal_cases",
            )
        )

    assert observed["provider_id"] == "legal_cases"
    assert observed["settings"] is host.settings
    assert result == {
        "tool_name": "search_docs_rag",
        "tool_args": {"query": "품질 관련 내용"},
    }


def test_host_delegates_manual_mcp_command_to_provider_adapter():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        observed["settings"] = settings
        yield FakeProvider()

    with patch("services.mcp.host.connect_provider", fake_connect_provider):
        result = asyncio.run(
            host.execute_manual_command(
                action="search",
                query="품질 관련 내용",
                max_results=7,
                provider_id="internal_docs",
            )
        )

    assert observed["provider_id"] == "internal_docs"
    assert observed["settings"] is host.settings
    assert result["success"] is True
    assert result["content"] == "manual:search"
    assert result["kwargs"]["query"] == "품질 관련 내용"
    assert result["kwargs"]["max_results"] == 7
