"""The only things "Ask ChainGuard" can do: five read-only lookups, all bound to ONE business.

- Read-only twice over: every query runs through run_query_readonly (a READ ONLY database transaction) and none of them writes.
- The business is fixed when the tools are made, never a tool argument, so a question cannot reach another business's data.
- Answers are small (a few rows, short strings) and carry a `count`, so the model quotes numbers instead of calculating them.
- A tool never raises: a database problem comes back as {"error": ...} and the model is told to say it could not look it up.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable

from src.ingestion.db import run_query_readonly
from src.risk import company_view

MAX_ROWS = 12
MAX_TEXT = 300


def _clip(value, n: int = MAX_TEXT):
    return value[:n] + "..." if isinstance(value, str) and len(value) > n else value


def _plain(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [_plain(v) for v in value[:8]]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return _clip(value)


def _safe(fn: Callable[[], dict]) -> dict:
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a tool must never raise into the agent loop
        return {"error": f"could not look that up ({exc.__class__.__name__})"}


SQL_ALERT_LIST = """
    SELECT alert_id, level, alert_type, title, expected_loss_usd, exposure_usd, confidence_band, stockout_risk, lead_time_days,
           act_by, action, judge_source, last_seen
    FROM alerts
    WHERE business_id = %(b)s AND status = 'open' AND (%(level)s::text IS NULL OR level = %(level)s)
    ORDER BY CASE level WHEN 'notify' THEN 0 WHEN 'watch' THEN 1 ELSE 2 END, expected_loss_usd DESC, last_seen DESC
    LIMIT %(limit)s
"""

SQL_ALERT_DETAIL = """
    SELECT alert_id, level, alert_type, status, title, source, event_type, signal_kind, exposure_usd, expected_loss_usd, loss_components,
           confidence_band, confidence_score, confidence_reasons, stockout_risk, lead_time_days, event_start, event_end, act_by,
           action, judge_source, judge_reasoning, judge_claims, explanation, assumptions, evidence, affected_shipments,
           affected_suppliers, first_seen, last_seen
    FROM alerts WHERE alert_id = %(id)s AND business_id = %(b)s
"""

def make_tools(business_id: str) -> list[Callable]:
    """The tool functions the agent may call (ADK reads each function's name, signature and docstring)."""

    def list_open_alerts(level: str = "", limit: int = 8) -> dict:
        """List this business's open risk alerts, most important first (Notify, then Watch, then Log; larger expected loss first).

        Args:
            level: optional filter, one of "notify", "watch", "log"; empty for all levels.
            limit: how many alerts to return (1-12).
        Returns: count and a list of alerts with alert_id, level, type (now / heads_up), title, expected_loss_usd, exposure_usd,
        confidence_band, stockout_risk, lead_time_days, act_by and the recommended action.
        """
        def go():
            lv = level.strip().lower() or None
            if lv not in (None, "notify", "watch", "log"):
                return {"error": "level must be notify, watch, log or empty"}
            rows = run_query_readonly(SQL_ALERT_LIST, {"b": business_id, "level": lv, "limit": max(1, min(int(limit), MAX_ROWS))})
            return {"count": len(rows), "level_filter": lv, "alerts": [_plain(r) for r in rows]}
        return _safe(go)

    def get_alert_details(alert_id: str) -> dict:
        """Everything behind ONE alert: the money (possible loss, expected loss, components), why the confidence is high / medium / low,
        the evidence it was built from, why it did or did not notify, the recommended action and act-by date, affected suppliers.

        Args:
            alert_id: an alert_id returned by list_open_alerts.
        """
        def go():
            rows = run_query_readonly(SQL_ALERT_DETAIL, {"id": alert_id.strip(), "b": business_id})
            return _plain(rows[0]) if rows else {"error": f"no alert {alert_id!r} for this business"}
        return _safe(go)

    def list_shipments(limit: int = 10) -> dict:
        """List this business's inbound shipments that are on the way: supplier, product category, value, route, when they left and arrive.

        Args:
            limit: how many shipments to return (1-12), soonest arrival first.
        """
        def go():
            rows = company_view.shipments(business_id, min(max(1, int(limit)), MAX_ROWS))
            return {"count": len(rows), "shipments": [_plain(r) for r in rows]}
        return _safe(go)

    def get_stock_and_orders() -> dict:
        """Stock cover per product category: inventory value, pending customer order value, daily demand and how many days the stock lasts
        (computed by code, same formula as the alerts)."""
        def go():
            out = company_view.stock_cover(business_id)
            return {"count": len(out), "categories": out}
        return _safe(go)

    def data_freshness() -> dict:
        """How fresh each external data source is (news, disasters, ports, trade notices, weather forecast, exchange rates):
        minutes since the last sync and whether that is stale."""
        def go():
            from src.agent.freshness_agent import _table_freshness
            from src.agent.freshness_config import configured_table_names

            rows = [_table_freshness(t) for t in configured_table_names()]
            return {"count": len(rows), "sources": [{"source": r["table_name"], "minutes_since_sync": r["age_minutes"],
                                                    "max_minutes": r["max_age_minutes"], "stale": r["is_stale"],
                                                    "measured_from": r.get("measured_from")} for r in rows]}
        return _safe(go)

    return [list_open_alerts, get_alert_details, list_shipments, get_stock_and_orders, data_freshness]
