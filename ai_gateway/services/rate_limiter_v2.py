"""
Rate Limiter v2 for FabriX API
- Backward compatible with existing public methods
- Adds soft/hard limit split, server-led slowdown helpers, and operational metrics
"""

from collections import deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Optional
import logging
import math
import random

logger = logging.getLogger(__name__)


class TokenRateLimiterV2:
    """
    Thread-safe rate limiter for API requests with token tracking.

    Compatibility methods:
    - can_proceed(estimated_tokens)
    - get_wait_time(estimated_tokens)
    - get_current_usage()
    - get_response_headers(retry_after)
    - get_policy()
    - reset()

    Added methods:
    - get_soft_throttle_delay(estimated_tokens)
    - mark_soft_wait_start() / mark_soft_wait_end()
    - record_upstream_result(status_code, retry_after)
    - record_latency_ms(latency_ms)
    - get_metrics_snapshot()
    """

    def __init__(
        self,
        rpm_limit: int = 100,
        tpm_limit: int = 1000000,
        time_window_seconds: int = 60,
        soft_limit_ratio: float = 0.8,
        max_soft_delay_seconds: float = 3.0,
        jitter_seconds: float = 0.4,
        metrics_retention_minutes: int = 120,
    ):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.time_window_seconds = time_window_seconds
        self.time_window = timedelta(seconds=time_window_seconds)
        self.scope = "global_shared"

        self.soft_limit_ratio = max(0.0, min(1.0, soft_limit_ratio))
        self.max_soft_delay_seconds = max(0.0, max_soft_delay_seconds)
        self.jitter_seconds = max(0.0, jitter_seconds)

        self.requests = deque()  # (timestamp, tokens)
        self.lock = Lock()

        self._metrics_retention_minutes = max(10, metrics_retention_minutes)
        self._minute_buckets = deque()  # oldest -> newest, bucket dict

        self._soft_waiting_count = 0

        logger.info(
            "Rate Limiter v2 initialized: RPM=%s, TPM=%s, Window=%ss, SoftRatio=%.2f",
            rpm_limit,
            tpm_limit,
            time_window_seconds,
            self.soft_limit_ratio,
        )

    def _cleanup_old_requests(self, now: datetime):
        cutoff_time = now - self.time_window
        while self.requests and self.requests[0][0] < cutoff_time:
            self.requests.popleft()

    def _minute_key(self, now: datetime) -> datetime:
        return now.replace(second=0, microsecond=0)

    def _new_bucket(self, minute: datetime) -> dict:
        return {
            "minute": minute,
            "rpm_used": 0,
            "tpm_used": 0,
            "429_count": 0,
            "queue_depth": self._soft_waiting_count,
            "queue_depth_peak": self._soft_waiting_count,
            "latencies_ms": [],
            "upstream_429": 0,
            "upstream_5xx": 0,
            "retry_after_sum": 0.0,
            "retry_after_count": 0,
        }

    def _prune_old_buckets(self, now: datetime):
        cutoff = self._minute_key(now) - timedelta(minutes=self._metrics_retention_minutes)
        while self._minute_buckets and self._minute_buckets[0]["minute"] < cutoff:
            self._minute_buckets.popleft()

    def _get_bucket(self, now: datetime) -> dict:
        minute = self._minute_key(now)
        if not self._minute_buckets or self._minute_buckets[-1]["minute"] < minute:
            self._minute_buckets.append(self._new_bucket(minute))
        elif self._minute_buckets[-1]["minute"] > minute:
            # 예상치 못한 시계 역행 방어
            return self._new_bucket(minute)

        self._prune_old_buckets(now)
        return self._minute_buckets[-1]

    def _current_usage_no_lock(self, now: datetime) -> tuple[int, int]:
        self._cleanup_old_requests(now)
        request_count = len(self.requests)
        total_tokens = sum(tokens for _, tokens in self.requests)
        return request_count, total_tokens

    def _current_load_ratio_no_lock(self, estimated_tokens: int, now: datetime) -> float:
        request_count, total_tokens = self._current_usage_no_lock(now)
        rpm_ratio = request_count / self.rpm_limit if self.rpm_limit > 0 else 1.0
        tpm_ratio = (total_tokens + estimated_tokens) / self.tpm_limit if self.tpm_limit > 0 else 1.0
        return max(rpm_ratio, tpm_ratio)

    def can_proceed(self, estimated_tokens: int = 100) -> tuple[bool, Optional[str]]:
        with self.lock:
            now = datetime.now()
            request_count, total_tokens = self._current_usage_no_lock(now)
            bucket = self._get_bucket(now)

            if request_count >= self.rpm_limit:
                bucket["429_count"] += 1
                logger.warning("RPM limit reached: %s/%s", request_count, self.rpm_limit)
                return (
                    False,
                    f"Rate limit exceeded: {request_count} requests in last minute (limit: {self.rpm_limit})",
                )

            if total_tokens + estimated_tokens > self.tpm_limit:
                bucket["429_count"] += 1
                logger.warning("TPM limit reached: %s/%s", total_tokens + estimated_tokens, self.tpm_limit)
                return (
                    False,
                    f"Token limit exceeded: {total_tokens + estimated_tokens} tokens in last minute (limit: {self.tpm_limit})",
                )

            self.requests.append((now, estimated_tokens))
            bucket["rpm_used"] += 1
            bucket["tpm_used"] += estimated_tokens
            return True, None

    def get_soft_throttle_delay(self, estimated_tokens: int = 100) -> float:
        """
        Return server-led slowdown delay for soft limit zone.
        Hard-limit 영역(>=1.0)은 여기서 지연하지 않고 0 반환 후 can_proceed가 429 처리.
        """
        with self.lock:
            now = datetime.now()
            load_ratio = self._current_load_ratio_no_lock(estimated_tokens, now)

            if load_ratio >= 1.0:
                return 0.0

            if load_ratio <= self.soft_limit_ratio:
                return 0.0

            soft_zone = 1.0 - self.soft_limit_ratio
            if soft_zone <= 0:
                return 0.0

            normalized = (load_ratio - self.soft_limit_ratio) / soft_zone
            normalized = max(0.0, min(1.0, normalized))

            delay = normalized * self.max_soft_delay_seconds
            if self.jitter_seconds > 0:
                delay += random.uniform(0.0, self.jitter_seconds)

            return delay

    def mark_soft_wait_start(self):
        with self.lock:
            self._soft_waiting_count += 1
            bucket = self._get_bucket(datetime.now())
            bucket["queue_depth"] = self._soft_waiting_count
            if self._soft_waiting_count > bucket["queue_depth_peak"]:
                bucket["queue_depth_peak"] = self._soft_waiting_count

    def mark_soft_wait_end(self):
        with self.lock:
            self._soft_waiting_count = max(0, self._soft_waiting_count - 1)
            bucket = self._get_bucket(datetime.now())
            bucket["queue_depth"] = self._soft_waiting_count

    def record_latency_ms(self, latency_ms: float):
        with self.lock:
            bucket = self._get_bucket(datetime.now())
            bucket["latencies_ms"].append(max(0.0, float(latency_ms)))

    def record_upstream_result(self, status_code: int, retry_after: Optional[float] = None):
        with self.lock:
            bucket = self._get_bucket(datetime.now())

            if status_code == 429:
                bucket["upstream_429"] += 1
            if 500 <= status_code <= 599:
                bucket["upstream_5xx"] += 1

            if retry_after is not None:
                try:
                    retry_after_value = float(retry_after)
                    if retry_after_value >= 0:
                        bucket["retry_after_sum"] += retry_after_value
                        bucket["retry_after_count"] += 1
                except (TypeError, ValueError):
                    pass

    def get_wait_time(self, estimated_tokens: int = 100) -> float:
        with self.lock:
            now = datetime.now()
            request_count, total_tokens = self._current_usage_no_lock(now)

            if request_count >= self.rpm_limit and self.requests:
                oldest_request_time = self.requests[0][0]
                wait_until = oldest_request_time + self.time_window
                return max(0.0, (wait_until - now).total_seconds())

            if total_tokens + estimated_tokens > self.tpm_limit:
                tokens_to_free = (total_tokens + estimated_tokens) - self.tpm_limit
                freed_tokens = 0
                for timestamp, tokens in self.requests:
                    freed_tokens += tokens
                    if freed_tokens >= tokens_to_free:
                        wait_until = timestamp + self.time_window
                        return max(0.0, (wait_until - now).total_seconds())

                if self.requests:
                    oldest_request_time = self.requests[0][0]
                    wait_until = oldest_request_time + self.time_window
                    return max(0.0, (wait_until - now).total_seconds())

            return 0.0

    def get_current_usage(self) -> dict:
        with self.lock:
            now = datetime.now()
            request_count, total_tokens = self._current_usage_no_lock(now)
            return {
                "current_rpm": request_count,
                "current_tpm": total_tokens,
                "remaining_rpm": max(0, self.rpm_limit - request_count),
                "remaining_tpm": max(0, self.tpm_limit - total_tokens),
                "rpm_limit": self.rpm_limit,
                "tpm_limit": self.tpm_limit,
                "scope": self.scope,
                "window_seconds": self.time_window_seconds,
                "queue_depth": self._soft_waiting_count,
            }

    def get_response_headers(self, retry_after: Optional[float] = None) -> dict:
        usage = self.get_current_usage()
        headers = {
            "X-RateLimit-Scope": usage["scope"],
            "X-RateLimit-Window-Seconds": str(usage["window_seconds"]),
            "X-RateLimit-Limit-RPM": str(usage["rpm_limit"]),
            "X-RateLimit-Limit-TPM": str(usage["tpm_limit"]),
            "X-RateLimit-Remaining-RPM": str(usage["remaining_rpm"]),
            "X-RateLimit-Remaining-TPM": str(usage["remaining_tpm"]),
        }
        if retry_after is not None:
            headers["Retry-After"] = str(max(1, int(round(retry_after))))
        return headers

    def get_policy(self) -> dict:
        return {
            "scope": self.scope,
            "window_seconds": self.time_window_seconds,
            "rpm_limit": self.rpm_limit,
            "tpm_limit": self.tpm_limit,
            "soft_limit_ratio": self.soft_limit_ratio,
            "max_soft_delay_seconds": self.max_soft_delay_seconds,
            "jitter_seconds": self.jitter_seconds,
        }

    @staticmethod
    def _percentile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = max(0, min(len(sorted_values) - 1, int(math.ceil((q / 100.0) * len(sorted_values)) - 1)))
        return float(sorted_values[index])

    def _bucket_snapshot(self, bucket: Optional[dict]) -> dict:
        if not bucket:
            return {
                "minute": None,
                "rpm_used": 0,
                "tpm_used": 0,
                "429_count": 0,
                "queue_depth": self._soft_waiting_count,
                "p95_latency": 0.0,
                "upstream_429": 0,
                "upstream_5xx": 0,
                "retry_after_avg": 0.0,
            }

        retry_after_avg = (
            bucket["retry_after_sum"] / bucket["retry_after_count"]
            if bucket["retry_after_count"] > 0
            else 0.0
        )

        return {
            "minute": bucket["minute"].isoformat(),
            "rpm_used": bucket["rpm_used"],
            "tpm_used": bucket["tpm_used"],
            "429_count": bucket["429_count"],
            "queue_depth": bucket["queue_depth"],
            "p95_latency": round(self._percentile(bucket["latencies_ms"], 95), 2),
            "upstream_429": bucket["upstream_429"],
            "upstream_5xx": bucket["upstream_5xx"],
            "retry_after_avg": round(retry_after_avg, 3),
        }

    def _rolling_5m_snapshot(self) -> dict:
        if not self._minute_buckets:
            return {"rpm_used_5m_avg": 0.0, "tpm_used_5m_avg": 0.0}

        latest_minute = self._minute_buckets[-1]["minute"]
        lower_bound = latest_minute - timedelta(minutes=4)
        recent = [b for b in self._minute_buckets if b["minute"] >= lower_bound]

        if not recent:
            return {"rpm_used_5m_avg": 0.0, "tpm_used_5m_avg": 0.0}

        rpm_avg = sum(b["rpm_used"] for b in recent) / len(recent)
        tpm_avg = sum(b["tpm_used"] for b in recent) / len(recent)

        return {
            "rpm_used_5m_avg": round(rpm_avg, 2),
            "tpm_used_5m_avg": round(tpm_avg, 2),
        }

    def get_metrics_snapshot(self) -> dict:
        with self.lock:
            now = datetime.now()
            self._get_bucket(now)
            latest_bucket = self._minute_buckets[-1] if self._minute_buckets else None

            minute_snapshot = self._bucket_snapshot(latest_bucket)
            rolling_5m = self._rolling_5m_snapshot()

            return {
                "operational": {
                    "rpm_used": minute_snapshot["rpm_used"],
                    "tpm_used": minute_snapshot["tpm_used"],
                    "429_count": minute_snapshot["429_count"],
                    "queue_depth": minute_snapshot["queue_depth"],
                    "p95_latency": minute_snapshot["p95_latency"],
                },
                "upstream_quality": {
                    "upstream_429": minute_snapshot["upstream_429"],
                    "upstream_5xx": minute_snapshot["upstream_5xx"],
                    "retry_after_avg": minute_snapshot["retry_after_avg"],
                },
                "rolling_5m": rolling_5m,
                "minute": minute_snapshot["minute"],
            }

    def reset(self):
        with self.lock:
            self.requests.clear()
            self._minute_buckets.clear()
            self._soft_waiting_count = 0
            logger.info("Rate limiter v2 reset")


# Global rate limiter instance (v2)
rate_limiter = TokenRateLimiterV2(rpm_limit=100, tpm_limit=1000000)
