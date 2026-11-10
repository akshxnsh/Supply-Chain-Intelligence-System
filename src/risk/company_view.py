"""Read-only views of a business's inbound shipments and stock cover, shared by the dashboard API and "Ask ChainGuard".

Every query runs in a READ ONLY transaction. Stock cover uses the same function the alerts use (risk.exposure.stock_for_category),
so the screen, the chat answers and the alerts always agree.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from src.ingestion.db import run_query_readonly

SQL_SHIPMENTS = """
    SELECT st.id AS shipment_id, bs.supplier_name, bs.country AS supplier_country, st.product_category, st.shipment_value_usd,
           st.origin_port, st.destination_port, st.route, st.etd::date AS departed, st.eta::date AS arrives
    FROM shipment_timetable st JOIN business_suppliers bs ON bs.id = st.supplier_id
    WHERE st.business_id = %(b)s AND st.status = 'in_transit'
    ORDER BY st.eta LIMIT %(limit)s
"""
SQL_INVENTORY = "SELECT product_category, inventory_value_usd FROM inventory WHERE business_id = %(b)s"
SQL_ORDERS = """
    SELECT product_category, order_value_usd, required_by_date FROM pending_orders
    WHERE business_id = %(b)s AND status = 'pending'
"""


def monitored_business_ids() -> list[str]:
    """Businesses the scheduled pipeline analyses (PIPELINE_BUSINESSES, default demo-business-001)."""
    return [b for b in os.getenv("PIPELINE_BUSINESSES", "demo-business-001").split(",") if b]


def shipments(business_id: str, limit: int = 50) -> list[dict]:
    """In-transit shipments, soonest arrival first."""
    return run_query_readonly(SQL_SHIPMENTS, {"b": business_id, "limit": max(1, int(limit))})


def stock_cover(business_id: str) -> list[dict]:
    """Per product category: inventory value, pending order value, daily demand and days of stock (computed by code)."""
    from src.risk.config import load_config
    from src.risk.exposure import CompanyData, stock_for_category

    inv = {r["product_category"]: float(r["inventory_value_usd"]) for r in run_query_readonly(SQL_INVENTORY, {"b": business_id})}
    orders = run_query_readonly(SQL_ORDERS, {"b": business_id})
    today = datetime.now(timezone.utc).date()
    cfg, company = load_config(), CompanyData(orders, inv, {})
    out = []
    for cat in sorted(set(inv) | {o["product_category"] for o in orders}):
        s = stock_for_category(cat, company, 0.0, cfg, today)
        pending = sum(float(o["order_value_usd"]) for o in orders if o["product_category"] == cat)
        out.append({"product_category": cat, "inventory_value_usd": round(s.inventory_value), "pending_orders_value_usd": round(pending),
                    "daily_demand_usd": s.daily_demand, "days_of_stock": s.days_of_stock})
    return out


def trader_settings(business_id: str) -> dict:
    """How alerts are decided for this business: its own settings plus the (read-only) rules in config/risk.yaml."""
    from src.risk.config import load_config

    cfg = load_config()
    rows = run_query_readonly("SELECT importing_country, notify_threshold_usd FROM trader_settings WHERE business_id = %(b)s", {"b": business_id})
    mine = rows[0] if rows else {}
    a, conf, loss = cfg["alerts"], cfg["confidence"], cfg["loss_model"]
    threshold = float(mine.get("notify_threshold_usd") or a["default_notify_threshold_usd"])
    return {
        "business_id": business_id,
        "has_own_settings": bool(rows),
        "importing_country": mine.get("importing_country") or "United States",
        "notify_threshold_usd": threshold,
        "watch_floor_usd": round(threshold * float(a["watch_floor_fraction"]), 2),
        "rare_event_guard_usd": float(a["rare_event_guard_usd"]),
        "repeat_loss_increase_factor": float(a["repeat_loss_increase_factor"]),
        "likelihood_by_band": cfg["likelihood_by_band"],
        "band_cutoffs": conf["band_cutoffs"],
        "confidence_weights": conf["weights"],
        "loss_model": {"delay_cost_rate_per_day": loss["delay_cost_rate_per_day"], "late_order_loss_rate": loss["late_order_loss_rate"],
                       "tariff_horizon_days": loss["tariff_horizon_days"]},
        "horizon_days": cfg["horizon_days"],
        "default_delay_days": cfg["default_delay_days"],
    }
