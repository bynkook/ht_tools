"""
FastAPI Router: MCP Command
/mcp 슬래시 커맨드 처리 — configured MCP provider host 연동
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from ..dependencies import verify_token
from ..services.mcp import GenericMcpHost
from ..services.mcp.doc_search_policy import DOC_SEARCH_FILE_FALLBACK_MAX_FILES

router = APIRouter()
logger = logging.getLogger(__name__)

# Path traversal 방지: .. 또는 절대경로 패턴 검출
_UNSAFE_PATH_RE = re.compile(r"\.\.|^[/\\]|[<>:\"|?*\x00-\x1f]")


def _validate_filename(value: str | None, field_name: str = "filename") -> str | None:
    """파일명/경로에 path traversal 패턴이 포함되어 있으면 ValueError를 발생시킨다."""
    if value is None:
        return value
    stripped = value.strip()
    if _UNSAFE_PATH_RE.search(stripped):
        raise ValueError(
            f"Invalid {field_name}: path traversal or unsafe characters not allowed"
        )
    return stripped or None


class McpCommandRequest(BaseModel):
    action: str  # "search" | "read" | "list"
    query: str | None = None  # search 시 검색어
    target: str | None = None  # list/read 시 원본 인자
    category: str | None = None  # search/list 시 카테고리 필터
    filename: str | None = None  # read 시 파일 경로
    session_category: str | None = None
    session_provider_id: str | None = None
    rag_enabled: bool = False
    max_results: int = 5
    provider_id: str | None = None

    @field_validator("target", "filename", mode="before")
    @classmethod
    def validate_path_fields(cls, value):
        return _validate_filename(value, "path")


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

    @field_validator("filename_filter", mode="before")
    @classmethod
    def validate_filename_filter(cls, value):
        return _validate_filename(value, "filename_filter")


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
        raise HTTPException(
            status_code=502, detail=f"카테고리 검증 실패: {error}"
        ) from error


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
            target=body.target,
            category=body.category,
            filename=body.filename,
            session_category=body.session_category,
            session_provider_id=body.session_provider_id,
            rag_enabled=body.rag_enabled,
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
