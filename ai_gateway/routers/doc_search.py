"""
FastAPI Router: MCP Command
/mcp 슬래시 커맨드 처리 — FastMCP Doc Server 연동
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import logging
import toml
from pathlib import Path
from fastmcp import Client

from ..dependencies import verify_token

router = APIRouter()
logger = logging.getLogger(__name__)

# ht_tools/ 루트 기준: routers/ → ai_gateway/ → ht_tools/
BASE_DIR = Path(__file__).resolve().parent.parent.parent
SECRETS_PATH = BASE_DIR / "secrets.toml"


def get_doc_server_url() -> str:
    with open(SECRETS_PATH, "r", encoding="utf-8") as f:
        secrets = toml.load(f)
    return secrets.get("doc_server", {}).get("base_url", "http://127.0.0.1:8002/mcp")


class McpCommandRequest(BaseModel):
    action: str                     # "categories" | "search" | "read" | "list"
    query: Optional[str] = None     # search 시 검색어
    category: Optional[str] = None  # search/list 시 카테고리 필터
    filename: Optional[str] = None  # read 시 파일 경로
    max_results: int = 5


@router.post("", dependencies=[Depends(verify_token)])
async def mcp_command(body: McpCommandRequest):
    """
    [POST] /mcp-command

    /mcp 슬래시 커맨드 처리 엔드포인트.
    FastMCP Doc Server(포트 8002)에 연결하여 문서를 검색·조회한다.

    Actions:
    - categories: list_categories 도구 호출 — 카테고리 목록 반환
    - search:     search_docs(query, category) 도구 호출 — 문서 검색
    - read:       read_doc(filename) 도구 호출 — 문서 전체 내용 반환
    - list:       docs://{category}/list 또는 docs://categories 리소스 읽기

    Returns:
        {"success": True, "content": "..."} on success
        {"success": False, "content": "오류 메시지"} on Doc Server connection error
    """
    doc_server_url = get_doc_server_url()
    try:
        async with Client(doc_server_url) as client:

            if body.action == "categories":
                result = await client.call_tool("list_categories", {})

            elif body.action == "search":
                if not body.query:
                    raise HTTPException(status_code=400, detail="검색어(query)가 필요합니다.")
                tool_args: dict = {"query": body.query, "max_results": body.max_results}
                if body.category:
                    tool_args["category"] = body.category
                result = await client.call_tool("search_docs", tool_args)

            elif body.action == "read":
                if not body.filename:
                    raise HTTPException(status_code=400, detail="파일 경로(filename)가 필요합니다.")
                result = await client.call_tool("read_doc", {"filename": body.filename})

            elif body.action == "list":
                if body.category:
                    resource = await client.read_resource(f"docs://{body.category}/list")
                else:
                    resource = await client.read_resource("docs://categories")
                # read_resource() → list[TextResourceContents | BlobResourceContents]
                if resource and hasattr(resource[0], "text"):
                    content = resource[0].text
                else:
                    content = "문서가 없습니다."
                return {"success": True, "content": content}

            else:
                raise HTTPException(status_code=400, detail=f"알 수 없는 action: {body.action}")

        # call_tool() → CallToolResult
        # .data : 원시 Python 값 (str 반환 도구면 str)
        # .content : list[ContentBlock] (fallback)
        if result.data is not None:
            content = str(result.data)
        else:
            content = "\n".join(
                c.text for c in result.content if hasattr(c, "text")
            )
        return {"success": True, "content": content}

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("FastMCP Doc Server 오류: %s", e)
        return {
            "success": False,
            "content": (
                f"⚠️ Doc Server 연결 실패: {e}\n"
                "서버가 실행 중인지 확인하세요 (fastmcp/run_server.bat)"
            ),
        }
