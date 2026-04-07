"""
Internal docs MCP provider adapter.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from fastmcp import Client

from ..config import McpServerConfig, load_doc_search_server_config
from ..result_normalizer import tool_result_to_dict

LIST_CATEGORIES_DETAIL_TOOL = "list_categories_detail"
LIST_DOCS_DETAIL_TOOL = "list_docs_detail"
SEARCH_DOCS_TOOL = "search_docs"
SEARCH_DOCS_RAG_TOOL = "search_docs_rag"
READ_DOC_TOOL = "read_doc"


@dataclass(frozen=True)
class InternalDocsProvider:
    config: McpServerConfig
    client: Client

    @classmethod
    @asynccontextmanager
    async def connect_from_settings(cls) -> AsyncIterator["InternalDocsProvider"]:
        config = load_doc_search_server_config()
        async with cls.connect_from_config(config) as provider:
            yield provider

    @classmethod
    @asynccontextmanager
    async def connect_from_config(cls, config: McpServerConfig) -> AsyncIterator["InternalDocsProvider"]:
        async with Client(config.base_url) as client:
            yield cls(config=config, client=client)

    async def call_tool(self, tool_name: str, tool_args: dict[str, Any]) -> Any:
        return await self.client.call_tool(tool_name, tool_args)

    async def call_tool_dict(self, tool_name: str, tool_args: dict[str, Any]) -> dict[str, Any]:
        result = await self.call_tool(tool_name, tool_args)
        return tool_result_to_dict(result)

    async def list_capabilities(self) -> dict[str, list[str]]:
        tools = await self.client.list_tools()
        resources = await self.client.list_resources()
        prompts = await self.client.list_prompts()
        return {
            "tools": [tool.name for tool in tools],
            "resources": [str(resource.uri) for resource in resources],
            "prompts": [prompt.name for prompt in prompts],
        }

    async def list_categories_detail(self) -> dict[str, Any]:
        return await self.call_tool_dict(LIST_CATEGORIES_DETAIL_TOOL, {})

    async def list_category_catalog(self) -> list[dict[str, Any]]:
        data = await self.list_categories_detail()
        categories = data.get("categories", [])
        return categories if isinstance(categories, list) else []

    async def list_docs_detail(self, category: str) -> dict[str, Any]:
        return await self.call_tool_dict(LIST_DOCS_DETAIL_TOOL, {"category": category})

    async def search_docs(
        self,
        query: str,
        max_results: int,
        category: str | None = None,
    ) -> Any:
        tool_args: dict[str, Any] = {"query": query, "max_results": max_results}
        if category:
            tool_args["category"] = category
        return await self.call_tool(SEARCH_DOCS_TOOL, tool_args)

    async def read_doc(self, filename: str, category: str | None = None) -> Any:
        tool_args: dict[str, Any] = {"filename": filename}
        if category:
            tool_args["category"] = category
        return await self.call_tool(READ_DOC_TOOL, tool_args)

    async def search_docs_rag(
        self,
        query: str,
        category: str | None = None,
        filename_filter: str | None = None,
        max_docs: int = 10,
        snippet_chars: int = 1500,
    ) -> dict[str, Any]:
        tool_args: dict[str, Any] = {
            "query": query,
            "max_docs": max_docs,
            "snippet_chars": snippet_chars,
        }
        if category:
            tool_args["category"] = category
        if filename_filter:
            tool_args["filename_filter"] = filename_filter
        return await self.call_tool_dict(SEARCH_DOCS_RAG_TOOL, tool_args)


__all__ = ["InternalDocsProvider"]
