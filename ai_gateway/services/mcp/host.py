"""
Generic MCP host service for FabriX Chat Phase 1.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from .context_merge import build_multi_file_system_prompt
from .intent_router import route_chat_query, split_mention_target
from .rag_context import build_rag_response
from .registry import connect_provider
from .result_normalizer import tool_result_to_text


@dataclass(frozen=True)
class McpChatResolution:
    route: str
    system_prompt: str | None
    missing_mentions: list[str]


class GenericMcpHost:
    async def list_category_catalog(self) -> list[dict[str, Any]]:
        async with connect_provider() as provider:
            return await provider.list_category_catalog()

    async def validate_category(self, requested: str) -> dict[str, Any]:
        categories = await self.list_category_catalog()
        normalized_requested = requested.strip()
        for category in categories:
            if category.get("name") == normalized_requested:
                return category
        raise HTTPException(
            status_code=400,
            detail=f"존재하지 않는 카테고리입니다: {requested}",
        )

    async def execute_manual_command(
        self,
        *,
        action: str,
        query: str | None = None,
        category: str | None = None,
        filename: str | None = None,
        max_results: int = 5,
    ) -> dict[str, Any]:
        async with connect_provider() as provider:
            if action == "search":
                if not query:
                    raise HTTPException(status_code=400, detail="검색어(query)가 필요합니다.")
                if category:
                    await self.validate_category(category)
                result = await provider.search_docs(
                    query=query,
                    max_results=max_results,
                    category=category,
                )
                return {"success": True, "content": tool_result_to_text(result)}

            if action == "read":
                if not filename:
                    raise HTTPException(status_code=400, detail="파일 경로(filename)가 필요합니다.")
                if category:
                    await self.validate_category(category)
                result = await provider.read_doc(filename=filename, category=category)
                return {"success": True, "content": tool_result_to_text(result)}

            if action == "list":
                if category:
                    await self.validate_category(category)
                    data = await provider.list_docs_detail(category)
                    error = data.get("error")
                    if error:
                        return {"success": True, "content": f"⚠️ {error}"}
                    files = data.get("files", [])
                    if not files:
                        return {"success": True, "content": f"**'{category}'** 카테고리에 문서가 없습니다."}

                    lines = [
                        f"## 📁 `{category}` 문서 목록 ({len(files)}개)",
                        "",
                        "| 파일명 | 최종 수정일 |",
                        "|:---|:---|",
                    ]
                    for file_item in files:
                        lines.append(f"| `{file_item['filename']}` | {file_item['last_modified']} |")
                    return {"success": True, "content": "\n".join(lines)}

                data = await provider.list_categories_detail()
                categories = data.get("categories", [])
                if not categories:
                    return {"success": True, "content": "등록된 카테고리가 없습니다."}

                total_docs = sum(category_item["doc_count"] for category_item in categories)
                lines = [
                    f"## 📚 문서 카테고리 목록  ({len(categories)}개 카테고리 · 총 {total_docs}개 문서)",
                    "",
                    "| 카테고리 | 문서 수 |",
                    "|:---|---:|",
                ]
                for category_item in categories:
                    lines.append(f"| {category_item['name']} | {category_item['doc_count']} |")
                return {"success": True, "content": "\n".join(lines)}

        raise HTTPException(status_code=400, detail=f"알 수 없는 action: {action}")

    async def run_rag_search(
        self,
        *,
        query: str,
        category: str | None = None,
        filename_filter: str | None = None,
        max_docs: int = 10,
        snippet_chars: int = 1500,
    ) -> dict[str, Any]:
        async with connect_provider() as provider:
            if category:
                await self.validate_category(category)
            raw_data = await provider.search_docs_rag(
                query=query,
                category=category,
                filename_filter=filename_filter,
                max_docs=max_docs,
                snippet_chars=snippet_chars,
            )
        return build_rag_response(
            query=query,
            category=category,
            filename_filter=filename_filter,
            data=raw_data,
        )

    async def build_chat_resolution(
        self,
        *,
        user_text: str,
        active_category: str | None = None,
        rag_enabled: bool = False,
    ) -> McpChatResolution:
        decision = route_chat_query(user_text, rag_enabled)
        if decision.route == "chat_only":
            return McpChatResolution(route=decision.route, system_prompt=None, missing_mentions=[])

        if decision.route == "rag_search":
            data = await self.run_rag_search(
                query=decision.clean_query,
                category=active_category,
            )
            return McpChatResolution(
                route=decision.route,
                system_prompt=data.get("system_prompt"),
                missing_mentions=[],
            )

        resolved_mentions: list[dict[str, Any]] = []
        missing_mentions: list[str] = []
        clean_query = decision.clean_query

        for raw_target in decision.mentions:
            category, filename_filter = split_mention_target(raw_target, active_category)
            data = await self.run_rag_search(
                query=clean_query or raw_target,
                category=category,
                filename_filter=filename_filter,
            )
            if data.get("error"):
                missing_mentions.append(raw_target)
                continue

            resolved_mentions.append(
                {
                    "filename": raw_target,
                    "snippets": data.get("snippets", []),
                    "system_prompt": data.get("system_prompt"),
                }
            )

        if not resolved_mentions:
            quoted_mentions = ", ".join(f'@"{name}"' for name in missing_mentions)
            raise HTTPException(
                status_code=404,
                detail=f"파일을 찾을 수 없습니다: {quoted_mentions}",
            )

        if len(resolved_mentions) == 1:
            return McpChatResolution(
                route=decision.route,
                system_prompt=resolved_mentions[0].get("system_prompt"),
                missing_mentions=missing_mentions,
            )

        return McpChatResolution(
            route=decision.route,
            system_prompt=build_multi_file_system_prompt(resolved_mentions),
            missing_mentions=missing_mentions,
        )


__all__ = ["GenericMcpHost", "McpChatResolution"]
