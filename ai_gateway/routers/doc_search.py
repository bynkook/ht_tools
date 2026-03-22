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


class RagSearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    max_docs: int = 10
    snippet_chars: int = 1500


@router.post("/rag-search", dependencies=[Depends(verify_token)])
async def rag_search(body: RagSearchRequest):
    """
    [POST] /mcp-command/rag-search

    RAG 파이프라인 전용 검색 엔드포인트.
    FastMCP search_docs_rag 도구를 호출하여 BM25 관련성 랭킹 + 최신 우선으로
    문서 스니펫을 검색하고, LLM에 주입할 systemPrompt를 조립하여 반환한다.

    Returns:
        {
          "success": bool,
          "files": [{ "filename": str, "snippet": str, "bm25_score": float }],
          "query": str,
          "category": str | None,
          "system_prompt": str | None  # LLM systemPrompt로 바로 주입 가능
        }
    """
    doc_server_url = get_doc_server_url()
    try:
        async with Client(doc_server_url) as client:
            result = await client.call_tool("search_docs_rag", {
                "query": body.query,
                "category": body.category,
                "max_docs": body.max_docs,
                "snippet_chars": body.snippet_chars,
            })

        # search_docs_rag가 -> dict를 반환하므로 result.data가 이미 dict
        # (FastMCP 공식 권고: dict 반환 시 json.dumps/loads 불필요)
        data = result.data
        if data is None:
            raw = "\n".join(c.text for c in result.content if hasattr(c, "text"))
            import json
            data = json.loads(raw) if raw else {}

        files = data.get("files", [])

        if not files:
            return {
                "success": True,
                "files": [],
                "query": body.query,
                "category": body.category,
                "system_prompt": None,
            }

        category_label = f" ({body.category})" if body.category else " (전체)"
        doc_blocks = "\n\n---\n\n".join(
            f"📄 파일: {f['filename']}\n\n{f['snippet']}"
            for f in files
        )
        system_prompt = (
            f"당신은 사내 문서 기반 질문 답변 어시스턴트입니다.\n"
            f"아래 참고 문서{category_label}를 바탕으로 사용자의 질문에 답하세요.\n"
            f"참고 문서에 없는 내용은 '제공된 문서에서 찾을 수 없습니다'라고 솔직하게 답하세요.\n\n"
            f"=== 참고 문서 ===\n\n{doc_blocks}\n\n=================="
        )

        return {
            "success": True,
            "files": files,
            "query": body.query,
            "category": body.category,
            "system_prompt": system_prompt,
        }

    except Exception as e:
        logger.warning("RAG 검색 오류: %s", e)
        return {
            "success": False,
            "files": [],
            "query": body.query,
            "category": body.category,
            "system_prompt": None,
        }
