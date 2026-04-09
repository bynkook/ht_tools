"""
Internal docs MCP provider adapter.
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
import json
import re
from typing import Any, AsyncIterator

from fastmcp import Client

from ..config import DOC_SEARCH_PROVIDER_ID, McpServerConfig, load_provider_config
from ..doc_search_policy import DOC_SEARCH_DEFAULT_MAX_DOCS, DOC_SEARCH_DEFAULT_SNIPPET_CHARS
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

    async def validate_category(self, category: str) -> dict[str, Any]:
        target = category.strip()
        if not target:
            raise ValueError("카테고리 이름을 입력하세요.")
        normalized_target = target.casefold()
        for item in await self.list_category_catalog():
            name = str(item.get("name", "")).strip()
            if name.casefold() == normalized_target:
                return item
        raise ValueError(f"카테고리를 찾을 수 없습니다: {category}")

    async def list_docs_detail(self, category: str) -> dict[str, Any]:
        raw = await self.call_tool_dict(LIST_DOCS_DETAIL_TOOL, {"category": category})
        return self._normalize_list_docs_detail_result(raw)

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
        max_docs: int | None = DOC_SEARCH_DEFAULT_MAX_DOCS,
        snippet_chars: int | None = DOC_SEARCH_DEFAULT_SNIPPET_CHARS,
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
        target: str | None = None,
        category: str | None = None,
        filename: str | None = None,
        session_category: str | None = None,
        session_provider_id: str | None = None,
        rag_enabled: bool = False,
        max_results: int = 5,
    ) -> dict[str, Any]:
        if action == "list":
            resolved_category = await self._resolve_list_category(target=target, category=category)
            if resolved_category:
                details = await self.list_docs_detail(resolved_category)
                return {"success": True, "content": self._render_doc_list(resolved_category, details)}
            categories = await self.list_category_catalog()
            return {"success": True, "content": self._render_category_list(categories)}

        if action == "search":
            resolved_query, resolved_category = await self._resolve_search_request(
                query=query,
                category=category,
                session_category=session_category,
                session_provider_id=session_provider_id,
                rag_enabled=rag_enabled,
            )
            result = await self.search_docs(query=resolved_query, max_results=max_results, category=resolved_category)
            return {"success": True, "content": self._manual_result_to_content(result)}

        if action == "read":
            resolved_filename, resolved_category = await self._resolve_read_request(
                target=target,
                filename=filename,
                category=category,
                session_category=session_category,
                session_provider_id=session_provider_id,
            )
            result = await self.read_doc(filename=resolved_filename, category=resolved_category)
            return {"success": True, "content": self._manual_result_to_content(result)}

        raise ValueError(f"지원하지 않는 MCP 명령입니다: {action}")

    async def _resolve_list_category(
        self,
        *,
        target: str | None,
        category: str | None,
    ) -> str | None:
        candidate = self._clean_text(target) or self._clean_text(category)
        if not candidate:
            return None
        matched = await self.validate_category(candidate)
        return str(matched.get("name") or candidate)

    async def _resolve_search_request(
        self,
        *,
        query: str | None,
        category: str | None,
        session_category: str | None,
        session_provider_id: str | None,
        rag_enabled: bool,
    ) -> tuple[str, str | None]:
        resolved_query = self._clean_text(query)
        if not resolved_query:
            raise ValueError("검색어를 입력하세요.")
        resolved_category = await self._resolve_manual_category(
            explicit_category=category,
            session_category=session_category,
            session_provider_id=session_provider_id,
            allow_session_category=rag_enabled,
        )
        return resolved_query, resolved_category

    async def _resolve_read_request(
        self,
        *,
        target: str | None,
        filename: str | None,
        category: str | None,
        session_category: str | None,
        session_provider_id: str | None,
    ) -> tuple[str, str | None]:
        resolved_filename = self._clean_text(filename)
        resolved_category = self._clean_text(category)
        raw_target = self._clean_text(target)

        if not resolved_filename and raw_target:
            path_match = re.match(r"^([^/\\]+)[/\\](.+)$", raw_target)
            if path_match:
                resolved_category = path_match.group(1).strip()
                resolved_filename = path_match.group(2).strip()
            else:
                resolved_filename = raw_target

        if not resolved_filename:
            raise ValueError("파일명을 입력하세요.")

        resolved_category = await self._resolve_manual_category(
            explicit_category=resolved_category,
            session_category=session_category,
            session_provider_id=session_provider_id,
            allow_session_category=True,
        )
        return resolved_filename, resolved_category

    async def _resolve_manual_category(
        self,
        *,
        explicit_category: str | None,
        session_category: str | None,
        session_provider_id: str | None,
        allow_session_category: bool,
    ) -> str | None:
        candidate = self._clean_text(explicit_category)
        if not candidate and allow_session_category and self._session_category_belongs_to_provider(
            session_category=session_category,
            session_provider_id=session_provider_id,
        ):
            candidate = self._clean_text(session_category)
        if not candidate:
            return None
        matched = await self.validate_category(candidate)
        return str(matched.get("name") or candidate)

    def _session_category_belongs_to_provider(
        self,
        *,
        session_category: str | None,
        session_provider_id: str | None,
    ) -> bool:
        return bool(
            self._clean_text(session_category)
            and self._clean_text(session_provider_id) == self.config.provider_id
        )

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _render_category_list(self, categories: list[dict[str, Any]]) -> str:
        if not categories:
            return "등록된 카테고리가 없습니다."
        rows = ["| 카테고리 | 문서 수 |", "|:---|---:|"]
        for item in categories:
            rows.append(f"| {item.get('name', '-')} | {item.get('doc_count', 0)} |")
        return "## MCP 카테고리 목록\n\n" + "\n".join(rows)

    def _render_doc_list(self, category: str, details: dict[str, Any]) -> str:
        documents = details.get("files", []) if isinstance(details.get("files"), list) else []
        if not documents:
            return f"## `{category}` 문서 목록\n\n등록된 문서를 찾지 못했습니다."
        rows = ["| 파일 | 수정일 |", "|:---|:---|"]
        for document in documents:
            rows.append(f"| {document.get('filename', '-')} | {document.get('updated_at', '-') or '-'} |")
        return f"## `{category}` 문서 목록\n\n" + "\n".join(rows)

    def _normalize_list_docs_detail_result(self, raw: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(raw) if isinstance(raw, dict) else {}
        normalized["files"] = self._coerce_doc_entries(raw)
        return normalized

    def _coerce_doc_entries(self, raw: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(raw, dict):
            return []

        entries = self._extract_doc_entries(raw)
        if not entries and isinstance(raw.get("data"), dict):
            entries = self._extract_doc_entries(raw["data"])

        normalized_entries: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            filename = (
                self._clean_text(entry.get("filename"))
                or self._clean_text(entry.get("name"))
                or self._clean_text(entry.get("path"))
                or self._clean_text(entry.get("file_path"))
            )
            if not filename:
                continue
            updated_at = (
                self._clean_text(entry.get("updated_at"))
                or self._clean_text(entry.get("modified_at"))
                or self._clean_text(entry.get("last_modified"))
            )
            normalized_entries.append(
                {
                    "filename": filename,
                    "updated_at": updated_at,
                }
            )
        return normalized_entries

    @staticmethod
    def _extract_doc_entries(payload: dict[str, Any]) -> list[Any]:
        for key in ("files", "docs", "documents"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    def _manual_result_to_content(self, result: Any) -> str:
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False, indent=2)
        return tool_result_to_text(result)


__all__ = [
    "INTERNAL_DOCS_NORMALIZER_REF",
    "INTERNAL_DOCS_POLICY_REF",
    "InternalDocsProvider",
]
