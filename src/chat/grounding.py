"""Code check that an "Ask ChainGuard" answer only says things the tools actually returned.

The model may phrase and summarise; it may not bring its own facts. This check (same idea as the judge's) finds, in the answer text:
  - numbers that appear nowhere in the tool results (within 0.5%),
  - dates that appear nowhere in the tool results,
  - alert ids that no tool returned (an invented reference),
and returns them as readable problems. Words for numbers ("two") and month names are not checked; list markers ("1.") are ignored.
"""

from __future__ import annotations

import json
import re
from datetime import date

from src.judge.verify import DATE_RE, TEXT_DATE_RE, MONTHS, _close, _numbers_in, _walk_numbers

ID_RE = re.compile(r"\b[0-9a-f]{16,}\b")
LIST_MARKER = re.compile(r"(?m)^\s*(?:[-*]\s*)?\d{1,2}[.)]\s")


def _dates_in(text: str) -> set[date]:
    out: set[date] = set()
    for y, m, d in DATE_RE.findall(text):
        try:
            out.add(date(int(y), int(m), int(d)))
        except ValueError:
            pass
    for month, d, y in TEXT_DATE_RE.findall(text):
        try:
            out.add(date(int(y), MONTHS[month.lower()], int(d)))
        except ValueError:
            pass
    return out


def check_grounding(answer: str, tool_outputs: list[dict]) -> list[str]:
    """Problems found in `answer` given everything the tools returned (empty list = grounded)."""
    blob = json.dumps(tool_outputs, default=str)
    known_numbers: set[float] = set()
    _walk_numbers(tool_outputs, known_numbers)
    known_dates = _dates_in(blob)
    known_ids = set(ID_RE.findall(blob))

    issues: list[str] = []
    for i in sorted(set(ID_RE.findall(answer)) - known_ids):
        issues.append(f"alert id {i} was not returned by any lookup")
    text = ID_RE.sub(" ", LIST_MARKER.sub(" ", answer))
    seen: set[float] = set()
    for n in _numbers_in(text):
        if n not in seen and not _close(n, known_numbers):
            seen.add(n)
            issues.append(f"number {n:g} is not in the data the lookups returned")
    for d in sorted(_dates_in(text) - known_dates):
        issues.append(f"date {d} is not in the data the lookups returned")
    return issues
