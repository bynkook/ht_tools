"""
FastAPI Router: MCP Command
/mcp 슬래시 커맨드 처리 — configured MCP provider host 연동
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..dependencies import verify_token
from ..services.mcp import GenericMcpHost
from ..services.mcp.doc_search_policy import DOC_SEARCH_FILE_FALLBACK_MAX_FILES

router = APIRouter()
logger = logging.getLogger(__name__)


class McpCommandRequest(BaseModel):
    action: str                       # "search" | "read" | "list"
    query: str | None = None          # search 시 검색어
    category: str | None = None       # search/list 시 카테고리 필터
    filename: str | None = None       # read 시 파일 경로
    max_results: int = 5
    provider_id: str | None = None


class ValidateCategoryRequest(BaseModel):
    category: str
    provider_id: str | None = None


class RagSearchRequest(BaseModel):
    query: str
    category: str | None = None
    filename_filter: str | None = None  # @<파일명> 문법용: 특정 파일로 검색 제한
    max_docs: int | None = None
    snippet_chars: int | None = None
    provider_id: str | None = None


def _configured_host(request: Request) -> GenericMcpHost:
    return GenericMcpHost(request.app.state.mcp_settings)


@router.post("/validate-category", dependencies=[Depends(verify_token)])
async def validate_category(body: ValidateCategoryRequest, request: Request):
    """`/mcp set` 전용 category validation 엔드포인트."""
    try:
        matched = await _configured_host(request).validate_category(
            body.category,
            provider_id=body.provider_id,
        )
        return {
            "success": True,
            "category": matched.get("name"),
            "doc_count": matched.get("doc_count", 0),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        logger.warning("카테고리 검증 오류: %s", error)
        raise HTTPException(status_code=502, detail=f"카테고리 검증 실패: {error}") from error


@router.post("", dependencies=[Depends(verify_token)])
async def mcp_command(body: McpCommandRequest, request: Request):
    """
    [POST] /mcp-command

    /mcp 슬래시 커맨드 처리 엔드포인트.
    현재 선택된 MCP provider 또는 명시 override provider에 연결하여 문서를 검색·조회한다.
    """
    try:
        return await _configured_host(request).execute_manual_command(
            action=body.action,
            query=body.query,
            category=body.category,
            filename=body.filename,
            max_results=body.max_results,
            provider_id=body.provider_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        logger.warning("MCP provider command 오류: %s", error)
        return {
            "success": False,
            "content": f"⚠️ MCP provider 연결 실패: {error}",
        }


@router.post("/rag-search", dependencies=[Depends(verify_token)])
async def rag_search(body: RagSearchRequest, request: Request):
    """
    [POST] /mcp-command/rag-search

    RAG 파이프라인 전용 검색 엔드포인트.
    MCP search_docs_rag 도구를 호출하여 BM25 관련성 랭킹 + 최신 우선으로
    문서 스니펫을 검색하고, LLM에 주입할 systemPrompt를 조립하여 반환한다.
    """
    try:
        data = await _configured_host(request).run_rag_search(
            query=body.query,
            category=body.category,
            filename_filter=body.filename_filter,
            max_docs=body.max_docs,
            snippet_chars=body.snippet_chars,
            provider_id=body.provider_id,
        )

        prompt_chars = len(data.get("system_prompt") or "")
        prompt_tokens_est = prompt_chars // 2
        logger.info(
            "RAG prompt budget — query=%r provider=%s category=%s snippets=%d chars=%d tokens≈%d",
            body.query,
            body.provider_id or "default",
            body.category or "all",
            len(data.get("snippets") or [])
            if data.get("snippets")
            else len((data.get("files") or [])[:DOC_SEARCH_FILE_FALLBACK_MAX_FILES]),
            prompt_chars,
            prompt_tokens_est,
        )
        return data
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except HTTPException:
        raise
    except Exception as error:
        logger.warning("RAG 검색 오류: %s", error)
        return {
            "success": False,
            "files": [],
            "snippets": [],
            "query": body.query,
            "category": body.category,
            "system_prompt": None,
        }
