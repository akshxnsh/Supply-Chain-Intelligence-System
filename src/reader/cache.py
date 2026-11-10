"""Cache for reader results, keyed by the content hash of the text the model saw.

Redis is the real cache (shared across processes, survives restarts). If REDIS_URL is not set or Redis is down the
reader falls back to an in-process dict, so it still works and the numbers are reported honestly (`backend`).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 30 * 24 * 3600
KEY_PREFIX = "chainguard:reader:"


class MemoryCache:
    backend = "memory"

    def __init__(self):
        self._data: dict[str, str] = {}

    def get(self, key: str) -> Optional[dict]:
        raw = self._data.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        self._data[key] = json.dumps(value)


class RedisCache:
    backend = "redis"

    def __init__(self, client, prefix: str = KEY_PREFIX):
        self._r, self._prefix = client, prefix

    def get(self, key: str) -> Optional[dict]:
        try:
            raw = self._r.get(self._prefix + key)
        except Exception as exc:  # noqa: BLE001 - a cache outage must never break reading
            logger.warning("redis get failed (%s); treating as a miss", exc)
            return None
        return json.loads(raw) if raw else None

    def set(self, key: str, value: dict, ttl: int = DEFAULT_TTL_SECONDS) -> None:
        try:
            self._r.set(self._prefix + key, json.dumps(value), ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis set failed (%s); result not cached", exc)


def make_cache(url: str | None = None):
    """Redis cache if REDIS_URL works, otherwise an in-memory fallback."""
    url = url if url is not None else os.getenv("REDIS_URL")
    if not url:
        logger.info("REDIS_URL not set: using in-memory cache")
        return MemoryCache()
    try:
        import redis

        client = redis.Redis.from_url(url, socket_timeout=3, socket_connect_timeout=3, decode_responses=True)
        client.ping()
        return RedisCache(client)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable (%s): using in-memory cache", exc)
        return MemoryCache()
