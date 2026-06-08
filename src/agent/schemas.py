from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AlternativeSupplier(BaseModel):
    model_config = ConfigDict(extra="allow")

    rank: int
    supplier_id: str
    name: str
    country: str
    unit_price_usd: float
    unit_price_difference_usd: float = 0
    total_cost_premium_usd: float = 0
    lead_time_days: int
    dynamic_reliability_score: float = 0
    on_time_rate: float | None = None
    avg_review_rating: float | None = None
    completed_orders_count: int = 0
    total_score: float = 0
    tradeoff_summary: str = ""


class SupplyChainAnalysis(BaseModel):
    model_config = ConfigDict(extra="allow")

    alert_fired: bool = False
    disruption: dict[str, Any] = Field(default_factory=dict)
    signals_detected: list[str] = Field(default_factory=list)
    exposure_usd: float = 0
    expected_loss_usd: float = 0
    affected_suppliers: list[dict[str, Any]] = Field(default_factory=list)
    severity_score: float = 0
    calibration_confidence: float = 0
    black_swan_detected: bool = False
    suggested_alternatives: list[AlternativeSupplier] = Field(default_factory=list)
    top_supplier: Any = None
    purchase_order: Any = None
    owner_email: Any = None
