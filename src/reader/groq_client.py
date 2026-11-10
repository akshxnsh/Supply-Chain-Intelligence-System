"""Groq client (OpenAI-compatible chat completions) behind the same LLMClient interface, over plain `requests`.

Free-tier limits seen in Nov 2026 for gpt-oss-120b / gpt-oss-20b / qwen3.8-27b: 30 requests/min, 1,000 requests/day, but only
8,000 tokens/min and 200,000 tokens/day, so it suits the judge (few, small calls) and not the reader (big batches).
The key is read from GROQ_API_KEY and never logged.
"""

from __future__ import annotations

import os
import time

import requests

from src.reader.client import LLMResponse
from src.reader.limiter import LLMError

URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_COMPLETION_TOKENS = 3000   # reasoning tokens count too; keep the per-call token reservation small under an 8,000 tokens/min cap


class GroqClient:
    def __init__(self, api_key: str | None = None, session=None, timeout: tuple[float, float] = (10, 60)):
        self._key = api_key or os.getenv("GROQ_API_KEY")
        if not self._key:
            raise LLMError("GROQ_API_KEY is not set (put it in .env)", status_code=401)
        self._session, self._timeout = session or requests, timeout

    def generate(self, prompt: str, model: str, *, temperature: float = 0.0, max_output_tokens: int = 8192) -> LLMResponse:
        started = time.perf_counter()
        body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": temperature,
                "response_format": {"type": "json_object"}, "max_completion_tokens": min(max_output_tokens, MAX_COMPLETION_TOKENS)}
        try:
            r = self._session.post(URL, headers={"Authorization": f"Bearer {self._key}"}, json=body, timeout=self._timeout)
        except (requests.Timeout, requests.ConnectionError) as exc:
            raise LLMError(f"Groq connection problem: {exc.__class__.__name__}", status_code=None) from exc
        if r.status_code >= 400:
            retry_after = r.headers.get("retry-after")
            raise LLMError(f"Groq API error {r.status_code}: {r.text[:200]}", status_code=r.status_code,
                           retry_after=float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else None)
        data = r.json()
        usage = data.get("usage") or {}
        return LLMResponse(text=(data["choices"][0]["message"].get("content") or ""), input_tokens=usage.get("prompt_tokens"),
                           output_tokens=usage.get("completion_tokens"), latency_ms=(time.perf_counter() - started) * 1000)
