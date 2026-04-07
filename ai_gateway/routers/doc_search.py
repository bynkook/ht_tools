"""
FastAPI Router: MCP Command
/mcp 슬래시 커맨드 처리 — FastMCP Doc Server 연동
"""
import logging

from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from ..dependencies import verify_token
from ..services.mcp import GenericMcpHost

router = APIRouter()
logger = logging.getLogger(__name__)
host = GenericMcpHost()


class McpCommandRequest(BaseModel):
    action: str                       # "search" | "read" | "list"
    query: str | None = None          # search 시 검색어
    category: str | None = None       # search/list 시 카테고리 필터
    filename: str | None = None       # read 시 파일 경로
    max_results: int = 5


class ValidateCategoryRequest(BaseModel):
    category: str
async def _require_existing_category(requested: str) -> dict[str, Any]:
    """
    `/mcp set`와 `/mcp list`가 동일한 backend catalog를 참조하도록 강제한다.

    invalid category는 RAG 무검색 결과와 다른 오류이므로, 선택 단계에서 즉시 차단한다.
    """
    return await host.validate_category(requested)


@router.post("/validate-category", dependencies=[Depends(verify_token)])
async def validate_category(body: ValidateCategoryRequest):
    """`/mcp set` 전용 category validation 엔드포인트."""
    try:
        matched = await _require_existing_category(body.category)
        return {
            "success": True,
            "category": matched.get("name"),
            "doc_count": matched.get("doc_count", 0),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("카테고리 검증 오류: %s", e)
        raise HTTPException(status_code=502, detail=f"카테고리 검증 실패: {e}")


@router.post("", dependencies=[Depends(verify_token)])
async def mcp_command(body: McpCommandRequest):
    """
    [POST] /mcp-command

    /mcp 슬래시 커맨드 처리 엔드포인트.
    FastMCP Doc Server(포트 8002)에 연결하여 문서를 검색·조회한다.

    Actions:
    - search:     search_docs(query, category) 도구 호출 — 문서 검색
    - read:       read_doc(filename) 도구 호출 — 문서 전체 내용 반환
    - list:       list_categories_detail() 또는 list_docs_detail(category) 도구 호출
                  카테고리 목록(문서 수 포함) 또는 파일 목록(최종 수정일 포함) 마크다운 표 반환

    Returns:
        {"success": True, "content": "..."} on success
        {"success": False, "content": "오류 메시지"} on Doc Server connection error
    """
    try:
        return await host.execute_manual_command(
            action=body.action,
            query=body.query,
            category=body.category,
            filename=body.filename,
            max_results=body.max_results,
        )

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
    category: str | None = None
    filename_filter: str | None = None  # @<파일명> 문법용: 특정 파일로 검색 제한
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
          "snippets": [{ "filename": str, "snippet": str, "snippet_score": float }],
          "query": str,
          "category": str | None,
          "system_prompt": str | None  # LLM systemPrompt로 바로 주입 가능
        }
    """
    try:
        data = await host.run_rag_search(
            query=body.query,
            category=body.category,
            filename_filter=body.filename_filter,
            max_docs=body.max_docs,
            snippet_chars=body.snippet_chars,
        )

        prompt_chars = len(data.get("system_prompt") or "")
        prompt_tokens_est = prompt_chars // 2
        logger.info(
            "RAG prompt budget — query=%r category=%s snippets=%d chars=%d tokens≈%d",
            body.query,
            body.category or "all",
            len(data.get("snippets") or []) if data.get("snippets") else len((data.get("files") or [])[:4]),
            prompt_chars,
            prompt_tokens_est,
        )
        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("RAG 검색 오류: %s", e)
        return {
            "success": False,
            "files": [],
            "snippets": [],
            "query": body.query,
            "category": body.category,
            "system_prompt": None,
        }
