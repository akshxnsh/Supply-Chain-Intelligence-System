"""All SQL used by the app, written for PostgreSQL.

Hot-path SQL lives in module-level constants so scripts/benchmark_db.py can run
EXPLAIN ANALYZE on exactly the statements the app runs. Values are always bound
parameters (never string-formatted into SQL).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.ingestion.db import execute, insert_rows, run_query


@dataclass
class AlertRecord:
    """Validated shape for agent_alerts rows. Matches the agent_alerts table."""
    id: str
    business_id: str
    created_at: str          # ISO 8601 string
    disruption_id: Optional[str] = None
    severity_score: Optional[float] = None
    exposure_usd: Optional[float] = None
    actions_json: Optional[str] = None
    status: str = "active"

    def __post_init__(self):
        if not self.id:
            raise ValueError("AlertRecord.id is required")
        if not self.business_id:
            raise ValueError("AlertRecord.business_id is required")
        if not self.created_at:
            raise ValueError("AlertRecord.created_at is required")
        if self.severity_score is not None and not (0.0 <= self.severity_score <= 10.0):
            raise ValueError(f"severity_score must be 0-10, got {self.severity_score}")


# ── Hot-path SQL (also benchmarked) ───────────────────────────────────────────

SQL_RECENT_EVENTS = """
    SELECT id, source, headline, location_name, lat, lon, severity_raw,
           published_at::text AS published_at
    FROM disruption_events
    WHERE published_at >= now() - make_interval(hours => %(hours)s)
    ORDER BY published_at DESC
    LIMIT 50
"""

SQL_BUSINESS_SUPPLIERS = """
    SELECT id, supplier_name, country, product_category, annual_spend_usd
    FROM business_suppliers
    WHERE business_id = %(business_id)s
"""

SQL_PENDING_ORDERS = """
    SELECT id, client_id, product_category, quantity, order_value_usd,
           required_by_date::text AS required_by_date, status
    FROM pending_orders
    WHERE business_id = %(business_id)s AND status = 'pending'
"""

SQL_ALTERNATIVE_SUPPLIERS = """
    SELECT id, name, country, product_category,
           moq, lead_time_days, unit_price_usd, reliability_score, geographic_risk_score
    FROM alternative_suppliers
    WHERE product_category = %(product_category)s
      AND country != %(exclude_country)s
    ORDER BY reliability_score DESC
    LIMIT 5
"""

SQL_PORT_STATUS = """
    SELECT port_id, port_name, congestion_score, vessel_delay_hours, strike_flag
    FROM port_activity
    WHERE lower(port_name) LIKE %(pattern)s
"""

SQL_CALIBRATION_RECORDS = """
    SELECT severity_scored, actual_delay_days, hallucination_score, relevance_score,
           helpfulness_score, reasoning_score,
           floor(extract(epoch FROM (now() - created_at)) / 86400)::int AS days_ago
    FROM agent_calibration
    WHERE event_type = %(event_type)s
      AND region = %(region)s
      AND severity_scored IS NOT NULL
      AND actual_delay_days IS NOT NULL
      AND created_at >= now() - make_interval(days => %(days_lookback)s)
    ORDER BY created_at DESC
"""

SQL_SHIPMENTS_AT_RISK = """
    SELECT id, supplier_id, product_category, quantity, shipment_value_usd,
           expected_arrival_date::text AS expected_arrival_date,
           origin_port, destination_port,
           etd::text AS etd, eta::text AS eta,
           journey_time_hours, route, status
    FROM shipment_timetable
    WHERE business_id = %(business_id)s
      AND supplier_id = ANY(%(supplier_ids)s)
      AND status = 'in_transit'
      AND expected_arrival_date <= CURRENT_DATE + %(window_days)s::int
    ORDER BY expected_arrival_date ASC
"""

SQL_SUPPLIERS_BY_COUNTRY = """
    SELECT id, supplier_name, product_category, annual_spend_usd
    FROM business_suppliers
    WHERE business_id = %(business_id)s
      AND lower(country) = lower(%(country)s)
"""

SQL_WEATHER_BY_REGION = """
    SELECT id, region, alert_type, severity, affected_ports,
           start_time::text AS start_time, end_time::text AS end_time
    FROM weather_alerts
    WHERE lower(region) LIKE %(pattern)s
      AND start_time >= now() - make_interval(hours => %(hours_back)s)
    ORDER BY severity DESC
"""

SQL_RECENT_WEATHER = """
    SELECT id, region, alert_type, severity, affected_ports,
           start_time::text AS start_time, end_time::text AS end_time
    FROM weather_alerts
    WHERE start_time >= now() - make_interval(hours => %(hours_back)s)
    ORDER BY severity DESC, start_time DESC
"""

SQL_TARIFFS = """
    SELECT id, country_of_origin, product_category, tariff_rate_percentage,
           effective_date::text AS effective_date, description
    FROM tariff_updates
    WHERE effective_date >= CURRENT_DATE - %(days_back)s::int
    ORDER BY effective_date DESC
"""

SQL_INVENTORY = """
    SELECT product_category, inventory_value_usd
    FROM inventory
    WHERE business_id = %(business_id)s
"""

SQL_COMPLETED_ORDERS_MANY = """
    SELECT supplier_id, delay_days, defective_items_count, status,
           expected_delivery_date::text AS expected_delivery_date,
           actual_delivery_date::text AS actual_delivery_date
    FROM completed_orders
    WHERE supplier_id = ANY(%(supplier_ids)s)
      AND status = 'delivered'
    ORDER BY expected_delivery_date DESC
"""

SQL_REVIEWS_MANY = """
    SELECT supplier_id, rating, review_text, review_date::text AS review_date
    FROM supplier_reviews
    WHERE supplier_id = ANY(%(supplier_ids)s)
    ORDER BY review_date DESC
"""

SQL_TIMETABLE = """
    SELECT st.id AS shipment_id, st.supplier_id, bs.supplier_name, bs.country,
           st.product_category, st.shipment_value_usd, st.quantity,
           st.origin_port, st.destination_port,
           st.dispatched_date::text AS dispatched_date,
           st.expected_arrival_date::text AS eta_date,
           st.dispatched_date::text AS dispatch_timestamp,
           st.expected_arrival_date::text AS estimated_arrival,
           st.etd::text AS etd, st.eta::text AS eta,
           st.journey_time_hours, st.route, st.status
    FROM shipment_timetable st
    JOIN business_suppliers bs ON st.supplier_id = bs.id
    WHERE st.business_id = %(business_id)s
      AND st.status = 'in_transit'
    ORDER BY st.expected_arrival_date ASC
"""

SQL_ALERTS_PAGE = """
    SELECT al.id, al.business_id, al.severity_score, al.exposure_usd, al.status,
           al.created_at::text AS created_at,
           (SELECT round(avg(
                (coalesce(c.relevance_score, 0.85)
                 + coalesce(c.helpfulness_score, 0.85)
                 + coalesce(c.reasoning_score, 0.85)
                 + (1 - coalesce(c.hallucination_score, 0.1))) / 4
            )::numeric, 2)::float
            FROM agent_calibration c
            WHERE c.region = al.business_id
              AND c.calibration_applied = TRUE) AS calibration_confidence
    FROM agent_alerts al
    WHERE al.business_id = %(business_id)s
    ORDER BY al.created_at DESC
    LIMIT %(limit)s OFFSET %(offset)s
"""

SQL_ALERTS_ALL = """
    SELECT id, business_id, severity_score, exposure_usd, status,
           created_at::text AS created_at
    FROM agent_alerts
    ORDER BY severity_score DESC, created_at DESC
    LIMIT %(limit)s
"""

SQL_SUPPLIERS_OVERVIEW = """
    SELECT bs.supplier_name, bs.country, bs.product_category, bs.annual_spend_usd,
           (SELECT count(*) - 1 FROM business_suppliers x
             WHERE x.business_id = %(business_id)s
               AND x.product_category = bs.product_category) AS other_suppliers_count,
           (SELECT round(avg(co.delay_days)::numeric, 1)::float FROM completed_orders co
             WHERE co.supplier_id = bs.id AND co.status = 'delivered') AS avg_delay_days
    FROM business_suppliers bs
    WHERE bs.business_id = %(business_id)s
"""

SQL_DUPLICATE_ALERT = """
    SELECT count(*) AS cnt
    FROM agent_alerts
    WHERE business_id = %(business_id)s
      AND disruption_id = %(disruption_id)s
      AND created_at > now() - make_interval(hours => %(hours)s)
"""

# name -> (sql, example params builder is in scripts/benchmark_db.py)
BENCHMARK_QUERIES = {
    "recent_events": SQL_RECENT_EVENTS,
    "business_suppliers": SQL_BUSINESS_SUPPLIERS,
    "pending_orders": SQL_PENDING_ORDERS,
    "alternative_suppliers": SQL_ALTERNATIVE_SUPPLIERS,
    "shipments_at_risk": SQL_SHIPMENTS_AT_RISK,
    "recent_weather": SQL_RECENT_WEATHER,
    "tariffs": SQL_TARIFFS,
    "completed_orders_many": SQL_COMPLETED_ORDERS_MANY,
    "reviews_many": SQL_REVIEWS_MANY,
    "timetable_join": SQL_TIMETABLE,
    "alerts_page": SQL_ALERTS_PAGE,
    "alerts_all": SQL_ALERTS_ALL,
    "suppliers_overview": SQL_SUPPLIERS_OVERVIEW,
    "duplicate_alert": SQL_DUPLICATE_ALERT,
    "calibration_records": SQL_CALIBRATION_RECORDS,
}


# ── Reads ─────────────────────────────────────────────────────────────────────

def query_recent_events(hours: int = 24) -> list[dict]:
    return run_query(SQL_RECENT_EVENTS, {"hours": hours})


def query_business_suppliers(business_id: str) -> list[dict]:
    return run_query(SQL_BUSINESS_SUPPLIERS, {"business_id": business_id})


def query_pending_orders(business_id: str) -> list[dict]:
    """Pending client orders (demand side) for a business."""
    return run_query(SQL_PENDING_ORDERS, {"business_id": business_id})


def query_alternative_suppliers(product_category: str, exclude_country: str) -> list[dict]:
    return run_query(SQL_ALTERNATIVE_SUPPLIERS,
                     {"product_category": product_category, "exclude_country": exclude_country})


def query_port_status(port_name: str) -> list[dict]:
    return run_query(SQL_PORT_STATUS, {"pattern": f"%{port_name.lower()}%"})


def query_calibration_with_recency(event_type: str, region: str, days_lookback: int = 180) -> dict:
    """
    Fetch calibration records for similar events and apply exponential decay
    weighting (half-life 180 days).
    Returns: weighted_baseline_severity, confidence_score, record_count
    """
    records = run_query(SQL_CALIBRATION_RECORDS,
                        {"event_type": event_type, "region": region, "days_lookback": days_lookback})

    if not records:
        return {
            "weighted_baseline_severity": 5.0,  # neutral default
            "confidence_score": 0.0,
            "record_count": 0,
            "days_weighted_avg": 0,
        }

    total_weight = 0.0
    weighted_severity = 0.0
    weighted_days = 0.0
    accuracy_scores = []

    for record in records:
        days_ago = record.get("days_ago", 0)
        weight = math.exp(-0.693 * days_ago / 180)
        severity = record.get("severity_scored", 5.0)
        weighted_severity += severity * weight
        weighted_days += days_ago * weight
        total_weight += weight
        accuracy_scores.append({
            "hallucination": record.get("hallucination_score") if record.get("hallucination_score") is not None else 0.1,
            "relevance": record.get("relevance_score") if record.get("relevance_score") is not None else 0.85,
            "helpfulness": record.get("helpfulness_score") if record.get("helpfulness_score") is not None else 0.80,
            "reasoning": record.get("reasoning_score") if record.get("reasoning_score") is not None else 0.80,
        })

    baseline_severity = weighted_severity / total_weight if total_weight > 0 else 5.0
    weighted_days_avg = weighted_days / total_weight if total_weight > 0 else 0

    n = len(accuracy_scores)
    avg_accuracy = (
        (1 - sum(s["hallucination"] for s in accuracy_scores) / n) * 0.3 +
        sum(s["relevance"] for s in accuracy_scores) / n * 0.3 +
        sum(s["helpfulness"] for s in accuracy_scores) / n * 0.2 +
        sum(s["reasoning"] for s in accuracy_scores) / n * 0.2
    )
    confidence_score = min(0.95, (len(records) / 10) * avg_accuracy)

    return {
        "weighted_baseline_severity": round(baseline_severity, 2),
        "confidence_score": round(confidence_score, 2),
        "record_count": len(records),
        "days_weighted_avg": round(weighted_days_avg, 1),
    }


def query_shipments_at_risk(business_id: str, supplier_ids: list[str], window_days: int = 30) -> list[dict]:
    """Inbound shipments from affected suppliers arriving within window_days."""
    if not supplier_ids:
        return []
    return run_query(SQL_SHIPMENTS_AT_RISK,
                     {"business_id": business_id, "supplier_ids": list(supplier_ids), "window_days": window_days})


def query_business_suppliers_by_country(business_id: str, country: str) -> list[dict]:
    return run_query(SQL_SUPPLIERS_BY_COUNTRY, {"business_id": business_id, "country": country})


def query_weather_alerts_by_region(region: str, hours_back: int = 48) -> list[dict]:
    return run_query(SQL_WEATHER_BY_REGION, {"pattern": f"%{region.lower()}%", "hours_back": hours_back})


def query_recent_weather_alerts(hours_back: int = 48) -> list[dict]:
    """ALL active weather alerts in the last N hours (no region filter)."""
    return run_query(SQL_RECENT_WEATHER, {"hours_back": hours_back})


def query_tariff_updates(days_back: int = 30) -> list[dict]:
    """Tariff changes effective in the last N days (or later)."""
    return run_query(SQL_TARIFFS, {"days_back": days_back})


def query_inventory(business_id: str) -> list[dict]:
    return run_query(SQL_INVENTORY, {"business_id": business_id})


def query_completed_orders_by_supplier(supplier_id: str) -> list[dict]:
    return query_completed_orders_by_suppliers([supplier_id]).get(supplier_id, [])


def query_supplier_reviews(supplier_id: str) -> list[dict]:
    return query_supplier_reviews_by_suppliers([supplier_id]).get(supplier_id, [])


def query_completed_orders_by_suppliers(supplier_ids: list) -> dict:
    """Batch-fetch completed orders for many suppliers in one query (no N+1)."""
    if not supplier_ids:
        return {}
    rows = run_query(SQL_COMPLETED_ORDERS_MANY, {"supplier_ids": list(supplier_ids)})
    grouped: dict = {sid: [] for sid in supplier_ids}
    for r in rows:
        grouped.setdefault(r["supplier_id"], []).append(r)
    return grouped


def query_supplier_reviews_by_suppliers(supplier_ids: list) -> dict:
    """Batch-fetch reviews for many suppliers in one query."""
    if not supplier_ids:
        return {}
    rows = run_query(SQL_REVIEWS_MANY, {"supplier_ids": list(supplier_ids)})
    grouped: dict = {sid: [] for sid in supplier_ids}
    for r in rows:
        grouped.setdefault(r["supplier_id"], []).append(r)
    return grouped


def query_supplier_timetable(business_id: str) -> list[dict]:
    """Active inbound shipments for a business."""
    return run_query(SQL_TIMETABLE, {"business_id": business_id})


def query_alerts_page(business_id: str, limit: int, offset: int) -> list[dict]:
    return run_query(SQL_ALERTS_PAGE, {"business_id": business_id, "limit": limit, "offset": offset})


def query_all_alerts(limit: int) -> list[dict]:
    return run_query(SQL_ALERTS_ALL, {"limit": limit})


def query_suppliers_overview(business_id: str) -> list[dict]:
    return run_query(SQL_SUPPLIERS_OVERVIEW, {"business_id": business_id})


def query_table_last_updated(table_name: str, schema: Optional[str] = None,
                             column: str = "updated_at") -> Optional[datetime]:
    """Newest value of a timestamp column (Postgres has no table-modified metadata).

    Our own tables use `updated_at`; Fivetran tables use `_fivetran_synced` in their own schema.
    Identifiers come from code (freshness_config), never from users, and are quoted.
    """
    from src.ingestion.db import quote_ident
    target = f"{quote_ident(schema)}.{quote_ident(table_name)}" if schema else quote_ident(table_name)
    import psycopg.errors
    try:
        rows = run_query(f"SELECT max({quote_ident(column)}) AS last_updated FROM {target}")
    except psycopg.errors.UndefinedTable:  # connector has not completed its first sync yet
        return None
    return rows[0]["last_updated"] if rows else None


SQL_RISK_ALERTS = """
    SELECT alert_id, alert_type, level, signal_kind, source, event_type, title, status, exposure_usd, expected_loss_usd,
           confidence_band, confidence_score, stockout_risk, lead_time_days, act_by, action, judge_source, last_seen
    FROM alerts
    WHERE business_id = %(business_id)s
      AND (%(level)s::text IS NULL OR level = %(level)s)
      AND (%(status)s::text IS NULL OR status = %(status)s)
    ORDER BY CASE level WHEN 'notify' THEN 0 WHEN 'watch' THEN 1 ELSE 2 END, expected_loss_usd DESC, last_seen DESC
    LIMIT %(limit)s OFFSET %(offset)s
"""


def query_risk_alerts(business_id: str, level: Optional[str], status: Optional[str], limit: int, offset: int) -> list[dict]:
    """Risk alerts (the `alerts` table written by src/risk/pipeline.py), Notify first, then by expected loss."""
    return run_query(SQL_RISK_ALERTS, {"business_id": business_id, "level": level, "status": status,
                                       "limit": limit, "offset": offset})


def query_notifications(business_id: str, limit: int, offset: int) -> list[dict]:
    """Every notification decision for the business, newest first."""
    return run_query("SELECT n.*, a.status AS alert_status FROM alert_notifications n LEFT JOIN alerts a USING (alert_id) "
                     "WHERE n.business_id = %(b)s ORDER BY n.notified_at DESC, n.id DESC LIMIT %(limit)s OFFSET %(offset)s",
                     {"b": business_id, "limit": limit, "offset": offset})


def query_risk_alert(alert_id: str) -> Optional[dict]:
    rows = run_query("SELECT * FROM alerts WHERE alert_id = %(id)s", {"id": alert_id})
    return rows[0] if rows else None


def acknowledge_risk_alert(alert_id: str) -> bool:
    return execute("UPDATE alerts SET status = 'acknowledged', updated_at = now() WHERE alert_id = %(id)s", {"id": alert_id}) > 0


# ── Writes ────────────────────────────────────────────────────────────────────

def save_alert(alert: dict) -> None:
    """Validate alert shape, then insert into agent_alerts."""
    try:
        record = AlertRecord(
            id=alert.get("id", ""),
            business_id=alert.get("business_id", ""),
            created_at=alert.get("created_at", ""),
            disruption_id=alert.get("disruption_id"),
            severity_score=alert.get("severity_score"),
            exposure_usd=alert.get("exposure_usd"),
            actions_json=alert.get("actions_json"),
            status=alert.get("status", "active"),
        )
    except (ValueError, TypeError) as e:
        raise ValueError(f"save_alert: invalid alert data — {e}") from e

    row = {k: v for k, v in record.__dict__.items() if v is not None}
    insert_rows("agent_alerts", [row])


def save_calibration_approval(business_id: str, supplier_name: str,
                              approved: bool, rejection_reason: str = None) -> None:
    """Write an owner approval decision to agent_calibration."""
    now = datetime.now(timezone.utc)
    insert_rows("agent_calibration", [{
        "id": f"approval-{now.strftime('%Y%m%d%H%M%S%f')}",
        "event_type": "owner_approval",
        "region": business_id,
        "supplier_recommended": supplier_name,
        "owner_approved": approved,
        "rejection_reason": rejection_reason or "",
        "calibration_applied": False,
        "created_at": now,
    }])


def update_calibration_outcomes() -> None:
    """
    Stage 3: for agent_calibration records that are 30+ days old, owner-approved
    and missing actual outcomes, look up completed_orders for the recommended
    supplier and write back actual delay + accuracy scores.
    """
    pending = run_query("""
        SELECT id, supplier_recommended, created_at, delay_days_predicted
        FROM agent_calibration
        WHERE owner_approved = TRUE
          AND actual_delay_days IS NULL
          AND created_at <= now() - interval '30 days'
    """)

    if not pending:
        print("[CALIBRATION] No records ready for outcome update.")
        return

    for record in pending:
        rec_id = record["id"]
        supplier_name = record.get("supplier_recommended", "")
        alert_date = record["created_at"].date() if record.get("created_at") else None
        predicted_delay = int(record.get("delay_days_predicted") or 0)

        deliveries = run_query("""
            SELECT delay_days
            FROM completed_orders
            WHERE supplier_id IN (
                SELECT id FROM business_suppliers WHERE supplier_name = %(supplier_name)s
            )
            AND ordered_date >= %(alert_date)s
            LIMIT 5
        """, {"supplier_name": supplier_name, "alert_date": alert_date})

        if not deliveries:
            continue

        actual_delays = [d.get("delay_days") or 0 for d in deliveries]
        avg_actual_delay = round(sum(actual_delays) / len(actual_delays), 1)
        delivered = all(d.get("delay_days") is not None for d in deliveries)

        delay_error = abs(avg_actual_delay - predicted_delay)
        hallucination = round(min(delay_error / max(predicted_delay, 1), 1.0), 3)
        reasoning = round(max(0.0, 1.0 - hallucination), 3)

        execute("""
            UPDATE agent_calibration
            SET actual_delay_days   = %(actual_delay)s,
                supplier_delivered  = %(delivered)s,
                hallucination_score = %(hallucination)s,
                reasoning_score     = %(reasoning)s,
                relevance_score     = 0.85,
                helpfulness_score   = 0.85,
                calibration_applied = TRUE
            WHERE id = %(rec_id)s
        """, {"actual_delay": int(avg_actual_delay), "delivered": delivered,
              "hallucination": hallucination, "reasoning": reasoning, "rec_id": rec_id})
        print(f"[CALIBRATION] Updated record {rec_id}: actual_delay={avg_actual_delay}d, delivered={delivered}")


def acknowledge_alert(alert_id: str) -> None:
    execute("UPDATE agent_alerts SET status = 'acknowledged' WHERE id = %(alert_id)s",
            {"alert_id": alert_id})


def save_phoenix_trace_summary(row: dict) -> None:
    """Write one cycle trace summary row to phoenix_traces."""
    insert_rows("phoenix_traces", [row])


def query_recent_cycle_performance(business_id: str, limit: int = 10) -> dict:
    """Aggregate metrics for the last N agent cycles from phoenix_traces."""
    rows = run_query("""
        SELECT output_json::jsonb ->> 'success'      AS success,
               (output_json::jsonb ->> 'severity_score')::float AS severity_score,
               output_json::jsonb ->> 'alert_fired'  AS alert_fired,
               latency_ms, created_at
        FROM phoenix_traces
        WHERE span_id = %(span_id)s
        ORDER BY created_at DESC
        LIMIT %(lim)s
    """, {"span_id": f"{business_id}-cycle", "lim": limit})
    if not rows:
        return {"success_rate": None, "avg_latency_ms": None, "avg_severity_score": None,
                "alert_rate": None, "cycle_count": 0}
    truthy = lambda v: str(v).lower() == "true"
    successes = [r for r in rows if truthy(r.get("success"))]
    alerts = [r for r in rows if truthy(r.get("alert_fired"))]
    latencies = [r["latency_ms"] for r in rows if r.get("latency_ms") is not None]
    scores = [r["severity_score"] for r in rows if r.get("severity_score") is not None]
    n = len(rows)
    return {
        "success_rate": round(len(successes) / n, 3),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
        "avg_severity_score": round(sum(scores) / len(scores), 3) if scores else None,
        "alert_rate": round(len(alerts) / n, 3),
        "cycle_count": n,
    }


def query_severity_drift(business_id: str, lookback_days: int = 30) -> dict:
    """Recent predicted severity vs historical weighted baseline in agent_calibration."""
    rows = run_query("""
        SELECT avg(severity_scored)     AS avg_predicted,
               avg(weighted_baseline)   AS avg_baseline,
               avg(hallucination_score) AS avg_hallucination,
               avg(reasoning_score)     AS avg_reasoning,
               count(*)                 AS record_count
        FROM agent_calibration
        WHERE region = %(business_id)s
          AND created_at >= now() - make_interval(days => %(days)s)
          AND severity_scored IS NOT NULL
          AND weighted_baseline IS NOT NULL
    """, {"business_id": business_id, "days": lookback_days})
    if not rows or not rows[0].get("record_count"):
        return {"avg_predicted_severity": None, "avg_baseline_severity": None,
                "drift": None, "avg_accuracy": None, "record_count": 0}
    r = rows[0]
    predicted = float(r.get("avg_predicted") or 0.0)
    baseline = float(r.get("avg_baseline") or 0.0)
    hall = float(r.get("avg_hallucination") or 0.0)
    reas = float(r.get("avg_reasoning") or 0.0)
    return {
        "avg_predicted_severity": round(predicted, 3),
        "avg_baseline_severity": round(baseline, 3),
        "drift": round(predicted - baseline, 3),
        "avg_accuracy": round((1 - hall) * 0.5 + reas * 0.5, 3),
        "record_count": int(r.get("record_count") or 0),
    }


def check_duplicate_alert(business_id: str, disruption_id: str, hours: int = 24) -> bool:
    """True if an alert for this disruption was already fired within `hours`."""
    rows = run_query(SQL_DUPLICATE_ALERT,
                     {"business_id": business_id, "disruption_id": disruption_id, "hours": hours})
    return bool(rows and rows[0].get("cnt", 0) > 0)
