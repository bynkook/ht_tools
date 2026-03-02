"""
FastAPI Router: Health Check
헬스 체크 및 상태 확인 엔드포인트
"""

from fastapi import APIRouter, Response
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def health_check():
    """헬스 체크 엔드포인트"""
    return {
        "status": "healthy",
        "service": "ai_gateway",
        "version": "1.0.0"
    }


@router.get("/ping")
async def ping():
    """간단한 ping 엔드포인트"""
    return Response(content="pong", media_type="text/plain")
