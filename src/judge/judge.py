"""The judge: ONE stronger-model call per alert that turns code-computed facts and cited evidence into an action and an
act-by date. Code then verifies the answer (src/judge/verify.py); if anything fails, a deterministic rule-based answer is used.

The model never computes money or dates. No model key / API down / bad answer -> fallback, so alerts always get an action.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from pydantic import ValidationError

from src.agent.model_config import JUDGE_MODEL
from src.judge.evidence import FACTS_ID
from src.judge.prompt import PROMPT_VERSION, build_prompt
from src.judge.schema import Claim, EvidenceBundle, JudgeDecision
from src.judge.verify import verify
from src.reader.limiter import LLMError, RateLimiter, call_with_retry
from src.reader.reader import NullLogger, extract_json
from src.risk.pipeline import AlertRow

logger = logging.getLogger(__name__)

# Gemini 2.5/3.x models spend hidden 'thinking' tokens out of this budget; 1,024 truncated every real answer
# (live run 2026-11-10: 'unterminated JSON'), so leave generous room.
MAX_OUTPUT_TOKENS = 8192


@dataclass
class JudgeResult:
    decision: JudgeDecision
    source: str                         # model | cache | fallback
    issues: list[str] = field(default_factory=list)   # why the model answer was NOT used (empty if it was)
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_decision: JudgeDecision | None = None   # what the model actually answered, even if the code rejected it (for evaluation)


_FALLBACK_ACTION = {"tariff": "review_landed_cost", "fx": "hedge_exchange_rate"}


def fallback_decision(row: AlertRow, bundle: EvidenceBundle) -> JudgeDecision:
    """Deterministic answer from the risk pipeline's own rule-based action and act-by date."""
    if row.signal.kind in _FALLBACK_ACTION:
        action_type = _FALLBACK_ACTION[row.signal.kind]
    elif row.exposure.stockout_risk:
        action_type = "order_replacement"
    else:
        action_type = "notify_customers"
    act_by = row.act_by
    if act_by and bundle.act_by_limit and act_by > bundle.act_by_limit:
        act_by = bundle.act_by_limit
    expected, possible = row.decision.expected_loss_usd, row.exposure.loss_if_happens_usd
    claim = (f"Possible loss ${possible:,.0f}, expected loss ${expected:,.0f} at {row.confidence.band} confidence "
             f"(rule-based; see the computed facts).")
    if row.exposure.unpriced_reason:
        claim = f"The loss cannot be priced: {row.exposure.unpriced_reason}."
    return JudgeDecision(action_type=action_type, recommended_action=row.action[:400], act_by=act_by,
                         reasoning="Rule-based recommendation: no verified model answer was available.",
                         claims=[Claim(statement=claim[:300], evidence_ids=[FACTS_ID])])


class Judge:
    def __init__(self, client, cache, limiter: RateLimiter | None = None, *, model: str = JUDGE_MODEL,
                 call_logger=None, max_retries: int = 3, sleep: Callable[[float], None] = time.sleep):
        self.client, self.cache, self.limiter = client, cache, limiter
        self.model, self.max_retries, self._sleep = model, max_retries, sleep
        self.log = call_logger or NullLogger()

    def _key(self, bundle: EvidenceBundle) -> str:
        return hashlib.sha256(f"{PROMPT_VERSION}{self.model}{build_prompt(bundle)}".encode()).hexdigest()

    def is_cached(self, row: AlertRow, bundle: EvidenceBundle) -> bool:
        return bool(self.cache and self.cache.get(self._key(bundle)))

    def judge(self, row: AlertRow, bundle: EvidenceBundle) -> JudgeResult:
        prompt = build_prompt(bundle)
        key = self._key(bundle)
        entry = {"purpose": "judge", "kind": "call", "model": self.model, "prompt_version": PROMPT_VERSION, "batch_size": 1,
                 "attempt": 1, "cache_hits": 0, "cache_misses": 1}

        hit = self.cache.get(key) if self.cache else None
        if hit:
            try:
                decision = JudgeDecision.model_validate(hit["decision"])
                if not verify(decision, bundle):
                    self.log.log({**entry, "kind": "cache_summary", "cache_hits": 1, "cache_misses": 0, "status": "cache"})
                    return JudgeResult(decision, "cache", [], self.model)
            except (ValidationError, KeyError):
                pass  # stale / corrupt entry: ask again

        if self.client is None:
            return self._fallback(row, bundle, ["no model client (GEMINI_API_KEY missing): rule-based answer used"])

        def on_retry(n: int, exc: Exception, delay: float) -> None:
            self.log.log({**entry, "status": "retry", "error": f"try {n}: {exc}"[:300]})

        try:
            resp = call_with_retry(lambda: self.client.generate(prompt, self.model, temperature=0.1, max_output_tokens=MAX_OUTPUT_TOKENS),
                                   limiter=self.limiter, max_retries=self.max_retries, sleep=self._sleep, on_retry=on_retry)
        except LLMError as exc:
            self.log.log({**entry, "status": "error", "error": str(exc)[:300]})
            return self._fallback(row, bundle, [f"model unavailable: {exc}"[:300]])

        base = {**entry, "input_tokens": resp.input_tokens, "output_tokens": resp.output_tokens, "latency_ms": resp.latency_ms}
        try:
            decision = JudgeDecision.model_validate(extract_json(resp.text))
        except (ValueError, ValidationError) as exc:
            self.log.log({**base, "status": "parse_error", "error": str(exc)[:300]})
            return self._fallback(row, bundle, [f"model answer was not valid: {str(exc)[:200]}"], resp)

        issues = verify(decision, bundle)
        if issues:
            self.log.log({**base, "status": "rejected", "error": "; ".join(issues)[:300]})
            return self._fallback(row, bundle, issues, resp, decision)

        self.log.log({**base, "status": "ok"})
        if self.cache:
            self.cache.set(key, {"decision": decision.model_dump(mode="json")})
        return JudgeResult(decision, "model", [], self.model, resp.input_tokens, resp.output_tokens, decision)

    def _fallback(self, row: AlertRow, bundle: EvidenceBundle, issues: list[str], resp=None, model_decision=None) -> JudgeResult:
        return JudgeResult(fallback_decision(row, bundle), "fallback", issues, self.model,
                           getattr(resp, "input_tokens", None), getattr(resp, "output_tokens", None), model_decision)
