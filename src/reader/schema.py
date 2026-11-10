"""Structured output of the reader, plus the input item type.

The model may answer "unknown" for anything the text does not say; code (not the model) normalises dates and
rejects impossible values, so a wrong date from the model cannot silently become a wrong alert.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

EventType = Literal[
    "port_strike", "port_closure", "port_congestion", "severe_weather", "natural_disaster",
    "canal_or_strait_closure", "tariff_or_trade_rule", "sanctions", "accident_or_incident",
    "other_labor_action", "other", "unknown",
]
Status = Literal["happened", "ongoing", "expected", "unknown"]
Clarity = Literal["explicit", "implied", "unclear"]
Direction = Literal["delay", "higher_cost", "both", "none", "unknown"]

MAX_LIST_ITEMS = 6
MAX_FUTURE_DAYS = 730      # a date further than 2 years from the text's own date is treated as a model mistake
MAX_PAST_DAYS = 365


class ReadEvent(BaseModel):
    """What the reader returns for ONE item."""

    item_id: str
    relevant: bool = Field(description="True only if this could delay shipments or change import costs")
    event_type: EventType = "unknown"
    status: Status = "unknown"
    direction: Direction = "unknown"
    locations: list[str] = Field(default_factory=list)   # trimmed to MAX_LIST_ITEMS by the validator (a notice may name 17 countries)
    countries: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    rate_percent: Optional[float] = Field(default=None, ge=0, le=500, description="duty/tariff rate in percent if the text states one")
    date_clarity: Clarity = "unclear"
    location_clarity: Clarity = "unclear"
    summary: str = Field(default="", max_length=400)

    @field_validator("locations", "countries", "products", mode="before")
    @classmethod
    def _clean_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        out = []
        for x in v:
            x = str(x).strip()
            if x and x.lower() not in ("unknown", "n/a", "none") and x not in out:
                out.append(x[:80])
        return out[:MAX_LIST_ITEMS]  # keep the first few instead of rejecting a long (but valid) answer

    @field_validator("summary", mode="before")
    @classmethod
    def _clean_summary(cls, v):
        return (v or "").strip()[:400]

    @field_validator("start_date", "end_date", "rate_percent", mode="before")
    @classmethod
    def _blank_dates(cls, v):
        if v in ("", "unknown", "null", "None"):
            return None
        return v


def normalize(event: ReadEvent, reference_date: date) -> ReadEvent:
    """Code-side sanity checks on a validated event (never trust model dates blindly)."""
    data = event.model_copy()
    for field_name in ("start_date", "end_date"):
        d = getattr(data, field_name)
        if d is not None and not (-MAX_PAST_DAYS <= (d - reference_date).days <= MAX_FUTURE_DAYS):
            setattr(data, field_name, None)
            data.date_clarity = "unclear"
    if data.start_date and data.end_date and data.end_date < data.start_date:
        data.end_date = None
        data.date_clarity = "unclear"
    if data.start_date is None and data.end_date is None:
        data.date_clarity = "unclear"
    if not data.locations and not data.countries:
        data.location_clarity = "unclear"
    if data.status == "expected" and data.start_date is None:
        data.date_clarity = "unclear"  # an announced future event without a date is a weak signal
    return data


@dataclass
class ReadItem:
    """One piece of messy text for the reader (a news cluster or an official notice)."""

    item_id: str                     # 'news:<cluster_id>' | 'notice:<document_number>'
    source_type: str                 # news | notice
    reference_date: date             # when the text was published / first seen (relative dates resolve against it)
    lines: list[str]                 # the text the model may use (headlines, notice title/abstract/dates text)
    meta: dict = field(default_factory=dict)  # carried through, never shown to the model (cluster_id, sources, url ...)

    def text(self) -> str:
        return "\n".join(self.lines)

    def content_hash(self, model: str, prompt_version: str) -> str:
        raw = "\x1f".join([prompt_version, model, self.source_type, self.reference_date.isoformat(), self.text()])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
