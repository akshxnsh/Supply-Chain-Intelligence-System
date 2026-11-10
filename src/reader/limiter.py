"""Rate limiting and retry with exponential backoff for model calls.

Free-tier limits differ per model and per project (read the exact numbers in the AI Studio console and set
READER_RPM accordingly); this stays under whatever number is configured and backs off when the API still says no.
Clock and sleep are injectable so tests never wait.
"""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class LLMError(Exception):
    """A model call failed. `status_code` follows HTTP (429 rate limit, 503 overloaded, 400 bad request ...)."""

    def __init__(self, message: str, status_code: int | None = None, retry_after: float | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def is_retryable(exc: Exception) -> bool:
    if isinstance(exc, LLMError):
        return exc.status_code is None or exc.status_code in RETRYABLE_STATUS
    return isinstance(exc, (TimeoutError, ConnectionError))


class RateLimiter:
    """Allow at most `requests_per_minute` calls: waits so consecutive calls are >= 60/rpm seconds apart."""

    def __init__(self, requests_per_minute: float, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        if requests_per_minute <= 0:
            raise ValueError("requests_per_minute must be > 0")
        self.min_interval = 60.0 / requests_per_minute
        self._clock, self._sleep = clock, sleep
        self._next_allowed = 0.0
        self.waited_seconds = 0.0

    def wait(self) -> float:
        now = self._clock()
        delay = max(0.0, self._next_allowed - now)
        if delay:
            self._sleep(delay)
            self.waited_seconds += delay
        self._next_allowed = max(now, self._next_allowed) + self.min_interval
        return delay


def call_with_retry(
    fn: Callable[[], T],
    *,
    limiter: RateLimiter | None = None,
    max_retries: int = 4,
    base_delay: float = 4.0,
    max_delay: float = 90.0,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, Exception, float], None] | None = None,
    jitter: Callable[[], float] = random.random,
) -> T:
    """Run `fn` (one model call). Wait for the limiter before each try; retry retryable errors with backoff."""
    attempt = 0
    while True:
        if limiter:
            limiter.wait()
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - classified below
            if not is_retryable(exc) or attempt >= max_retries:
                raise
            hinted = getattr(exc, "retry_after", None)
            delay = min(max_delay, hinted if hinted else base_delay * (2 ** attempt))
            delay += delay * 0.25 * jitter()
            attempt += 1
            if on_retry:
                on_retry(attempt, exc, delay)
            sleep(delay)
