"""Exposure: what could this signal cost the trader, and could stock run out?

All maths is here, in code (the model never computes money). Formulas, each parameter from config/risk.yaml:

  delay signal:  loss = SUM(shipment value x delay_cost_rate_per_day x delay_days)               holding / expediting cost
                      + SUM_per_category( min(uncovered late demand, matched shipment value) x late_order_loss_rate )
                 where uncovered late demand = pending orders in that category due by (arrival + delay) minus the
                 inventory on hand for that category.
  tariff signal: loss = rate% x value of the matched shipments (that arrive after the effective date)
  fx signal:     loss = move% x value of pending orders in the categories bought from that currency's countries

  stockout risk (any delay signal): days of stock < expected delay + replacement lead time
                 days of stock = inventory value / daily demand; daily demand = pending order value spread evenly until
                 the last required-by date (at least 7 days). This alerts regardless of the money amount.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from src.risk.matching import Match
from src.risk.signals import DELAY, FX, TARIFF, Signal


@dataclass
class StockInfo:
    category: str
    inventory_value: float
    daily_demand: float
    days_of_stock: float | None          # None = no demand, stock never runs out
    delay_days: float
    replacement_lead_days: float
    stockout_risk: bool
    stockout_date: date | None
    act_by: date | None                  # latest day to order a replacement so it arrives before stock runs out
    explanation: str


@dataclass
class Exposure:
    signal: Signal
    matches: list[Match]
    loss_if_happens_usd: float
    components: dict[str, float]
    affected_shipment_ids: list[str]
    affected_suppliers: list[dict]
    categories: list[str]
    stock: list[StockInfo] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    @property
    def stockout_risk(self) -> bool:
        return any(s.stockout_risk for s in self.stock)

    @property
    def worst_stock(self) -> StockInfo | None:
        risky = [s for s in self.stock if s.stockout_risk]
        return min(risky, key=lambda s: s.act_by or date.max) if risky else None


@dataclass
class CompanyData:
    orders: list[dict]                   # pending orders: product_category, order_value_usd, required_by_date
    inventory: dict[str, float]          # category -> inventory value
    replacement_lead_days: dict[str, float]  # category -> shortest known alternative-supplier lead time
    alternatives: dict[str, dict] = field(default_factory=dict)  # category -> best alternative supplier row


def _d(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).date() if v.tzinfo else v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def _eta_date(shipment: dict) -> date | None:
    return _d(shipment.get("eta") or shipment.get("eta_date") or shipment.get("estimated_arrival")
              or shipment.get("expected_arrival_date"))


def stock_for_category(category: str, company: CompanyData, delay_days: float, cfg: dict, today: date) -> StockInfo:
    orders = [o for o in company.orders if o.get("product_category") == category]
    pending_value = sum(float(o.get("order_value_usd") or 0) for o in orders)
    last_due = max((_d(o["required_by_date"]) for o in orders if o.get("required_by_date")), default=None)
    span = max(7, (last_due - today).days) if last_due else 7
    daily = pending_value / span if pending_value else 0.0
    inv = float(company.inventory.get(category, 0.0))
    lead = float(company.replacement_lead_days.get(category, cfg["loss_model"]["default_replacement_lead_time_days"]))
    if daily <= 0:
        return StockInfo(category, inv, 0.0, None, delay_days, lead, False, None, None,
                         f"{category}: no pending demand, stock cannot run out")
    days = inv / daily
    need = delay_days + lead
    risk = days < need
    stockout = today + timedelta(days=int(days))
    act_by = max(today, today + timedelta(days=int(days - lead))) if risk else None
    text = (f"{category}: stock covers {days:.0f} days; delay {delay_days:g} + replacement lead time {lead:g} = {need:g} days -> "
            + ("STOCKOUT RISK" if risk else "no stockout risk"))
    return StockInfo(category, inv, round(daily, 2), round(days, 1), delay_days, lead, risk,
                     stockout if risk else None, act_by, text)


def _suppliers(matches: list[Match]) -> list[dict]:
    seen, out = set(), []
    for m in matches:
        sid = m.shipment.get("supplier_id")
        if sid and sid not in seen:
            seen.add(sid)
            out.append({"supplier_id": sid, "supplier_name": m.shipment.get("supplier_name"), "country": m.shipment.get("country")})
    return out


def compute_exposure(sig: Signal, matches: list[Match], company: CompanyData, cfg: dict, today: date) -> Exposure:
    lm = cfg["loss_model"]
    comps: dict[str, float] = {}
    assumptions: list[str] = []
    cats = sorted({m.shipment.get("product_category") for m in matches if m.shipment.get("product_category")})
    stock: list[StockInfo] = []

    if sig.kind == DELAY:
        delay = sig.expected_delay_days
        comps["delay_cost"] = sum(float(m.shipment.get("shipment_value_usd") or 0) * lm["delay_cost_rate_per_day"] * delay for m in matches)
        late_total = 0.0
        for cat in cats:
            cat_matches = [m for m in matches if m.shipment.get("product_category") == cat]
            ship_value = sum(float(m.shipment.get("shipment_value_usd") or 0) for m in cat_matches)
            etas = [e for m in cat_matches if (e := _eta_date(m.shipment))]
            arrival = (max(etas) if etas else today) + timedelta(days=int(delay))
            due_value = sum(float(o.get("order_value_usd") or 0) for o in company.orders
                            if o.get("product_category") == cat and _d(o.get("required_by_date")) and _d(o["required_by_date"]) <= arrival)
            uncovered = max(0.0, due_value - company.inventory.get(cat, 0.0))
            late_total += min(uncovered, ship_value) * lm["late_order_loss_rate"]
            stock.append(stock_for_category(cat, company, delay, cfg, today))
        comps["late_orders"] = late_total
        assumptions.append(f"expected delay {delay:g} day(s) (config default for {sig.event_type}; the sources do not give a delay length)")
    elif sig.kind == TARIFF:
        comps["tariff"] = sum(float(m.shipment.get("shipment_value_usd") or 0) * (sig.rate_percent or 0) / 100.0 for m in matches)
        if sig.rate_assumed:
            assumptions.append(f"tariff rate not stated in the notice: assumed {sig.rate_percent:g}% (config)")
    elif sig.kind == FX:
        cat_set = {m.shipment.get("product_category") for m in matches}
        pending = sum(float(o.get("order_value_usd") or 0) for o in company.orders if o.get("product_category") in cat_set)
        comps["fx"] = pending * (sig.fx_move_pct or 0) / 100.0
        assumptions.append("exchange-rate loss = move % x value of pending orders in the affected categories")

    total = round(sum(comps.values()), 2)
    return Exposure(sig, matches, total, {k: round(v, 2) for k, v in comps.items()},
                    sorted({str(m.shipment.get("shipment_id") or m.shipment.get("id")) for m in matches}),
                    _suppliers(matches), cats, stock, assumptions)
