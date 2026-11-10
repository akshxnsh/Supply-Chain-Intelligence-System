"""What the judge returns, plus the evidence the model is allowed to see."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

ActionType = Literal["order_replacement", "notify_customers", "review_landed_cost", "hedge_exchange_rate", "monitor", "none"]


class Claim(BaseModel):
    """One statement the recommendation rests on, and the evidence ids that support it."""

    statement: str = Field(max_length=300)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)

    @field_validator("statement", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip()


class JudgeDecision(BaseModel):
    action_type: ActionType
    recommended_action: str = Field(max_length=400)
    act_by: Optional[date] = None
    reasoning: str = Field(default="", max_length=600)
    claims: list[Claim] = Field(min_length=1, max_length=6)
    uncertainty: Optional[str] = Field(default=None, max_length=300)

    @field_validator("act_by", mode="before")
    @classmethod
    def _blank_date(cls, v):
        return None if v in ("", "unknown", "null", "None") else v

    def cited_ids(self) -> list[str]:
        return sorted({i for c in self.claims for i in c.evidence_ids})


@dataclass
class EvidenceItem:
    """One piece of source material, with the id the model must cite (a real article / notice / event id)."""

    id: str
    kind: str                      # news_article | notice | disaster | forecast | exchange_rate
    text: str
    url: str | None = None


@dataclass
class EvidenceBundle:
    """Everything the model may use: code-computed facts + citable evidence. Nothing else is shown."""

    facts: dict
    items: list[EvidenceItem] = field(default_factory=list)
    allowed_dates: set[date] = field(default_factory=set)
    act_by_limit: date | None = None          # latest act-by date the code allows
    act_by_floor: date | None = None          # earliest (today)
    allowed_action_types: set[str] = field(default_factory=set)

    def ids(self) -> set[str]:
        return {i.id for i in self.items}
