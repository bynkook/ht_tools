from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from ai_gateway.services.mcp.config import load_mcp_settings
from ai_gateway.services.mcp.host import GenericMcpHost


def _build_host() -> GenericMcpHost:
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
    return GenericMcpHost(settings)


def _fake_manifest() -> SimpleNamespace:
    return SimpleNamespace(
        capability_policy=SimpleNamespace(
            supports_rag_context=True,
            supports_search=True,
            supports_document_read=True,
            supports_category_catalog=True,
            manual_commands=("list", "search", "read"),
        )
    )


@pytest.mark.asyncio
async def test_execute_tool_action_filters_planner_internal_params_before_provider_call():
    host = _build_host()
    call_provider_action = AsyncMock(return_value={"ok": True})

    with (
        patch(
            "ai_gateway.services.mcp.host.require_provider_manifest",
            return_value=_fake_manifest(),
        ),
        patch.object(host, "_call_provider_action", call_provider_action),
    ):
        result = cast(
            dict[str, bool],
            await host.execute_tool_action(
                action="search_docs_rag",
                arguments={"query": "test", "full_read_mode": True},
            ),
        )

    assert result == {"ok": True}
    call_provider_action.assert_awaited_once_with(
        action="search_docs_rag",
        arguments={"query": "test"},
        provider_id=None,
    )
