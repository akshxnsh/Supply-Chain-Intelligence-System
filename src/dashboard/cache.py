"""Redis caching for the read endpoints of the dashboard API.

    @cached("suppliers", ttl=300)
    def get_suppliers(business_id: str = ...): ...

- Key = group + endpoint + the request arguments, so different businesses / pages never share an entry.
- Only successful answers are cached (a dict with an "error" key is never stored).
- Writes call invalidate(group) so a user never sees stale data after their own change; the TTL covers changes made elsewhere.
- Redis down or API_CACHE=0 -> the endpoint just runs (response header X-Cache: BYPASS). A slow Redis cannot slow the API:
  socket timeouts are 250 ms.
- Every response says X-Cache: HIT | MISS | BYPASS; hit/miss counters live in Redis (/api/cache/stats).
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import logging
import os

from fastapi import Response
from fastapi.encoders import jsonable_encoder

logger = logging.getLogger(__name__)

PREFIX = "chainguard:api:"
_cache = None
_configured = False


class ApiCache:
    def __init__(self, client, prefix: str = PREFIX):
        self._r, self._prefix = client, prefix

    def get(self, key: str):
        try:
            raw = self._r.get(self._prefix + key)
        except Exception as exc:  # noqa: BLE001 - a cache outage must never break the API
            logger.warning("cache get failed: %s", exc)
            return None
        return json.loads(raw) if raw is not None else None

    def set(self, key: str, value, ttl: int) -> None:
        try:
            self._r.set(self._prefix + key, json.dumps(value), ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache set failed: %s", exc)

    def invalidate(self, group: str) -> int:
        try:
            keys = list(self._r.scan_iter(match=f"{self._prefix}{group}:*", count=200))
            return self._r.delete(*keys) if keys else 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("cache invalidate failed: %s", exc)
            return 0

    def count(self, what: str) -> None:
        try:
            self._r.incr(f"{self._prefix}stats:{what}")
        except Exception:  # noqa: BLE001
            pass

    def stats(self) -> dict:
        try:
            hits = int(self._r.get(f"{self._prefix}stats:hits") or 0)
            misses = int(self._r.get(f"{self._prefix}stats:misses") or 0)
        except Exception:  # noqa: BLE001
            return {"enabled": True, "available": False}
        total = hits + misses
        return {"enabled": True, "available": True, "hits": hits, "misses": misses,
                "hit_rate": round(hits / total, 3) if total else None}

    def reset_stats(self) -> None:
        try:
            self._r.delete(f"{self._prefix}stats:hits", f"{self._prefix}stats:misses")
        except Exception:  # noqa: BLE001
            pass


def configure(client) -> None:
    """Set the Redis client explicitly (tests); None disables caching."""
    global _cache, _configured
    _cache, _configured = (ApiCache(client) if client is not None else None), True


def reset() -> None:
    global _cache, _configured
    _cache, _configured = None, False


def get_cache() -> ApiCache | None:
    global _cache, _configured
    if not _configured:
        _configured = True
        url = os.getenv("REDIS_URL")
        if os.getenv("API_CACHE", "1") != "0" and url:
            try:
                import redis

                client = redis.Redis.from_url(url, socket_timeout=0.25, socket_connect_timeout=0.5, decode_responses=True)
                client.ping()
                _cache = ApiCache(client)
            except Exception as exc:  # noqa: BLE001
                logger.warning("API cache disabled, Redis unavailable: %s", exc)
    return _cache


def invalidate(*groups: str) -> None:
    cache = get_cache()
    if cache:
        for g in groups:
            cache.invalidate(g)


def _key(group: str, name: str, kwargs: dict) -> str:
    raw = json.dumps(kwargs, sort_keys=True, default=str)
    return f"{group}:{name}:{hashlib.sha1(raw.encode()).hexdigest()[:16]}"


def _cacheable(payload) -> bool:
    return not (isinstance(payload, dict) and "error" in payload)


def cached(group: str, ttl: int):
    """Cache the JSON result of a GET endpoint function (sync or async) in Redis for `ttl` seconds."""

    def deco(fn):
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        # let FastAPI inject the Response so we can set the X-Cache header
        params.append(inspect.Parameter("response", inspect.Parameter.KEYWORD_ONLY, annotation=Response))

        def prepare(kwargs):
            response = kwargs.pop("response", None)
            return response, get_cache(), _key(group, fn.__name__, kwargs)

        def mark(response, status):
            if response is not None:
                response.headers["X-Cache"] = status

        def store(cache, key, result, response):
            payload = jsonable_encoder(result)
            if cache is None:
                mark(response, "BYPASS")
            else:
                if _cacheable(payload):
                    cache.set(key, {"v": payload}, ttl)
                cache.count("misses")
                mark(response, "MISS")
            return payload

        def hit_of(cache, key, response):
            hit = cache.get(key) if cache else None
            if hit is not None:
                cache.count("hits")
                mark(response, "HIT")
                return hit["v"]
            return None

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args, **kwargs):
                response, cache, key = prepare(kwargs)
                hit = hit_of(cache, key, response)
                if hit is not None:
                    return hit
                return store(cache, key, await fn(*args, **kwargs), response)
        else:
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                response, cache, key = prepare(kwargs)
                hit = hit_of(cache, key, response)
                if hit is not None:
                    return hit
                return store(cache, key, fn(*args, **kwargs), response)

        wrapper.__signature__ = sig.replace(parameters=params)
        return wrapper

    return deco
