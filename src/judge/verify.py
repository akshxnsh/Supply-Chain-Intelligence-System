"""Code checks on the judge's answer. The model proposes; this module decides whether the proposal may be used.

Checks (any failure rejects the whole answer -> deterministic fallback):
  1. the action type is allowed for this kind of alert;
  2. every claim cites at least one evidence id, and every cited id exists (real article / notice / event ids, or "facts");
  3. every number written anywhere in the answer appears in the FACTS or the EVIDENCE text (within 0.5%);
  4. every date written anywhere in the answer is a date the code knows (today, event window, stock-out / order dates, ETAs);
  5. the act-by date lies between today and the latest date the code allows.
Words for numbers ("two days") and month names are not checked, which is why the prompt asks for digits and ISO dates.
"""

from __future__ import annotations

import math
import re
from datetime import date

from src.judge.schema import EvidenceBundle, JudgeDecision

DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
NUM_RE = re.compile(r"(?<![\w.:/\-])\$?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?\s*(%|k\b|K\b|m\b|M\b)?")
SCALE = {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}
REL_TOL = 0.005


def _numbers_in(text: str) -> list[float]:
    text = DATE_RE.sub(" ", text or "")
    out = []
    for m in NUM_RE.finditer(text):
        value = float(m.group(1).replace(",", "") + (m.group(2) or ""))
        if m.group(3) in SCALE:
            value *= SCALE[m.group(3)]
        out.append(value)
    return out


def _walk_numbers(obj, acc: set[float]) -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        acc.update({float(obj), float(round(obj)), float(math.floor(obj)), float(math.ceil(obj)), round(float(obj), 1)})
    elif isinstance(obj, str):
        acc.update(_numbers_in(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk_numbers(v, acc)
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            _walk_numbers(v, acc)


def allowed_numbers(bundle: EvidenceBundle) -> set[float]:
    acc: set[float] = set()
    _walk_numbers(bundle.facts, acc)
    for item in bundle.items:
        acc.update(_numbers_in(item.text))
    return acc


def _close(x: float, allowed: set[float]) -> bool:
    return any(abs(x - a) <= max(0.05, REL_TOL * abs(a)) for a in allowed)


def _texts(d: JudgeDecision) -> list[tuple[str, str]]:
    out = [("recommended_action", d.recommended_action), ("reasoning", d.reasoning)]
    if d.uncertainty:
        out.append(("uncertainty", d.uncertainty))
    out += [(f"claim {i + 1}", c.statement) for i, c in enumerate(d.claims)]
    return out


def verify(decision: JudgeDecision, bundle: EvidenceBundle) -> list[str]:
    """Return the list of problems; empty = the answer may be used."""
    issues: list[str] = []

    if decision.action_type not in bundle.allowed_action_types:
        issues.append(f"action_type '{decision.action_type}' not allowed here (allowed: {sorted(bundle.allowed_action_types)})")

    known = bundle.ids()
    for i, c in enumerate(decision.claims, 1):
        if not c.statement:
            issues.append(f"claim {i} is empty")
        unknown = [e for e in c.evidence_ids if e not in known]
        if unknown:
            issues.append(f"claim {i} cites unknown evidence id(s): {unknown}")

    allowed = allowed_numbers(bundle)
    seen_numbers, seen_dates = set(), set()
    for where, text in _texts(decision):
        for n in _numbers_in(text):
            if n not in seen_numbers and not _close(n, allowed):
                seen_numbers.add(n)
                issues.append(f"number {n:g} in {where} is not in the facts or evidence")
        for y, mth, d in DATE_RE.findall(text):
            try:
                dt = date(int(y), int(mth), int(d))
            except ValueError:
                issues.append(f"invalid date {y}-{mth}-{d} in {where}")
                continue
            if dt not in bundle.allowed_dates and dt not in seen_dates:
                seen_dates.add(dt)
                issues.append(f"date {dt} in {where} is not one of the dates the system computed")

    if decision.act_by is not None:
        if bundle.act_by_floor and decision.act_by < bundle.act_by_floor:
            issues.append(f"act_by {decision.act_by} is before today ({bundle.act_by_floor})")
        if bundle.act_by_limit and decision.act_by > bundle.act_by_limit:
            issues.append(f"act_by {decision.act_by} is after the latest allowed date ({bundle.act_by_limit})")
    return issues
