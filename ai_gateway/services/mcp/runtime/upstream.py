"""
Shared FabriX upstream configuration helpers.
"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException, Request

from ...rate_limiter_v2 import rate_limiter
from ..config import load_secrets

logger = logging.getLogger(__name__)


def get_fabrix_chat_config() -> tuple[dict, str]:
    secrets = load_secrets()
    fabrix_chat_api_config = secrets["fabrix_chat_api"]
    fabrix_chat_base_url = fabrix_chat_api_config["base_url"].rstrip("/")
    fabrix_chat_url = f"{fabrix_chat_base_url}/openapi/chat/v1"
    return fabrix_chat_api_config, fabrix_chat_url


def get_fabrix_chat_headers() -> dict[str, str]:
    fabrix_config, _ = get_fabrix_chat_config()
    return {
        "Content-Type": "application/json",
        "x-fabrix-client": fabrix_config["client_key"],
        "x-openapi-token": fabrix_config["openapi_token"],
        "x-generative-ai-user-email": fabrix_config.get("user_email", ""),
    }


class FabrixUpstreamClient:
    def __init__(self, request: Request):
        self._request = request

    async def stream_chat(
        self,
        *,
        model_ids: list[str],
        contents: list[str],
        is_stream: bool,
        system_prompt: str | None = None,
        llm_config: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        estimated_tokens = sum(len(content) for content in contents) // 4
        estimated_tokens = max(100, estimated_tokens)

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
                logger.warning("Rate limit exceeded after %s attempts: %s", attempt + 1, error_msg)
                raise HTTPException(
                    status_code=429,
                    headers=rate_limiter.get_response_headers(wait_time),
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": error_msg,
                        "retry_after": wait_time,
                        "current_usage": rate_limiter.get_current_usage(),
                    },
                )

            logger.info(
                "Rate limit reached, waiting %.2fs (attempt %s/%s)",
                wait_time,
                attempt + 1,
                max_retries,
            )
            await asyncio.sleep(wait_time)
        else:
            logger.error("Rate limit exceeded after %s retries", max_retries)
            raise HTTPException(status_code=429, detail="Rate limit exceeded, please try again later")

        _, fabrix_chat_url = get_fabrix_chat_config()
        payload = {
            "modelIds": model_ids,
            "contents": contents,
            "isStream": is_stream,
        }
        if system_prompt:
            payload["systemPrompt"] = system_prompt
        if llm_config:
            payload["llmConfig"] = llm_config

        url = f"{fabrix_chat_url}/messages"
        headers = get_fabrix_chat_headers()

        logger.info("[CHAT] Sending to FabriX Chat API - URL: %s", url)
        logger.info(
            "[CHAT] Payload summary: model_count=%s, content_count=%s, stream=%s",
            len(model_ids),
            len(contents),
            is_stream,
        )
        return self._event_generator(url=url, headers=headers, payload=payload)

    async def _event_generator(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> AsyncIterator[str]:
        try:
            logger.info("[CHAT] Starting stream to FabriX Chat API...")
            started_at = time.perf_counter()
            async with self._request.app.state.http_client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
                timeout=200.0,
            ) as response:
                logger.info("[CHAT] FabriX response status: %s", response.status_code)

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
                    logger.error("[CHAT] FabriX error response: %s", error_text)
                    yield f'data: {{"error": "FabriX Chat API error", "status": {response.status_code}}}\n\n'
                    return

                response.raise_for_status()

                line_count = 0
                async for line in response.aiter_lines():
                    line_count += 1
                    if not line:
                        continue

                    decoded_line = line if isinstance(line, str) else line.decode("utf-8")
                    if decoded_line.startswith("data:"):
                        try:
                            json_str = decoded_line[5:].strip()
                            if json_str:
                                data = json.loads(json_str)
                                yield f"data: {json.dumps(data)}\n\n"
                        except json.JSONDecodeError:
                            logger.warning(
                                "[CHAT] JSON decode failed, sending raw: %s",
                                decoded_line[:100],
                            )
                            if not decoded_line.endswith("\n"):
                                yield f"{decoded_line}\n\n"
                            else:
                                yield decoded_line
                    elif decoded_line.strip().startswith(":"):
                        yield f"{decoded_line}\n\n"
                    elif decoded_line.strip():
                        logger.warning(
                            "[CHAT] Line without 'data:' prefix: %s",
                            decoded_line[:100],
                        )
                        yield f"data: {decoded_line}\n\n"

                logger.info("[CHAT] Stream completed. Total lines: %s", line_count)
        except httpx.TimeoutException:
            logger.error("Streaming timeout occurred")
            yield f'data: {json.dumps({"error": "timeout", "detail": "API request timeout"})}\n\n'
        except httpx.HTTPStatusError as error:
            logger.error("HTTP error during streaming: %s", error.response.status_code)
            yield (
                f'data: {json.dumps({"error": "http_error", "status": error.response.status_code, "detail": str(error)})}\n\n'
            )
        except httpx.RequestError as error:
            logger.error("Request error during streaming: %s", error)
            yield f'data: {json.dumps({"error": "request_error", "detail": str(error)})}\n\n'
        except Exception as error:
            logger.error("Unexpected streaming error: %s", error)
            yield f'data: {json.dumps({"error": "unexpected_error", "detail": str(error)})}\n\n'


__all__ = ["FabrixUpstreamClient", "get_fabrix_chat_config", "get_fabrix_chat_headers"]
