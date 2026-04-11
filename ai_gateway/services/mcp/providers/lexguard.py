"""
LexguardProvider — MCP provider adapter for lexguard-mcp legal QA server.

lexguard-mcp is an external MCP server (separate process, separate venv).
FabriX acts only as an MCP client via fastmcp.Client.

Server endpoints:
  - Local:  http://127.0.0.1:9099/mcp
  - Remote: https://lexguard-mcp.onrender.com/mcp
"""

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator

from fastmcp import Client

from ..config import McpServerConfig, load_provider_config
from ..result_normalizer import tool_result_to_dict, tool_result_to_text

# Provider identity
LEXGUARD_PROVIDER_ID = "lexguard"
LEXGUARD_PROVIDER_NAME = "lexguard-mcp"
LEXGUARD_PROVIDER_TRANSPORT = "streamable_http"
LEXGUARD_PROVIDER_ORIGIN_TYPE = "local"
DEFAULT_LEXGUARD_SERVER_URL = "http://127.0.0.1:9099/mcp"
DEFAULT_LEXGUARD_ACTIVATION_RULE_REF = "lexguard.default"

# Tool name constants (matched to lexguard-mcp server tool definitions)
LEGAL_QA_TOOL = "legal_qa_tool"
LAW_ARTICLE_TOOL = "law_article_tool"
PRECEDENT_LOOKUP_TOOL = "precedent_lookup_tool"
DOCUMENT_ISSUE_TOOL = "document_issue_tool"
LAW_COMPARISON_TOOL = "law_comparison_tool"
INTERPRETATION_TOOL = "interpretation_tool"
ADMINISTRATIVE_APPEAL_TOOL = "administrative_appeal_tool"
CONSTITUTIONAL_DECISION_TOOL = "constitutional_decision_tool"
COMMITTEE_DECISION_TOOL = "committee_decision_tool"
SPECIAL_ADMINISTRATIVE_APPEAL_TOOL = "special_administrative_appeal_tool"
LOCAL_ORDINANCE_TOOL = "local_ordinance_tool"
ADMINISTRATIVE_RULE_TOOL = "administrative_rule_tool"

# Normalizer and policy references
LEXGUARD_NORMALIZER_REF = "legal_qa_context"
LEXGUARD_POLICY_REF = "lexguard"


@dataclass(frozen=True)
class LexguardProvider:
    config: McpServerConfig
    client: Client

    @classmethod
    @asynccontextmanager
    async def connect_from_settings(cls) -> AsyncIterator["LexguardProvider"]:
        config = load_provider_config(LEXGUARD_PROVIDER_ID)
        async with cls.connect_from_config(config) as provider:
            yield provider

    @classmethod
    @asynccontextmanager
    async def connect_from_config(
        cls, config: McpServerConfig
    ) -> AsyncIterator["LexguardProvider"]:
        async with Client(config.base_url) as client:
            yield cls(config=config, client=client)

    async def call_tool(self, tool_name: str, tool_args: dict[str, Any]) -> Any:
        return await self.client.call_tool(tool_name, tool_args)

    async def call_tool_dict(
        self, tool_name: str, tool_args: dict[str, Any]
    ) -> dict[str, Any]:
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

    async def health_check(self) -> dict[str, Any]:
        """Check server health by listing capabilities."""
        try:
            capabilities = await self.list_capabilities()
            return {
                "status": "ok",
                "provider_id": self.config.provider_id,
                "base_url": self.config.base_url,
                "tools": len(capabilities.get("tools", [])),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "status": "error",
                "provider_id": self.config.provider_id,
                "base_url": self.config.base_url,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }

    async def legal_qa(
        self,
        query: str,
        domain: str | None = None,
    ) -> Any:
        """Integrated legal QA — primary entry point for legal questions."""
        tool_args: dict[str, Any] = {"query": query}
        if domain:
            tool_args["domain"] = domain
        return await self.call_tool(LEGAL_QA_TOOL, tool_args)

    async def law_article(
        self,
        query: str,
        law_name: str | None = None,
    ) -> Any:
        """Search for law articles / statutory provisions."""
        tool_args: dict[str, Any] = {"query": query}
        if law_name:
            tool_args["law_name"] = law_name
        return await self.call_tool(LAW_ARTICLE_TOOL, tool_args)

    async def precedent_lookup(
        self,
        query: str,
        court: str | None = None,
    ) -> Any:
        """Search for court precedents / case law."""
        tool_args: dict[str, Any] = {"query": query}
        if court:
            tool_args["court"] = court
        return await self.call_tool(PRECEDENT_LOOKUP_TOOL, tool_args)

    async def document_issue(
        self,
        document_text: str,
        document_type: str | None = None,
    ) -> Any:
        """Analyze contracts or agreements for legal issues."""
        tool_args: dict[str, Any] = {"document_text": document_text}
        if document_type:
            tool_args["document_type"] = document_type
        return await self.call_tool(DOCUMENT_ISSUE_TOOL, tool_args)

    def _result_to_text(self, result: Any) -> str:
        return tool_result_to_text(result)


__all__ = [
    "DEFAULT_LEXGUARD_ACTIVATION_RULE_REF",
    "DEFAULT_LEXGUARD_SERVER_URL",
    "LEXGUARD_NORMALIZER_REF",
    "LEXGUARD_POLICY_REF",
    "LEXGUARD_PROVIDER_ID",
    "LEXGUARD_PROVIDER_NAME",
    "LEXGUARD_PROVIDER_ORIGIN_TYPE",
    "LEXGUARD_PROVIDER_TRANSPORT",
    "LexguardProvider",
]
