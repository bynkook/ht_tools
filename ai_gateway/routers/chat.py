"""
FastAPI Router: FabriX Chat API
FabriX LLM 모델과의 채팅 엔드포인트
"""

import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..dependencies import verify_token
from ..services.mcp import build_chat_runtime_contract
from ..services.mcp.runtime import ChatRuntimeFactory, ChatRuntimeInput, McpContextInput
from ..services.rate_limiter_v2 import rate_limiter
from ..services.mcp.runtime.upstream import get_fabrix_chat_config, get_fabrix_chat_headers

router = APIRouter()
logger = logging.getLogger(__name__)


# Pydantic Models
class McpChatContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    active_category: Optional[str] = Field(default=None, alias="activeCategory")
    rag_enabled: bool = Field(default=False, alias="ragEnabled")


class ChatMessageRequest(BaseModel):
    """FabriX Chat API 메시지 요청 모델"""
    model_config = ConfigDict(populate_by_name=True)

    modelIds: List[str] = Field(default_factory=list)  # Normal Mode only
    contents: List[str]                    # 대화 내용
    isStream: bool = True                  # 스트리밍 여부 (기본값: True)
    systemPrompt: Optional[str] = None     # 시스템 프롬프트 (선택)
    llmConfig: Optional[dict] = None       # LLM 설정 (temperature, max_new_tokens 등)
    mcp_context: Optional[McpChatContext] = Field(default=None, alias="mcpContext")
    # Note: llmName 생략 시 기본값 "FabriX" 사용


@router.get("/models")
async def get_models(request: Request, page: int = 1, limit: int = 50):
    """
    [GET] /chat-messages/models
    FabriX에서 사용 가능한 LLM Model 목록을 조회합니다.
    
    Response 구조:
    {
        "items": [
            {
                "modelId": "uuid",
                "name": [{"languageCode": "ko", "content": "모델명"}, ...],
                "description": [{"languageCode": "ko", "content": "설명"}, ...]
            },
            ...
        ]
    }
    """
    _, fabrix_chat_url = get_fabrix_chat_config()
    url = f"{fabrix_chat_url}/models"
    params = {"page": page, "limit": limit}
    headers = get_fabrix_chat_headers()

    try:
        response = await request.app.state.http_client.get(
            url, headers=headers, params=params
        )
        response.raise_for_status()
        return response.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Request timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"FabriX Chat API Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch models")


@router.post("", dependencies=[Depends(verify_token)])
async def chat_message_stream(req: ChatMessageRequest, request: Request):
    """
    [POST] /chat-messages
    사용자 메시지를 FabriX Chat API로 전송하고, 답변을 SSE 스트림으로 반환합니다.
    
    Note: 스트리밍 응답 시 필드명이 스네이크케이스로 반환됩니다.
    (예: eventStatus → event_status, finishReason → finish_reason)
    """
    normalized_model_ids = [model_id for model_id in req.modelIds if model_id and model_id.strip()]
    if not request.app.state.mcp_settings.host.test_mode and not normalized_model_ids:
        logger.error("[CHAT] modelIds is empty")
        raise HTTPException(status_code=400, detail="modelIds is required and cannot be empty")
    
    if not req.contents or not req.contents[-1].strip():
        logger.error("[CHAT] contents is empty or last element is whitespace")
        raise HTTPException(status_code=400, detail="contents required and last element cannot be empty/whitespace")
    runtime_input = ChatRuntimeInput(
        model_ids=normalized_model_ids,
        contents=req.contents,
        is_stream=req.isStream,
        system_prompt=req.systemPrompt,
        llm_config=req.llmConfig,
        mcp_context=(
            McpContextInput(
                active_category=req.mcp_context.active_category,
                rag_enabled=req.mcp_context.rag_enabled,
            )
            if req.mcp_context is not None
            else None
        ),
    )
    runtime = ChatRuntimeFactory(request=request, mcp_settings=request.app.state.mcp_settings).create()
    event_stream = await runtime.stream_chat(runtime_input)

    return StreamingResponse(
        event_stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.get("/runtime-config", dependencies=[Depends(verify_token)])
async def get_runtime_config(request: Request):
    return build_chat_runtime_contract(request.app.state.mcp_settings)


@router.get("/rate-limit-status")
async def get_rate_limit_status():
    """
    [GET] /chat-messages/rate-limit-status
    현재 Rate Limiter 사용 현황을 조회합니다.
    localhost:8001/chat-messages/rate-limit-status
    """
    return {
        "policy": rate_limiter.get_policy(),
        "usage": rate_limiter.get_current_usage(),
        "metrics": rate_limiter.get_metrics_snapshot(),
    }
