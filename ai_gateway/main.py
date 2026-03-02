"""
FastAPI Main Application
AI Gateway - FabriX 및 Image Inspector를 위한 API 게이트웨이
"""

import sys
import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
import toml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health_router, agent_chat_router, chat_router, image_router
from .services.rate_limiter_v2 import rate_limiter

# 환경 설정 및 Secrets 로드
BASE_DIR = Path(__file__).resolve().parent.parent
SECRETS_PATH = BASE_DIR / "secrets.toml"


def _configure_logging() -> logging.Logger:
    """콘솔 + 일별 파일 회전 로그 설정"""
    log_dir = BASE_DIR / "logs" / "ai_gateway"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "fastapi.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    configured_logger = logging.getLogger(__name__)
    configured_logger.info("✅ Logging initialized: console + daily file (%s)", log_file)
    return configured_logger


logger = _configure_logging()

try:
    with open(SECRETS_PATH, "r", encoding="utf-8") as f:
        SECRETS = toml.load(f)
except FileNotFoundError:
    print(f"Error: secrets.toml not found at {SECRETS_PATH}")
    sys.exit(1)

SERVER_CONFIG = SECRETS['server']


def _get_int_config(key: str, default: int) -> int:
    value = SERVER_CONFIG.get(key, default)
    try:
        parsed = int(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


def _get_float_config(key: str, default: float) -> float:
    value = SERVER_CONFIG.get(key, default)
    try:
        parsed = float(value)
        return parsed if parsed > 0 else default
    except (TypeError, ValueError):
        return default


HTTPX_MAX_CONNECTIONS = _get_int_config('httpx_max_connections', 100)
HTTPX_MAX_KEEPALIVE_CONNECTIONS = _get_int_config('httpx_max_keepalive_connections', 20)
HTTPX_KEEPALIVE_EXPIRY_SECONDS = _get_float_config('httpx_keepalive_expiry_seconds', 30.0)

HTTPX_TIMEOUT_CONNECT_SECONDS = _get_float_config('httpx_timeout_connect_seconds', 10.0)
HTTPX_TIMEOUT_READ_SECONDS = _get_float_config('httpx_timeout_read_seconds', 60.0)
HTTPX_TIMEOUT_WRITE_SECONDS = _get_float_config('httpx_timeout_write_seconds', 60.0)
HTTPX_TIMEOUT_POOL_SECONDS = _get_float_config('httpx_timeout_pool_seconds', 5.0)

# Final recommendation lock:
# Item 2(httpx limits/timeout)는 현재 수준 유지 + 운영 검증만 수행합니다.
# 추가 강화(더 엄격한 제한/새 제한 계층 도입)는 온라인 재검증 전 보류합니다.


async def _metrics_log_loop(interval_seconds: int):
    """주기적으로 Rate Limiter 운영/품질 지표를 콘솔에 출력"""
    while True:
        await asyncio.sleep(interval_seconds)
        snapshot = rate_limiter.get_metrics_snapshot()
        operational = snapshot["operational"]
        upstream = snapshot["upstream_quality"]
        rolling_5m = snapshot["rolling_5m"]
        minute = snapshot.get("minute")

        if interval_seconds == 60:
            logger.info(
                "[RATE_METRICS_1M] minute=%s rpm_used=%s tpm_used=%s 429_count=%s "
                "queue_depth=%s p95_latency=%sms upstream_429=%s upstream_5xx=%s retry_after_avg=%s",
                minute,
                operational["rpm_used"],
                operational["tpm_used"],
                operational["429_count"],
                operational["queue_depth"],
                operational["p95_latency"],
                upstream["upstream_429"],
                upstream["upstream_5xx"],
                upstream["retry_after_avg"],
            )
        elif interval_seconds == 300:
            logger.info(
                "[RATE_METRICS_5M] minute=%s rpm_used_5m_avg=%s tpm_used_5m_avg=%s",
                minute,
                rolling_5m["rpm_used_5m_avg"],
                rolling_5m["tpm_used_5m_avg"],
            )

# Lifecycle management for HTTP client
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage HTTP client lifecycle"""
    # Startup: Create shared AsyncClient
    limits = httpx.Limits(
        max_connections=HTTPX_MAX_CONNECTIONS,
        max_keepalive_connections=HTTPX_MAX_KEEPALIVE_CONNECTIONS,
        keepalive_expiry=HTTPX_KEEPALIVE_EXPIRY_SECONDS,
    )
    timeout = httpx.Timeout(
        connect=HTTPX_TIMEOUT_CONNECT_SECONDS,
        read=HTTPX_TIMEOUT_READ_SECONDS,
        write=HTTPX_TIMEOUT_WRITE_SECONDS,
        pool=HTTPX_TIMEOUT_POOL_SECONDS,
    )

    app.state.http_client = httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
    )
    logger.info(
        "✅ HTTP Client initialized (limits: max=%s, keepalive=%s, expiry=%ss | timeout: connect=%ss, read=%ss, write=%ss, pool=%ss)",
        HTTPX_MAX_CONNECTIONS,
        HTTPX_MAX_KEEPALIVE_CONNECTIONS,
        HTTPX_KEEPALIVE_EXPIRY_SECONDS,
        HTTPX_TIMEOUT_CONNECT_SECONDS,
        HTTPX_TIMEOUT_READ_SECONDS,
        HTTPX_TIMEOUT_WRITE_SECONDS,
        HTTPX_TIMEOUT_POOL_SECONDS,
    )

    metrics_tasks = [
        asyncio.create_task(_metrics_log_loop(60)),
        asyncio.create_task(_metrics_log_loop(300)),
    ]
    app.state.metrics_tasks = metrics_tasks

    yield

    for task in getattr(app.state, "metrics_tasks", []):
        task.cancel()
    if getattr(app.state, "metrics_tasks", None):
        await asyncio.gather(*app.state.metrics_tasks, return_exceptions=True)

    # Shutdown: Close AsyncClient
    await app.state.http_client.aclose()
    logger.info("✅ HTTP Client closed")


# FastAPI 앱 초기화
app = FastAPI(
    title="AI Gateway",
    description="FabriX & Image Inspector API Gateway",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=SECRETS['security']['allowed_hosts'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(health_router, prefix="/health", tags=["Health"])
app.include_router(agent_chat_router, prefix="/agent-messages", tags=["FabriX Agent Chat"])
app.include_router(chat_router, prefix="/chat-messages", tags=["FabriX Chat"])
app.include_router(image_router, prefix="/image-compare", tags=["Image"])


@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "name": "AI Gateway",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "health": "/health",
            "agent_chat": "/agent-messages",
            "chat": "/chat-messages",
            "image": "/image-compare"
        }
    }


if __name__ == "__main__":
    import uvicorn
    # 개발용 실행 (실제 실행은 run_project.bat 사용 권장)
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
