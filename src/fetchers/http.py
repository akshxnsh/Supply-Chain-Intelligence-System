"""Shared HTTP helper for all source fetchers: timeouts, retries with backoff, polite rate limiting."""

from __future__ import annotations

import time
from typing import Any, Callable
from urllib.parse import urlparse

import requests

USER_AGENT = "chainguard-fetcher/1.0"
DEFAULT_TIMEOUT = (5, 30)  # (connect seconds, read seconds)
RETRY_STATUS = {429, 500, 502, 503, 504}

_last_call: dict[str, float] = {}  # host -> monotonic time of the last request (for min_interval)


class FetchError(RuntimeError):
    """A source could not be read (after retries), or answered with something unusable."""


def get_json(
    url: str,
    params: dict | None = None,
    *,
    headers: dict | None = None,
    timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    retries: int = 3,
    backoff: float = 1.5,
    min_interval: float = 0.0,
    session: Any = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """GET `url` and return the parsed JSON.

    - Retries on connection errors, timeouts and HTTP 429/5xx (exponential backoff,
      honouring Retry-After). Other 4xx fail immediately.
    - `min_interval` spaces calls to the same host (GDELT asks for one request per 5 s).
    - `session` and `sleep` are injectable so tests never touch the network or wait.
    """
    sess = session or requests
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json", **(headers or {})}
    host = urlparse(url).netloc
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        if min_interval:
            wait = _last_call.get(host, 0.0) + min_interval - time.monotonic()
            if wait > 0:
                sleep(wait)
        _last_call[host] = time.monotonic()
        try:
            resp = sess.get(url, params=params, headers=hdrs, timeout=timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_error = exc
        else:
            if resp.status_code in RETRY_STATUS:
                last_error = FetchError(f"HTTP {resp.status_code} from {host}")
                retry_after = resp.headers.get("Retry-After") if getattr(resp, "headers", None) else None
                if retry_after and str(retry_after).isdigit() and attempt < retries:
                    sleep(min(float(retry_after), 60.0))
                    continue
            elif resp.status_code >= 400:
                raise FetchError(f"HTTP {resp.status_code} from {host}: {resp.text[:120]!r}")
            else:
                try:
                    return resp.json()
                except ValueError as exc:
                    snippet = resp.text[:120].replace("\n", " ")
                    raise FetchError(f"{host} did not return JSON: {snippet!r}") from exc
        if attempt < retries:
            sleep(backoff * (2 ** attempt))

    raise FetchError(f"{host} failed after {retries + 1} attempts: {last_error}")
