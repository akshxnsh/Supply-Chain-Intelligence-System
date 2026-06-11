"""Lightweight model-call budgeting + caching for Gemini free-tier limits.

Free-tier targets this guards:
    * 5  requests / minute   (RPM)
    * 20 requests / day      (RPD)
    * 250k tokens / minute   (TPM)

The deterministic pipeline (src/agent/pipeline.py) does all data gathering in
Python and makes at most ONE model call per simulation. This module exists to
(a) hard-cap that to MAX_MODEL_CALLS_PER_SIMULATION, (b) refuse redundant calls,
and (c) cache slow/expensive deterministic lookups (calibration, supplier
scoring) so repeated simulations reuse unchanged results instead of recomputing.

No business logic lives here — only call accounting and a TTL cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable

_log = logging.getLogger(__name__)

# Minimum model calls that still preserve behavior. The synthesis step (severity
# score + PO sizing judgment) is the only irreducible model call per simulation.
MAX_MODEL_CALLS_PER_SIMULATION = 1

# Free-tier ceilings (used only for the usage estimate logged after each run).
RPM_LIMIT = 5
RPD_LIMIT = 20
TPM_LIMIT = 250_000


class CallBudget:
    """Counts model calls within a single simulation and refuses overruns."""

    def __init__(self, max_calls: int = MAX_MODEL_CALLS_PER_SIMULATION) -> None:
        self.max_calls = max_calls
        self.calls_made = 0
        self.tokens_estimated = 0

    def can_call(self) -> bool:
        return self.calls_made < self.max_calls

    def record(self, *, est_tokens: int = 0) -> None:
        self.calls_made += 1
        self.tokens_estimated += est_tokens

    def summary(self) -> dict[str, Any]:
        return {
            "model_calls": self.calls_made,
            "estimated_tokens": self.tokens_estimated,
            "max_calls_per_simulation": self.max_calls,
        }


class _TTLCache:
    """Tiny thread-safe TTL cache for deterministic, slow-changing lookups."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, ttl_seconds: float) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if time.monotonic() - stored_at > ttl_seconds:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_cache = _TTLCache()


def _key(prefix: str, *parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str)
    return f"{prefix}:{hashlib.sha1(raw.encode()).hexdigest()[:16]}"


def cached_call(
    prefix: str,
    parts: tuple,
    producer: Callable[[], Any],
    ttl_seconds: float = 300.0,
) -> Any:
    """Return a cached deterministic result or compute+store it.

    `parts` must fully identify the inputs so different inputs never collide.
    Only use for pure deterministic lookups (calibration, scoring) — never for
    anything whose result must reflect brand-new source data within the TTL.
    """
    key = _key(prefix, *parts)
    hit = _cache.get(key, ttl_seconds)
    if hit is not None:
        _log.info("[QUOTA] cache hit: %s", prefix)
        return hit
    value = producer()
    _cache.set(key, value)
    return value


def clear_cache() -> None:
    _cache.clear()
