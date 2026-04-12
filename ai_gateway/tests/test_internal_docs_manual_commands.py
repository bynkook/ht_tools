import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.mcp.config import load_mcp_settings
from services.mcp.providers.internal_docs import InternalDocsProvider


def _build_provider() -> InternalDocsProvider:
    settings = load_mcp_settings(
        {
            "mcp": {
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    }
                }
            }
        }
    )
    return InternalDocsProvider(config=settings.require_provider("internal_docs"), client=SimpleNamespace())


async def _fake_list_category_catalog(self):
    return [{"name": "회의록", "doc_count": 2}]


async def _fake_list_docs_detail(self, category):
    return {"files": [{"filename": "minutes.md", "updated_at": "2026-04-08"}]}


async def _fake_search_docs(self, query, max_results, category=None):
    return SimpleNamespace(data=f"{query}:{max_results}:{category}", content=[])


async def _fake_read_doc(self, filename, category=None):
    return SimpleNamespace(data=f"{filename}:{category}", content=[])


@patch.object(InternalDocsProvider, "list_category_catalog", _fake_list_category_catalog)
@patch.object(InternalDocsProvider, "list_docs_detail", _fake_list_docs_detail)
def test_internal_docs_manual_list_renders_existing_markdown_tables():
    provider = _build_provider()

    category_result = asyncio.run(provider.execute_manual_command(action="list"))
    docs_result = asyncio.run(provider.execute_manual_command(action="list", target="회의록"))

    assert category_result["success"] is True
    assert "## MCP 카테고리 목록" in category_result["content"]
    assert "| 회의록 | 2 |" in category_result["content"]
    assert docs_result["success"] is True
    assert "## `회의록` 문서 목록" in docs_result["content"]
    assert "| minutes.md | 2026-04-08 |" in docs_result["content"]


def test_internal_docs_normalizes_legacy_doc_list_shapes():
    provider = _build_provider()

    normalized = provider._normalize_list_docs_detail_result(
        {
            "docs": [
                {
                    "name": "legacy-minutes.md",
                    "modified_at": "2026-04-09",
                }
            ]
        }
    )

    assert normalized["files"] == [
        {
            "filename": "legacy-minutes.md",
            "updated_at": "2026-04-09",
        }
    ]


@patch.object(InternalDocsProvider, "search_docs", _fake_search_docs)
@patch.object(InternalDocsProvider, "read_doc", _fake_read_doc)
@patch.object(InternalDocsProvider, "list_category_catalog", _fake_list_category_catalog)
def test_internal_docs_manual_search_and_read_preserve_text_rendering():
    provider = _build_provider()

    search_result = asyncio.run(
        provider.execute_manual_command(
            action="search",
            query="품질 관련 내용",
            session_category="회의록",
            session_provider_id="internal_docs",
            rag_enabled=True,
            max_results=7,
        )
    )
    read_result = asyncio.run(
        provider.execute_manual_command(
            action="read",
            target="회의록/minutes.md",
        )
    )

    assert search_result == {"success": True, "content": "품질 관련 내용:7:회의록"}
    assert read_result == {"success": True, "content": "minutes.md:회의록"}


@patch.object(InternalDocsProvider, "search_docs", _fake_search_docs)
@patch.object(InternalDocsProvider, "list_category_catalog", _fake_list_category_catalog)
def test_internal_docs_manual_search_ignores_session_category_when_rag_is_off():
    provider = _build_provider()

    search_result = asyncio.run(
        provider.execute_manual_command(
            action="search",
            query="안전",
            session_category="회의록",
            session_provider_id="internal_docs",
            rag_enabled=False,
            max_results=5,
        )
    )

    assert search_result == {"success": True, "content": "안전:5:None"}
