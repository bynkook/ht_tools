"""
Internal docs MCP provider adapter.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
from typing import Any, AsyncIterator

from fastmcp import Client

from ..config import DOC_SEARCH_PROVIDER_ID, McpServerConfig, load_provider_config
from ..result_normalizer import tool_result_to_dict, tool_result_to_text

LIST_CATEGORIES_DETAIL_TOOL = "list_categories_detail"
LIST_DOCS_DETAIL_TOOL = "list_docs_detail"
SEARCH_DOCS_TOOL = "search_docs"
SEARCH_DOCS_RAG_TOOL = "search_docs_rag"
READ_DOC_TOOL = "read_doc"
INTERNAL_DOCS_NORMALIZER_REF = "rag_context"
INTERNAL_DOCS_POLICY_REF = "internal_docs"


@dataclass(frozen=True)
class InternalDocsProvider:
    config: McpServerConfig
    client: Client

    @classmethod
    @asynccontextmanager
    async def connect_from_settings(cls) -> AsyncIterator["InternalDocsProvider"]:
        config = load_provider_config(DOC_SEARCH_PROVIDER_ID)
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

    async def execute_manual_command(
        self,
        *,
        action: str,
        query: str | None = None,
        category: str | None = None,
        filename: str | None = None,
        max_results: int = 5,
    ) -> dict[str, Any]:
        if action == "list":
            if category:
                details = await self.list_docs_detail(category)
                return {"success": True, "content": self._render_doc_list(category, details)}
            categories = await self.list_category_catalog()
            return {"success": True, "content": self._render_category_list(categories)}

        if action == "search":
            if not query or not query.strip():
                raise ValueError("검색어를 입력하세요.")
            result = await self.search_docs(query=query, max_results=max_results, category=category)
            return {"success": True, "content": self._manual_result_to_content(result)}

        if action == "read":
            if not filename or not filename.strip():
                raise ValueError("파일명을 입력하세요.")
            result = await self.read_doc(filename=filename, category=category)
            return {"success": True, "content": self._manual_result_to_content(result)}

        raise ValueError(f"지원하지 않는 MCP 명령입니다: {action}")

    def _render_category_list(self, categories: list[dict[str, Any]]) -> str:
        if not categories:
            return "등록된 카테고리가 없습니다."
        rows = ["| 카테고리 | 문서 수 |", "|:---|---:|"]
        for item in categories:
            rows.append(f"| {item.get('name', '-')} | {item.get('doc_count', 0)} |")
        return "## MCP 카테고리 목록\n\n" + "\n".join(rows)

    def _render_doc_list(self, category: str, details: dict[str, Any]) -> str:
        documents = details.get("docs", []) if isinstance(details.get("docs"), list) else []
        if not documents:
            return f"## `{category}` 문서 목록\n\n등록된 문서를 찾지 못했습니다."
        rows = ["| 파일 | 수정일 |", "|:---|:---|"]
        for document in documents:
            rows.append(f"| {document.get('filename', '-')} | {document.get('updated_at', '-') or '-'} |")
        return f"## `{category}` 문서 목록\n\n" + "\n".join(rows)

    def _manual_result_to_content(self, result: Any) -> str:
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)
        return tool_result_to_text(result)


__all__ = [
    "INTERNAL_DOCS_NORMALIZER_REF",
    "INTERNAL_DOCS_POLICY_REF",
    "InternalDocsProvider",
]
