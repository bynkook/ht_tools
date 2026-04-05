"""
FastAPI Router: (FabriX Agent API)
FabriX AI 에이전트와의 채팅 엔드포인트
"""

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, Depends
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


# Pydantic Models
class ChatRequest(BaseModel):
    agentId: str
    contents: List[str]
    isStream: bool = True
    isRagOn: bool = True
    systemPrompt: Optional[str] = None     # 시스템 프롬프트 (선택)


def get_fabrix_config():
    """FabriX API 설정 가져오기 (main.py에서 로드됨)"""
    # main.py의 SECRETS에서 로드
    from pathlib import Path
    import toml
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    SECRETS_PATH = BASE_DIR / "secrets.toml"
    
    with open(SECRETS_PATH, "r", encoding="utf-8") as f:
        SECRETS = toml.load(f)
    
    FABRIX_AGENT_API_CONFIG = SECRETS['fabrix_agent_api']
    FABRIX_AGENT_BASE_URL = FABRIX_AGENT_API_CONFIG['base_url'].rstrip('/')
    FABRIX_AGENT_URL = f"{FABRIX_AGENT_BASE_URL}/openapi/agent-chat/v1"

    return FABRIX_AGENT_API_CONFIG, FABRIX_AGENT_URL


def get_fabrix_headers():
    """FabriX API 요청 헤더 생성"""
    fabrix_config, _ = get_fabrix_config()
    return {
        "Content-Type": "application/json",
        "x-fabrix-client": fabrix_config['client_key'],
        "x-openapi-token": fabrix_config['openapi_token'],
        "x-generative-ai-user-email": fabrix_config.get('user_email', ''),
    }


@router.get("/agents")
async def get_agents(request: Request, page: int = 1, limit: int = 50):
    """
    [GET] /agent-messages/agents
    FabriX에서 사용 가능한 Agent 목록을 조회합니다.
    """
    _, fabrix_agent_url = get_fabrix_config()
    url = f"{fabrix_agent_url}/agents"
    params = {"page": page, "limit": limit}
    headers = get_fabrix_headers()

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
        logger.error(f"FabriX API Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch agents")


@router.post("", dependencies=[Depends(verify_token)])
async def chat_stream(req: ChatRequest, request: Request):
    """
    [POST] /agent-messages
    사용자 메시지를 FabriX로 전송하고, 답변을 SSE 스트림으로 반환합니다.
    """
    # 디버깅용 로그
    # logger.info(f"[CHAT] Received request - agentId: {req.agentId}, contents: {req.contents}, isRagOn: {req.isRagOn}")
    
    if not req.agentId or req.agentId.strip() == "":
        logger.error("[CHAT] agentId is empty")
        raise HTTPException(status_code=400, detail="agentId is required and cannot be empty")
    
    if not req.contents or not req.contents[-1].strip():
        logger.error("[CHAT] contents is empty or last element is whitespace")
        raise HTTPException(status_code=400, detail="contents required and last element cannot be empty/whitespace")
    
    _, fabrix_agent_url = get_fabrix_config()
    
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
    
    url = f"{fabrix_agent_url}/agent-messages"
    headers = get_fabrix_headers()
    
    payload = {
        "agentId": req.agentId,
        "contents": req.contents,
        "isStream": True,
        "isRagOn": req.isRagOn,
        "executeFinalAnswer": True,
        "executeRagFinalAnswer": True,
        "executeRagStandaloneQuery": True
    }
    
    if req.systemPrompt:
        payload["systemPrompt"] = req.systemPrompt
    
    logger.info(f"[CHAT] Sending to FabriX - URL: {url}")
    logger.info(
        "[CHAT] Payload summary: agent_id=%s, content_count=%s, stream=%s, rag=%s",
        req.agentId,
        len(req.contents),
        req.isStream,
        req.isRagOn,
    )

    async def event_generator():
        try:
            logger.info(f"[CHAT] Starting stream to FabriX...")
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
                    yield f'data: {{"error": "FabriX API error", "status": {response.status_code}}}\n\n'
                    return
                
                response.raise_for_status()
                
                line_count = 0
                async for line in response.aiter_lines():
                    line_count += 1
                    if line:
                        decoded_line = line if isinstance(line, str) else line.decode('utf-8')
                        
                        # 디버깅: 원본 라인 로깅 (처음 200자만)
                        # if line_count % 2 == 1:  # 홀수 번째만 로깅 (실제 데이터 라인)
                        #     logger.info(f"[CHAT] Raw line #{line_count}: {decoded_line[:200]}")
                        
                        # SSE 포맷 처리: "data: ..." 또는 "data:..."
                        if decoded_line.startswith("data:"):
                            # data: 접두사 제거하고 JSON 파싱 시도
                            try:
                                json_str = decoded_line[5:].strip()  # "data:" 제거
                                if json_str:
                                    data = json.loads(json_str)
                                    # JSON을 다시 문자열화하여 SSE 형식으로 전송
                                    output = f"data: {json.dumps(data)}\n\n"
                                    # logger.info(f"[CHAT] Yielding data (content preview): {data.get('content', 'N/A')}")
                                    yield output
                            except json.JSONDecodeError:
                                # JSON 파싱 실패 시 원본 그대로 전송
                                logger.warning(f"[CHAT] JSON decode failed, sending raw: {decoded_line[:100]}")
                                yield f"{decoded_line}\n\n" if not decoded_line.endswith("\n") else decoded_line
                        elif decoded_line.strip().startswith(":"):
                            # SSE 주석 (ping 등)
                            yield f"{decoded_line}\n\n"
                        elif decoded_line.strip():
                            # data: 접두사가 없는 일반 텍스트도 SSE 형식으로 변환
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

    return StreamingResponse(
        event_generator(),
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
    [GET] /agent-messages/rate-limit-status
    현재 Rate Limiter 정책 및 사용 현황을 조회합니다.
    """
    return {
        "policy": rate_limiter.get_policy(),
        "usage": rate_limiter.get_current_usage(),
        "metrics": rate_limiter.get_metrics_snapshot(),
    }


@router.post("/file", dependencies=[Depends(verify_token)])
async def chat_with_file(
    request: Request,
    file: UploadFile = File(...),
    agentId: str = Form(...),
    contents: str = Form(...)
):
    """
    [POST] /agent-messages/file
    파일을 업로드하고 FabriX Code Interpreter 등을 이용해 분석 결과를 받습니다.
    """
    _, fabrix_agent_url = get_fabrix_config()
    
    # Rate Limiter 체크
    estimated_tokens = max(500, len(contents) // 4)
    
    max_retries = 2
    max_wait_time = 20
    
    for attempt in range(max_retries):
        soft_delay = rate_limiter.get_soft_throttle_delay(estimated_tokens)
        if soft_delay > 0:
            rate_limiter.mark_soft_wait_start()
            try:
                logger.info(
                    "Soft throttling applied for file upload: %.2fs before admission (attempt %s/%s)",
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
            logger.warning(f"Rate limit exceeded for file upload after {attempt + 1} attempts: {error_msg}")
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
        
        logger.info(f"Rate limit reached for file upload, waiting {wait_time:.2f}s (attempt {attempt + 1}/{max_retries})")
        await asyncio.sleep(wait_time)
    else:
        logger.error(f"File upload rate limit exceeded after {max_retries} retries")
        raise HTTPException(status_code=429, detail="Rate limit exceeded, please try again later")
    
    url = f"{fabrix_agent_url}/agent-messages/file"
    
    headers = get_fabrix_headers()
    headers.pop("Content-Type", None)

    try:
        started_at = time.perf_counter()
        file.file.seek(0)
        files = {
            'file': (file.filename, file.file, file.content_type)
        }
        
        # FabriX API expects contents as a list of strings
        # even for file uploads
        payload_contents = [contents] if isinstance(contents, str) else contents
        
        data = {
            'agentId': agentId,
            'isStream': 'False',
            'contents': payload_contents
        }
        
        response = await request.app.state.http_client.post(
            url,
            headers=headers,
            files=files,
            data=data
        )
        latency_ms = (time.perf_counter() - started_at) * 1000.0
        rate_limiter.record_latency_ms(latency_ms)
        retry_after_raw = response.headers.get("Retry-After")
        try:
            retry_after_val = float(retry_after_raw) if retry_after_raw is not None else None
        except ValueError:
            retry_after_val = None
        rate_limiter.record_upstream_result(response.status_code, retry_after_val)
        response.raise_for_status()
        return response.json()

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="File upload timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"File Upload Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

