"""Confidence: computed in code, never by the model. Shown as High / Medium / Low plus the reasons.

Six parts, each scored 0..1 from the config (our own judgment, stated as an estimate):
  source type, independent confirmation, forecast distance, text clarity, match precision, age.
A part that does not apply to a signal (e.g. forecast distance for a news item) is left out and the weights of the
others are renormalised, so a signal is not punished for something that does not exist for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

BANDS = ("low", "medium", "high")


@dataclass
class ConfidenceInput:
    source_class: str                      # official_notice | official_alert | observed_data | forecast_model | news
    independent_sources: int = 1
    days_ahead: float | None = None        # forecast signals only
    date_clarity: str | None = None        # reader-read signals only: explicit | implied | unclear
    location_clarity: str | None = None
    match_precision: str | None = None     # port | chokepoint | country | region
    reference_date: date | None = None     # when the information was published
    today: date | None = None


@dataclass
class ConfidenceResult:
    score: float
    band: str                              # low | medium | high
    reasons: list[str] = field(default_factory=list)
    parts: dict[str, float] = field(default_factory=dict)


def _age_score(age_days: float, table: list[list[float]]) -> float:
    for max_age, score in table:
        if age_days <= max_age:
            return score
    return table[-1][1]


def band_for(score: float, cutoffs: dict[str, float]) -> str:
    if score >= cutoffs["high"]:
        return "high"
    if score >= cutoffs["medium"]:
        return "medium"
    return "low"


def compute_confidence(inp: ConfidenceInput, cfg: dict) -> ConfidenceResult:
    c = cfg["confidence"]
    weights = c["weights"]
    parts: dict[str, float] = {}
    reasons: list[str] = []

    # (1) source type
    parts["source"] = c["source_scores"][inp.source_class]
    reasons.append(f"source: {inp.source_class.replace('_', ' ')} ({parts['source']:.2f})")

    # (2) independent confirmation (only for news-like sources: an official notice is already one authority)
    if inp.source_class == "news":
        n = max(1, inp.independent_sources)
        table = {int(k): v for k, v in c["confirmation_scores"].items()}
        parts["confirmation"] = table[min(n, max(table))]
        reasons.append(f"{n} independent outlet{'s' if n != 1 else ''} ({parts['confirmation']:.2f})")

    # (3) forecast distance
    if inp.days_ahead is not None:
        fd = c["forecast_distance"]
        parts["forecast_distance"] = max(fd["floor"], 1.0 - fd["per_day"] * max(0.0, inp.days_ahead))
        reasons.append(f"forecast {inp.days_ahead:.0f} day(s) ahead ({parts['forecast_distance']:.2f})")

    # (4) how clearly the text stated date and place (reader-read signals)
    if inp.date_clarity or inp.location_clarity:
        cs = c["clarity_scores"]
        vals = [cs[x] for x in (inp.date_clarity, inp.location_clarity) if x]
        parts["clarity"] = sum(vals) / len(vals)
        reasons.append(f"text clarity: date {inp.date_clarity or 'n/a'}, place {inp.location_clarity or 'n/a'} ({parts['clarity']:.2f})")

    # (5) match precision
    if inp.match_precision:
        parts["match"] = c["match_scores"][inp.match_precision]
        reasons.append(f"matched at {inp.match_precision} level ({parts['match']:.2f})")

    # (6) age of the information
    if inp.reference_date and inp.today:
        age = max(0, (inp.today - inp.reference_date).days)
        parts["age"] = _age_score(age, c["age_scores"])
        reasons.append(f"information is {age} day(s) old ({parts['age']:.2f})")

    total_w = sum(weights[k] for k in parts)
    score = sum(weights[k] * v for k, v in parts.items()) / total_w
    band = band_for(score, c["band_cutoffs"])
    return ConfidenceResult(score=round(score, 3), band=band, reasons=reasons, parts=parts)
