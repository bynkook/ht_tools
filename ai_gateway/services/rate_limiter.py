"""
Rate Limiter for FabriX API
"""
from datetime import datetime, timedelta
from collections import deque
from threading import Lock
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TokenRateLimiter:
    """
    Thread-safe rate limiter for API requests with token tracking.
    """
    
    def __init__(
        self, 
        rpm_limit: int = 100, 
        tpm_limit: int = 1000000,
        time_window_seconds: int = 60
    ):
        """
        Initialize rate limiter.
        
        Args:
            rpm_limit: Maximum requests per minute
            tpm_limit: Maximum tokens per minute
            time_window_seconds: Time window for rate limiting (default: 60 seconds)
        """
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.time_window_seconds = time_window_seconds
        self.time_window = timedelta(seconds=time_window_seconds)
        self.scope = "global_shared"
        
        # (timestamp, tokens_used) 형태로 저장
        self.requests = deque()
        self.lock = Lock()
        
        logger.info(
            f"Rate Limiter initialized: RPM={rpm_limit}, TPM={tpm_limit}, "
            f"Window={time_window_seconds}s"
        )
    
    def _cleanup_old_requests(self, now: datetime):
        """Remove requests outside the time window."""
        cutoff_time = now - self.time_window
        
        while self.requests and self.requests[0][0] < cutoff_time:
            self.requests.popleft()
    
    def can_proceed(self, estimated_tokens: int = 100) -> tuple[bool, Optional[str]]:
        """
        Check if request can proceed within rate limits.
        
        Args:
            estimated_tokens: Estimated token count for the request
            
        Returns:
            (can_proceed: bool, error_message: Optional[str])
        """
        with self.lock:
            now = datetime.now()
            self._cleanup_old_requests(now)
            
            # 현재 요청 수 및 토큰 수 계산
            request_count = len(self.requests)
            total_tokens = sum(tokens for _, tokens in self.requests)
            
            # RPM 체크
            if request_count >= self.rpm_limit:
                remaining = self.rpm_limit - request_count
                logger.warning(
                    f"RPM limit reached: {request_count}/{self.rpm_limit}"
                )
                return False, f"Rate limit exceeded: {request_count} requests in last minute (limit: {self.rpm_limit})"
            
            # TPM 체크
            if total_tokens + estimated_tokens > self.tpm_limit:
                logger.warning(
                    f"TPM limit reached: {total_tokens + estimated_tokens}/{self.tpm_limit}"
                )
                return False, f"Token limit exceeded: {total_tokens + estimated_tokens} tokens in last minute (limit: {self.tpm_limit})"
            
            # 요청 추가
            self.requests.append((now, estimated_tokens))
            
            logger.debug(
                f"Request allowed: {request_count + 1}/{self.rpm_limit} requests, "
                f"{total_tokens + estimated_tokens}/{self.tpm_limit} tokens"
            )
            
            return True, None
    
    def get_wait_time(self, estimated_tokens: int = 100) -> float:
        """
        Calculate how long to wait before the request can proceed.
        
        Args:
            estimated_tokens: Estimated token count for the request
            
        Returns:
            Wait time in seconds (0 if can proceed immediately)
        """
        with self.lock:
            now = datetime.now()
            self._cleanup_old_requests(now)
            
            request_count = len(self.requests)
            total_tokens = sum(tokens for _, tokens in self.requests)
            
            # 요청 수 초과
            if request_count >= self.rpm_limit:
                # 가장 오래된 요청이 만료될 때까지 대기
                oldest_request_time = self.requests[0][0]
                wait_until = oldest_request_time + self.time_window
                wait_seconds = (wait_until - now).total_seconds()
                return max(0, wait_seconds)
            
            # 토큰 수 초과
            if total_tokens + estimated_tokens > self.tpm_limit:
                # 토큰이 충분해질 때까지 대기 (추정)
                tokens_to_free = (total_tokens + estimated_tokens) - self.tpm_limit
                # 가장 오래된 요청부터 토큰 해제
                freed_tokens = 0
                for timestamp, tokens in self.requests:
                    freed_tokens += tokens
                    if freed_tokens >= tokens_to_free:
                        wait_until = timestamp + self.time_window
                        wait_seconds = (wait_until - now).total_seconds()
                        return max(0, wait_seconds)
                
                # 최악의 경우: 전체 윈도우 대기
                if self.requests:
                    oldest_request_time = self.requests[0][0]
                    wait_until = oldest_request_time + self.time_window
                    wait_seconds = (wait_until - now).total_seconds()
                    return max(0, wait_seconds)
            
            return 0.0
    
    def get_current_usage(self) -> dict:
        """
        Get current usage statistics.
        
        Returns:
            dict with current_rpm, current_tpm, remaining_rpm, remaining_tpm
        """
        with self.lock:
            now = datetime.now()
            self._cleanup_old_requests(now)
            
            request_count = len(self.requests)
            total_tokens = sum(tokens for _, tokens in self.requests)
            
            return {
                'current_rpm': request_count,
                'current_tpm': total_tokens,
                'remaining_rpm': max(0, self.rpm_limit - request_count),
                'remaining_tpm': max(0, self.tpm_limit - total_tokens),
                'rpm_limit': self.rpm_limit,
                'tpm_limit': self.tpm_limit,
                'scope': self.scope,
                'window_seconds': self.time_window_seconds,
            }

    def get_response_headers(self, retry_after: Optional[float] = None) -> dict:
        """
        Build rate limit headers for API responses.

        Args:
            retry_after: Optional wait seconds for Retry-After header.

        Returns:
            HTTP headers with current rate limit metadata.
        """
        usage = self.get_current_usage()
        headers = {
            "X-RateLimit-Scope": usage['scope'],
            "X-RateLimit-Window-Seconds": str(usage['window_seconds']),
            "X-RateLimit-Limit-RPM": str(usage['rpm_limit']),
            "X-RateLimit-Limit-TPM": str(usage['tpm_limit']),
            "X-RateLimit-Remaining-RPM": str(usage['remaining_rpm']),
            "X-RateLimit-Remaining-TPM": str(usage['remaining_tpm']),
        }
        if retry_after is not None:
            headers["Retry-After"] = str(max(1, int(round(retry_after))))
        return headers

    def get_policy(self) -> dict:
        """
        Return static rate limit policy metadata.
        """
        return {
            'scope': self.scope,
            'window_seconds': self.time_window_seconds,
            'rpm_limit': self.rpm_limit,
            'tpm_limit': self.tpm_limit,
        }
    
    def reset(self):
        """Reset rate limiter (for testing purposes)."""
        with self.lock:
            self.requests.clear()
            logger.info("Rate limiter reset")


# Global rate limiter instance
rate_limiter = TokenRateLimiter(rpm_limit=100, tpm_limit=1000000)
