"""The reader: messy text -> structured events with a cheap Gemini model.

Pipeline per call to `Reader.read(items)`:
  1. cache lookup by content hash (Redis / memory)  -> hits cost nothing;
  2. misses are packed into batches (one model call reads up to `batch_size` items);
  3. each call waits for the rate limiter and retries 429/5xx with backoff;
  4. the answer is parsed (code fences stripped), validated with Pydantic and sanity-checked by code;
  5. items the model answered badly are retried once on their own; still bad -> reported as failed, never cached.
The model sees only the item text. Every call is written to the call log (tokens, latency, status).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol

from pydantic import ValidationError

from src.agent.model_config import READER_MODEL
from src.reader.client import LLMClient
from src.reader.limiter import LLMError, RateLimiter, call_with_retry
from src.reader.prompt import PROMPT_VERSION, build_prompt
from src.reader.schema import ReadEvent, ReadItem, normalize

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 10
MAX_PROMPT_CHARS = 14000


class CallLogger(Protocol):
    def log(self, entry: dict) -> None: ...


class NullLogger:
    def log(self, entry: dict) -> None:
        pass


@dataclass
class ReadResult:
    item: ReadItem
    event: ReadEvent | None
    source: str                      # llm | cache | failed
    error: str | None = None


@dataclass
class ReadStats:
    items: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    llm_calls: int = 0               # successful + failed attempts that reached the API (retries included)
    retried_calls: int = 0
    parse_failures: int = 0
    failed_items: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_backend: str = ""

    def to_dict(self) -> dict:
        naive = self.items  # one call per item, no cache, no batching
        d = dict(self.__dict__)
        d["naive_calls"] = naive
        d["calls_saved"] = max(0, naive - self.llm_calls)
        d["call_reduction_pct"] = round(100 * (1 - self.llm_calls / naive), 1) if naive else 0.0
        return d


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.I)


def extract_json(text: str):
    """Parse model output as JSON, tolerating ```json fences and text around the JSON."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i != -1]
    if not starts:
        raise ValueError("no JSON found in model output")
    start = min(starts)
    end = max(cleaned.rfind("}"), cleaned.rfind("]"))
    if end <= start:
        raise ValueError("unterminated JSON in model output")
    return json.loads(cleaned[start:end + 1])


def parse_response(text: str, expected_ids: set[str]) -> tuple[dict[str, ReadEvent], dict[str, str]]:
    """-> (valid events by item_id, errors by item_id). Ids the model made up are ignored."""
    payload = extract_json(text)
    if isinstance(payload, dict):
        payload = payload.get("items", [payload] if "item_id" in payload else [])
    if not isinstance(payload, list):
        raise ValueError("model output is not a list of items")
    events: dict[str, ReadEvent] = {}
    errors: dict[str, str] = {}
    for raw in payload:
        if not isinstance(raw, dict) or raw.get("item_id") not in expected_ids:
            continue
        try:
            events[raw["item_id"]] = ReadEvent.model_validate(raw)
        except ValidationError as exc:
            errors[raw["item_id"]] = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())[:300]
    for missing in expected_ids - events.keys() - errors.keys():
        errors[missing] = "item missing from model answer"
    return events, errors


class Reader:
    def __init__(self, client: LLMClient, cache, limiter: RateLimiter | None = None, *, model: str = READER_MODEL,
                 batch_size: int = DEFAULT_BATCH_SIZE, max_prompt_chars: int = MAX_PROMPT_CHARS,
                 call_logger: CallLogger | None = None, max_retries: int = 4,
                 sleep: Callable[[float], None] = time.sleep):
        self.client, self.cache, self.limiter = client, cache, limiter
        self.model, self.batch_size, self.max_prompt_chars = model, batch_size, max_prompt_chars
        self.log = call_logger or NullLogger()
        self.max_retries, self._sleep = max_retries, sleep

    # -- public ---------------------------------------------------------------

    def read(self, items: list[ReadItem]) -> tuple[list[ReadResult], ReadStats]:
        stats = ReadStats(items=len(items), cache_backend=getattr(self.cache, "backend", "?"))
        results: dict[str, ReadResult] = {}
        misses: list[ReadItem] = []

        for item in items:
            key = item.content_hash(self.model, PROMPT_VERSION)
            hit = self.cache.get(key)
            event = None
            if hit:
                try:
                    event = normalize(ReadEvent.model_validate(hit["event"]), item.reference_date)
                except (ValidationError, KeyError):
                    event = None  # corrupt/old cache entry: read it again
            if event:
                results[item.item_id] = ReadResult(item, event, "cache")
                stats.cache_hits += 1
            else:
                misses.append(item)
        stats.cache_misses = len(misses)
        self.log.log({"purpose": "reader", "kind": "cache_summary", "model": self.model, "prompt_version": PROMPT_VERSION,
                      "cache_hits": stats.cache_hits, "cache_misses": stats.cache_misses, "status": "cache"})

        retry_alone: list[ReadItem] = []
        for batch in self._batches(misses):
            self._read_batch(batch, results, retry_alone, stats, attempt=1)
        for item in retry_alone:  # the model answered badly for these: one more try, each on its own
            self._read_batch([item], results, [], stats, attempt=2)

        for item in items:
            if item.item_id not in results:
                results[item.item_id] = ReadResult(item, None, "failed", "no valid answer")
        stats.failed_items = sum(1 for r in results.values() if r.source == "failed")
        return [results[i.item_id] for i in items], stats

    # -- internals ------------------------------------------------------------

    def _batches(self, items: list[ReadItem]):
        batch: list[ReadItem] = []
        size = 0
        for item in items:
            n = len(item.text()) + 120
            if batch and (len(batch) >= self.batch_size or size + n > self.max_prompt_chars):
                yield batch
                batch, size = [], 0
            batch.append(item)
            size += n
        if batch:
            yield batch

    def _read_batch(self, batch: list[ReadItem], results: dict[str, ReadResult], retry_alone: list[ReadItem],
                    stats: ReadStats, attempt: int) -> None:
        prompt = build_prompt(batch)
        entry = {"purpose": "reader", "kind": "call", "model": self.model, "prompt_version": PROMPT_VERSION,
                 "batch_size": len(batch), "attempt": attempt, "cache_hits": 0, "cache_misses": len(batch)}

        def on_retry(n: int, exc: Exception, delay: float) -> None:
            stats.llm_calls += 1
            stats.retried_calls += 1
            self.log.log({**entry, "status": "retry", "error": f"try {n}: {exc}"[:300]})

        try:
            resp = call_with_retry(lambda: self.client.generate(prompt, self.model), limiter=self.limiter,
                                   max_retries=self.max_retries, sleep=self._sleep, on_retry=on_retry)
        except LLMError as exc:
            stats.llm_calls += 1
            self.log.log({**entry, "status": "error", "error": str(exc)[:300]})
            for item in batch:
                results[item.item_id] = ReadResult(item, None, "failed", str(exc)[:200])
            return
        stats.llm_calls += 1
        stats.input_tokens += resp.input_tokens or 0
        stats.output_tokens += resp.output_tokens or 0
        base = {**entry, "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens, "latency_ms": resp.latency_ms}

        try:
            events, errors = parse_response(resp.text, {i.item_id for i in batch})
        except ValueError as exc:
            stats.parse_failures += len(batch)
            self.log.log({**base, "status": "parse_error", "error": str(exc)[:300]})
            self._requeue(batch, results, retry_alone, attempt, str(exc))
            return
        self.log.log({**base, "status": "ok" if not errors else "parse_error",
                      "error": "; ".join(f"{k}: {v}" for k, v in list(errors.items())[:3])[:300] or None})

        by_id = {i.item_id: i for i in batch}
        for item_id, event in events.items():
            item = by_id[item_id]
            event = normalize(event, item.reference_date)
            self.cache.set(item.content_hash(self.model, PROMPT_VERSION), {"event": event.model_dump(mode="json")})
            results[item_id] = ReadResult(item, event, "llm")
        stats.parse_failures += len(errors)
        self._requeue([by_id[i] for i in errors], results, retry_alone, attempt, "invalid item")

    def _requeue(self, items: list[ReadItem], results: dict[str, ReadResult], retry_alone: list[ReadItem],
                 attempt: int, reason: str) -> None:
        for item in items:
            if attempt == 1:
                retry_alone.append(item)
            else:
                results[item.item_id] = ReadResult(item, None, "failed", reason[:200])
