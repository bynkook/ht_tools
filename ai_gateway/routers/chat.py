"""
FastAPI Router: FabriX Chat API
FabriX LLM 모델과의 채팅 엔드포인트
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import json
import httpx
import asyncio
import logging
import time

from ..services.rate_limiter_v2 import rate_limiter
from ..dependencies import verify_token

router = APIRouter()
logger = logging.getLogger(__name__)


def is_mock_mode_enabled() -> bool:
    """Mock 모드 활성화 여부 확인"""
    from pathlib import Path
    import toml
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    SECRETS_PATH = BASE_DIR / "secrets.toml"
    
    try:
        with open(SECRETS_PATH, "r", encoding="utf-8") as f:
            secrets = toml.load(f)
        return secrets.get('server', {}).get('mock_mode', False)
    except Exception:
        return False


# Pydantic Models
class ChatMessageRequest(BaseModel):
    """FabriX Chat API 메시지 요청 모델"""
    modelIds: List[str]                    # 모델 ID 배열 (단일 선택도 배열로 전달)
    contents: List[str]                    # 대화 내용
    isStream: bool = True                  # 스트리밍 여부 (기본값: True)
    systemPrompt: Optional[str] = None     # 시스템 프롬프트 (선택)
    llmConfig: Optional[dict] = None       # LLM 설정 (temperature, max_new_tokens 등)
    # Note: llmName 생략 시 기본값 "FabriX" 사용


def get_fabrix_chat_config():
    """FabriX Chat API 설정 가져오기"""
    from pathlib import Path
    import toml
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    SECRETS_PATH = BASE_DIR / "secrets.toml"
    
    with open(SECRETS_PATH, "r", encoding="utf-8") as f:
        SECRETS = toml.load(f)
    
    FABRIX_CHAT_API_CONFIG = SECRETS['fabrix_chat_api']
    FABRIX_CHAT_BASE_URL = FABRIX_CHAT_API_CONFIG['base_url'].rstrip('/')
    FABRIX_CHAT_URL = f"{FABRIX_CHAT_BASE_URL}/openapi/chat/v1"
    
    return FABRIX_CHAT_API_CONFIG, FABRIX_CHAT_URL


def get_fabrix_chat_headers():
    """FabriX Chat API 요청 헤더 생성"""
    fabrix_config, _ = get_fabrix_chat_config()
    return {
        "Content-Type": "application/json",
        "x-fabrix-client": fabrix_config['client_key'],
        "x-openapi-token": fabrix_config['openapi_token'],
        "x-generative-ai-user-email": fabrix_config.get('user_email', ''),
    }


async def mock_event_generator(contents: List[str]):
    """
    Mock 모드용 SSE 이벤트 생성기
    FabriX API 응답 형식과 동일하게 스트리밍 응답 생성
    """
    history_count = len(contents)
    last_question = contents[-1] if contents else ""
    first_question = contents[0] if contents else ""
    
    # Mock 응답 메시지 구성
    mock_response = f"""[Mock 응답]
- 받은 대화 이력: {history_count}개
- 첫 번째 메시지: "{first_question[:50]}{'...' if len(first_question) > 50 else ''}"
- 마지막 질문: "{last_question[:50]}{'...' if len(last_question) > 50 else ''}"

※ 이 응답은 테스트용 Mock입니다. 실제 AI 응답이 아닙니다.
※ contents 배열이 올바르게 전달되었는지 확인하세요."""

    logger.info(f"[MOCK] Generating mock response for {history_count} contents")
    
    # 청크 단위로 스트리밍 (실제 LLM 응답처럼 보이도록)
    chunk_size = 5  # 5글자씩 전송
    for i in range(0, len(mock_response), chunk_size):
        chunk_text = mock_response[i:i+chunk_size]
        chunk = {
            "event_status": "CHUNK",
            "content": chunk_text,
            "finish_reason": None
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.03)  # 30ms 간격
    
    # 종료 신호
    final = {
        "event_status": "CHUNK",
        "content": "",
        "finish_reason": "stop"
    }
    yield f"data: {json.dumps(final, ensure_ascii=False)}\n\n"
    logger.info("[MOCK] Mock response completed")


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
    # Mock 모드: 가짜 모델 목록 반환
    if is_mock_mode_enabled():
        logger.info("[MOCK] Returning mock models list")
        return {
            "items": [
                {
                    "modelId": "mock-model-001",
                    "name": [{"languageCode": "ko", "content": "Mock 테스트 모델"}],
                    "description": [{"languageCode": "ko", "content": "오프라인 테스트용 Mock 모델입니다."}],
                    "displayName": "Mock 테스트 모델"
                },
                {
                    "modelId": "mock-model-002",
                    "name": [{"languageCode": "ko", "content": "Mock GPT-4"}],
                    "description": [{"languageCode": "ko", "content": "Mock GPT-4 모델 (테스트용)"}],
                    "displayName": "Mock GPT-4"
                }
            ]
        }
    
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
    if not req.modelIds or len(req.modelIds) == 0:
        logger.error("[CHAT] modelIds is empty")
        raise HTTPException(status_code=400, detail="modelIds is required and cannot be empty")
    
    if not req.contents or not req.contents[-1].strip():
        logger.error("[CHAT] contents is empty or last element is whitespace")
        raise HTTPException(status_code=400, detail="contents required and last element cannot be empty/whitespace")
    
    _, fabrix_chat_url = get_fabrix_chat_config()
    
    # Rate Limiter 체크
    estimated_tokens = sum(len(content) for content in req.contents) // 4
    estimated_tokens = max(100, estimated_tokens)
    
    # Rate limit 체크 및 자동 대기
    max_retries = 2
    max_wait_time = 20
    
    for attempt in range(max_retries):
        soft_delay = rate_limiter.get_soft_throttle_delay(estimated_tokens)
        if soft_delay > 0:
            rate_limiter.mark_soft_wait_start()
            try:
                logger.info(
                    "Soft throttling applied: %.2fs before admission (attempt %s/%s)",
                    soft_delay,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(soft_delay)
            finally:
                rate_limiter.mark_soft_wait_end()

        can_proceed, error_msg = rate_limiter.can_proceed(estimated_tokens)
        
        if can_proceed:
            break
        
        wait_time = rate_limiter.get_wait_time(estimated_tokens)
        
        if wait_time > max_wait_time or attempt == max_retries - 1:
            logger.warning(f"Rate limit exceeded after {attempt + 1} attempts: {error_msg}")
            raise HTTPException(
                status_code=429,
                headers=rate_limiter.get_response_headers(wait_time),
                detail={
                    "error": "rate_limit_exceeded",
                    "message": error_msg,
                    "retry_after": wait_time,
                    "current_usage": rate_limiter.get_current_usage()
                }
            )
        
        logger.info(f"Rate limit reached, waiting {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})")
        await asyncio.sleep(wait_time)
    else:
        logger.error(f"Rate limit exceeded after {max_retries} retries")
        raise HTTPException(status_code=429, detail="Rate limit exceeded, please try again later")
    
    url = f"{fabrix_chat_url}/messages"
    headers = get_fabrix_chat_headers()
    
    # FabriX Chat API 요청 페이로드
    payload = {
        "modelIds": req.modelIds,
        "contents": req.contents,
        "isStream": True,
    }
    
    # Optional fields
    if req.systemPrompt:
        payload["systemPrompt"] = req.systemPrompt
    
    if req.llmConfig:
        payload["llmConfig"] = req.llmConfig
    
    logger.info(f"[CHAT] Sending to FabriX Chat API - URL: {url}")
    logger.info(
        "[CHAT] Payload summary: model_count=%s, content_count=%s, stream=%s",
        len(req.modelIds),
        len(req.contents),
        req.isStream,
    )

    async def event_generator():
        try:
            logger.info(f"[CHAT] Starting stream to FabriX Chat API...")
            started_at = time.perf_counter()
            async with request.app.state.http_client.stream(
                "POST", url, headers=headers, json=payload, timeout=200.0
            ) as response:
                logger.info(f"[CHAT] FabriX response status: {response.status_code}")

                latency_ms = (time.perf_counter() - started_at) * 1000.0
                rate_limiter.record_latency_ms(latency_ms)
                retry_after_raw = response.headers.get("Retry-After")
                try:
                    retry_after_val = float(retry_after_raw) if retry_after_raw is not None else None
                except ValueError:
                    retry_after_val = None
                rate_limiter.record_upstream_result(response.status_code, retry_after_val)
                
                if response.status_code != 200:
                    error_text = await response.aread()
                    logger.error(f"[CHAT] FabriX error response: {error_text}")
                    yield f'data: {{"error": "FabriX Chat API error", "status": {response.status_code}}}\n\n'
                    return
                
                response.raise_for_status()
                
                line_count = 0
                async for line in response.aiter_lines():
                    line_count += 1
                    if line:
                        decoded_line = line if isinstance(line, str) else line.decode('utf-8')
                        
                        # SSE 포맷 처리: "data: ..." 또는 "data:..."
                        if decoded_line.startswith("data:"):
                            try:
                                json_str = decoded_line[5:].strip()  # "data:" 제거
                                if json_str:
                                    data = json.loads(json_str)
                                    output = f"data: {json.dumps(data)}\n\n"
                                    yield output
                            except json.JSONDecodeError:
                                logger.warning(f"[CHAT] JSON decode failed, sending raw: {decoded_line[:100]}")
                                yield f"{decoded_line}\n\n" if not decoded_line.endswith("\n") else decoded_line
                        elif decoded_line.strip().startswith(":"):
                            # SSE 주석 (ping 등)
                            yield f"{decoded_line}\n\n"
                        elif decoded_line.strip():
                            logger.warning(f"[CHAT] Line without 'data:' prefix: {decoded_line[:100]}")
                            yield f"data: {decoded_line}\n\n"
                
                logger.info(f"[CHAT] Stream completed. Total lines: {line_count}")
                            
        except httpx.TimeoutException:
            logger.error("Streaming timeout occurred")
            yield f'data: {json.dumps({"error": "timeout", "detail": "API request timeout"})}\n\n'
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error during streaming: {e.response.status_code}")
            yield f'data: {json.dumps({"error": "http_error", "status": e.response.status_code, "detail": str(e)})}\n\n'
        except httpx.RequestError as e:
            logger.error(f"Request error during streaming: {e}")
            yield f'data: {json.dumps({"error": "request_error", "detail": str(e)})}\n\n'
        except Exception as e:
            logger.error(f"Unexpected streaming error: {e}")
            yield f'data: {json.dumps({"error": "unexpected_error", "detail": str(e)})}\n\n'

    # Mock 모드 확인 및 적절한 generator 선택
    if is_mock_mode_enabled():
        logger.info("[CHAT] Mock mode enabled - using mock response generator")
        generator = mock_event_generator(req.contents)
    else:
        generator = event_generator()

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


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
