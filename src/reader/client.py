"""Thin wrapper around the plain Gemini SDK (google-genai). No agent framework.

Everything above this file talks to the small `LLMClient` protocol, so tests use a fake and the model can be swapped.
The key is read from GEMINI_API_KEY (or GOOGLE_API_KEY) and never logged.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import Protocol

from src.reader.limiter import LLMError


@dataclass
class LLMResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = 0.0


class LLMClient(Protocol):
    def generate(self, prompt: str, model: str, *, temperature: float = 0.0, max_output_tokens: int = 8192) -> LLMResponse: ...


class GeminiClient:
    """google-genai `generate_content` with JSON output and low temperature."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise LLMError("GEMINI_API_KEY is not set (put it in .env)", status_code=401)
        from google import genai  # imported late so tests and non-LLM code never need the SDK/key

        self._genai = genai
        self._client = genai.Client(api_key=self._api_key)

    def generate(self, prompt: str, model: str, *, temperature: float = 0.0, max_output_tokens: int = 8192) -> LLMResponse:
        from google.genai import errors, types

        started = time.perf_counter()
        try:
            resp = self._client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                    max_output_tokens=max_output_tokens,
                ),
            )
        except errors.APIError as exc:
            raise LLMError(f"Gemini API error {exc.code}: {str(exc)[:200]}", status_code=exc.code,
                           retry_after=_retry_after_seconds(str(exc))) from exc
        except (TimeoutError, ConnectionError) as exc:
            raise LLMError(f"Gemini connection problem: {exc}", status_code=None) from exc
        usage = getattr(resp, "usage_metadata", None)
        return LLMResponse(
            text=resp.text or "",
            input_tokens=getattr(usage, "prompt_token_count", None),
            output_tokens=getattr(usage, "candidates_token_count", None),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


def _retry_after_seconds(message: str) -> float | None:
    """Gemini 429 messages often contain 'Please retry in 12.5s' / 'retryDelay: 12s'."""
    m = re.search(r"retry(?: in|Delay['\": ]+)\s*([0-9]+(?:\.[0-9]+)?)s", message)
    return float(m.group(1)) if m else None
