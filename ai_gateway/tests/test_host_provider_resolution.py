import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import load_mcp_settings
from services.mcp.host import GenericMcpHost


class FakeProvider:
    async def call_tool_dict(self, tool_name, tool_args):
        return {"tool_name": tool_name, "tool_args": tool_args}

    async def list_category_catalog(self):
        return [{"name": "회의록"}]

    async def validate_category(self, category):
        return {"name": category}

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


def _fake_manifest(*, supports_rag: bool = True, manual_commands=("list", "search", "read")):
    return SimpleNamespace(
        capability_policy=SimpleNamespace(
            supports_rag_context=supports_rag,
            supports_search=True,
            supports_document_read=True,
            supports_category_catalog=True,
            manual_commands=manual_commands,
        )
    )


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

    with (
        patch("services.mcp.host.connect_provider", fake_connect_provider),
        patch("services.mcp.host.require_provider_manifest", return_value=_fake_manifest()),
    ):
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
                session_category="회의록",
                session_provider_id="internal_docs",
                rag_enabled=True,
                max_results=7,
                provider_id="internal_docs",
            )
        )

    assert observed["provider_id"] == "internal_docs"
    assert observed["settings"] is host.settings
    assert result["success"] is True
    assert result["content"] == "manual:search"
    assert result["kwargs"]["query"] == "품질 관련 내용"
    assert result["kwargs"]["session_category"] == "회의록"
    assert result["kwargs"]["session_provider_id"] == "internal_docs"
    assert result["kwargs"]["rag_enabled"] is True
    assert result["kwargs"]["max_results"] == 7


def test_host_delegates_category_validation_to_provider_adapter():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        observed["settings"] = settings
        yield FakeProvider()

    with patch("services.mcp.host.connect_provider", fake_connect_provider):
        result = asyncio.run(host.validate_category("회의록"))

    assert observed["provider_id"] == "internal_docs"
    assert observed["settings"] is host.settings
    assert result == {"name": "회의록"}


def test_host_rejects_rag_search_when_manifest_disables_rag_context():
    host = _build_host()

    class FakePolicy:
        supports_rag_context = False

    class FakeManifest:
        capability_policy = FakePolicy()

    async def fail_execute_tool_action(self, **kwargs):
        raise AssertionError("execute_tool_action should not run when capability check fails")

    with (
        patch("services.mcp.host.require_provider_manifest", return_value=FakeManifest()),
        patch.object(GenericMcpHost, "execute_tool_action", fail_execute_tool_action),
    ):
        try:
            asyncio.run(host.run_rag_search(query="위약금", provider_id="internal_docs"))
        except ValueError as error:
            assert str(error) == "MCP provider does not support RAG context search: internal_docs"
        else:
            raise AssertionError("Expected ValueError for unsupported RAG context search")


def test_host_manual_command_does_not_prevalidate_category_before_provider_call():
    host = _build_host()
    observed = {}

    @asynccontextmanager
    async def fake_connect_provider(provider_id, *, settings):
        observed["provider_id"] = provider_id
        yield FakeProvider()

    async def fail_validate_category(self, category, *, provider_id=None):
        raise AssertionError("validate_category should not run before provider manual command delegation")

    with (
        patch("services.mcp.host.connect_provider", fake_connect_provider),
        patch.object(GenericMcpHost, "validate_category", fail_validate_category),
    ):
        result = asyncio.run(
            host.execute_manual_command(
                action="list",
                target="회의록",
                provider_id="internal_docs",
            )
        )

    assert observed["provider_id"] == "internal_docs"
    assert result["success"] is True


def test_host_run_rag_search_balances_unscoped_results_across_categories():
    settings = load_mcp_settings(
        {
            "mcp": {
                "host": {
                    "doc_search": {
                        "max_docs": 4,
                        "snippet_chars": 1200,
                        "unscoped_fanout_enabled": True,
                        "unscoped_fanout_per_category_docs": 2,
                        "unscoped_fanout_category_limit": 0,
                    }
                },
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    }
                },
            }
        }
    )
    host = GenericMcpHost(settings)
    observed_categories = []

    async def fake_list_category_catalog(self, *, provider_id=None):
        return [{"name": "회의록"}, {"name": "팀주간업무"}]

    async def fake_execute_tool_action(self, *, action, arguments, provider_id=None):
        observed_categories.append(arguments.get("category"))
        category = arguments.get("category")
        if category == "회의록":
            return {
                "files": [{"filename": "minutes.md", "snippet": "회의 안전 점검", "category": category}],
                "snippets": [{"filename": "minutes.md", "snippet": "회의 안전 점검", "category": category, "start": 1, "end": 10}],
            }
        if category == "팀주간업무":
            return {
                "files": [{"filename": "weekly.md", "snippet": "업무 안전 조치", "category": category}],
                "snippets": [{"filename": "weekly.md", "snippet": "업무 안전 조치", "category": category, "start": 1, "end": 10}],
            }
        raise AssertionError(f"Unexpected category: {category}")

    with (
        patch.object(GenericMcpHost, "list_category_catalog", fake_list_category_catalog),
        patch.object(GenericMcpHost, "execute_tool_action", fake_execute_tool_action),
        patch("services.mcp.host.require_provider_manifest", return_value=_fake_manifest()),
    ):
        result = asyncio.run(host.run_rag_search(query="안전", provider_id="internal_docs"))

    assert observed_categories == ["회의록", "팀주간업무"]
    assert [item["filename"] for item in result["files"]] == ["minutes.md", "weekly.md"]
    assert [item["filename"] for item in result["snippets"]] == ["minutes.md", "weekly.md"]
    assert result["retrieval_meta"]["mode"] == "category_fanout"
    assert result["retrieval_meta"]["categories_queried"] == ["회의록", "팀주간업무"]
