from pathlib import Path
import sys
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ai_gateway.dependencies import verify_token
from ai_gateway.routers.doc_search import router
from ai_gateway.services.mcp.config import load_mcp_settings
from ai_gateway.services.mcp.host import GenericMcpHost


def _build_test_client(*, test_mode: bool = False) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/mcp-command")
    app.dependency_overrides[verify_token] = lambda: None
    app.state.mcp_settings = load_mcp_settings(
        {
            "mcp": {
                "host": {
                    "test_mode": test_mode,
                },
                "providers": {
                    "internal_docs": {
                        "base_url": "http://127.0.0.1:8002/mcp",
                        "transport": "streamable_http",
                    }
                }
            }
        }
    )
    return TestClient(app)


def test_mcp_command_forwards_provider_override_to_host():
    observed = {}

    async def fake_execute_manual_command(self, **kwargs):
        observed.update(kwargs)
        return {"success": True, "content": "ok"}

    with patch.object(GenericMcpHost, "execute_manual_command", fake_execute_manual_command):
        client = _build_test_client()
        response = client.post(
            "/mcp-command",
            json={
                "action": "search",
                "query": "품질 관련 내용",
                "provider_id": "legal_cases",
            },
        )

    assert response.status_code == 200
    assert observed["provider_id"] == "legal_cases"
    assert observed["query"] == "품질 관련 내용"


def test_mcp_command_forwards_manual_command_context_to_host():
    observed = {}

    async def fake_execute_manual_command(self, **kwargs):
        observed.update(kwargs)
        return {"success": True, "content": "ok"}

    with patch.object(GenericMcpHost, "execute_manual_command", fake_execute_manual_command):
        client = _build_test_client()
        response = client.post(
            "/mcp-command",
            json={
                "action": "read",
                "target": "회의록/260330 [회의록] 사업부 주간 업무 공유회 (3월4주).md",
                "session_category": "회의록",
                "session_provider_id": "internal_docs",
                "rag_enabled": False,
            },
        )

    assert response.status_code == 200
    assert observed["target"] == "회의록/260330 [회의록] 사업부 주간 업무 공유회 (3월4주).md"
    assert observed["session_category"] == "회의록"
    assert observed["session_provider_id"] == "internal_docs"
    assert observed["rag_enabled"] is False


def test_mcp_command_route_keeps_same_manual_command_contract_in_test_and_normal_mode():
    observed_calls = []

    async def fake_execute_manual_command(self, **kwargs):
        observed_calls.append(kwargs)
        return {"success": True, "content": "ok"}

    with patch.object(GenericMcpHost, "execute_manual_command", fake_execute_manual_command):
        for test_mode in (False, True):
            client = _build_test_client(test_mode=test_mode)
            response = client.post(
                "/mcp-command",
                json={
                    "action": "list",
                    "target": "회의록",
                    "provider_id": "internal_docs",
                },
            )
            assert response.status_code == 200

    assert observed_calls == [
        {"action": "list", "query": None, "target": "회의록", "category": None, "filename": None, "session_category": None, "session_provider_id": None, "rag_enabled": False, "max_results": 5, "provider_id": "internal_docs"},
        {"action": "list", "query": None, "target": "회의록", "category": None, "filename": None, "session_category": None, "session_provider_id": None, "rag_enabled": False, "max_results": 5, "provider_id": "internal_docs"},
    ]


def test_validate_category_returns_bad_request_for_invalid_provider_override():
    async def fake_validate_category(self, category, *, provider_id=None):
        raise ValueError(f"Unknown MCP provider: {provider_id}")

    with patch.object(GenericMcpHost, "validate_category", fake_validate_category):
        client = _build_test_client()
        response = client.post(
            "/mcp-command/validate-category",
            json={
                "category": "회의록",
                "provider_id": "legal_cases",
            },
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unknown MCP provider: legal_cases"
