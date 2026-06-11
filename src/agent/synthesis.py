"""The single model call per simulation: final judgment synthesis.

All data is gathered deterministically by src/agent/pipeline.py. This module
makes exactly ONE tool-free Gemini call whose only job is the genuine judgment
that has no code formula:

    * severity_score  (0-10, reflecting inventory coverage, expected loss, calibration)
    * disruption selection + concise summary (from a pre-built candidate shortlist)
    * purchase-order sizing (which ranked alternative, quantity, required-by date)

It is tool-free (no function-calling round-trips) so it costs exactly one
request. PO/email text is still produced by the existing deterministic template
functions in src/agent/tools.py using the params chosen here — so output format
and contracts are unchanged.

If the model is unavailable or the per-simulation budget is exhausted, a
deterministic fallback fills these fields and tags the result with
`synthesis_mode="deterministic_fallback"` so the substitution is never silent.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

MODEL = os.getenv("MODEL_NAME", "gemini-2.0-flash").removeprefix("models/")

# Compact instruction — single block, no duplicated schemas/examples (Task 4).
_SYNTHESIS_INSTRUCTION = (
    "You are the supply-chain synthesis step. All facts below are already "
    "computed by deterministic code and are authoritative — never recompute or "
    "alter them. Using ONLY this evidence, return strict JSON with:\n"
    "- severity_score: float 0-10 reflecting inventory coverage, expected loss, "
    "and the calibration baseline (higher when inventory does not cover demand).\n"
    "- chosen_event_id: id of the most material disruption from candidate_events "
    "(empty string if none).\n"
    "- disruption_type, disruption_region, disruption_summary: concise, from the "
    "chosen event.\n"
    "- po_supplier_rank: 1-based rank of the alternative to order from (1 = best); "
    "0 if no alternatives or a black swan requires human review.\n"
    "- po_quantity: integer units for the purchase order (0 if no PO).\n"
    "- po_required_by: ISO date the replacement is needed (empty if no PO).\n"
    "Do not output any field other than these."
)


class SynthesisDecision(BaseModel):
    severity_score: float = 0.0
    chosen_event_id: str = ""
    disruption_type: str = ""
    disruption_region: str = ""
    disruption_summary: str = ""
    po_supplier_rank: int = 0
    po_quantity: int = 0
    po_required_by: str = ""
    reasoning: str = Field(default="", description="one short sentence")


def _build_prompt(evidence: dict[str, Any]) -> str:
    """Compact, single-pass prompt. Targets < 4k input tokens."""
    return (
        f"{_SYNTHESIS_INSTRUCTION}\n\n"
        f"EVIDENCE (authoritative):\n{json.dumps(evidence, default=str)[:8000]}"
    )


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _deterministic_fallback(evidence: dict[str, Any]) -> SynthesisDecision:
    """Used only when the model is unavailable / budget exhausted.

    Mirrors the documented intent ("severity reflects inventory coverage,
    expected loss, calibration") without claiming to reproduce the model's
    judgment — the result is explicitly tagged downstream.
    """
    impact = evidence.get("impact", {}) or {}
    calibration = evidence.get("calibration", {}) or {}
    baseline = float(calibration.get("weighted_baseline_severity", 5.0) or 5.0)
    adjustment = float(impact.get("severity_adjustment", 1.0) or 1.0)
    severity = max(0.0, min(10.0, baseline * adjustment))

    events = evidence.get("candidate_events", []) or []
    chosen = events[0] if events else {}
    alternatives = evidence.get("alternatives", []) or []
    black_swan = bool(evidence.get("black_swan", {}).get("is_anomaly"))

    rank = 0 if (black_swan or not alternatives) else 1
    return SynthesisDecision(
        severity_score=round(severity, 2),
        chosen_event_id=str(chosen.get("id", "")),
        disruption_type=str(chosen.get("source", "disruption")),
        disruption_region=str(chosen.get("location_name", "")),
        disruption_summary=str(chosen.get("headline", "")),
        po_supplier_rank=rank,
        po_quantity=0,  # no deterministic PO-sizing formula exists; left to human review
        po_required_by="",
        reasoning="deterministic fallback (model unavailable)",
    )


def synthesize(evidence: dict[str, Any], budget) -> tuple[SynthesisDecision, str, int]:
    """Run the single synthesis model call.

    Returns (decision, mode, estimated_tokens) where mode is "model" or
    "deterministic_fallback". `budget` is a quota.CallBudget instance.
    """
    if not budget.can_call():
        _log.warning("[SYNTH] Per-simulation model budget exhausted — using fallback.")
        return _deterministic_fallback(evidence), "deterministic_fallback", 0

    prompt = _build_prompt(evidence)
    est_tokens = _estimate_tokens(prompt)

    try:
        from google import genai
        from google.genai import types as genai_types

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
                response_schema=SynthesisDecision,
                max_output_tokens=1024,
            ),
        )
        budget.record(est_tokens=est_tokens + _estimate_tokens(response.text or ""))

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, SynthesisDecision):
            return parsed, "model", est_tokens
        decision = SynthesisDecision.model_validate(json.loads(response.text))
        return decision, "model", est_tokens
    except Exception as exc:  # noqa: BLE001 — any model/parse failure → safe fallback
        _log.error("[SYNTH] Synthesis model call failed (%s) — using fallback.", exc)
        return _deterministic_fallback(evidence), "deterministic_fallback", est_tokens
