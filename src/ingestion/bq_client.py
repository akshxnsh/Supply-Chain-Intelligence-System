from google.cloud import bigquery
from google.oauth2 import service_account
from dataclasses import dataclass
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "akshxnsh-supplychain")
DATASET = "supply_chain"

KEY_FILE = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "gcp-key.json"))
)

if os.path.exists(KEY_FILE):
    credentials = service_account.Credentials.from_service_account_file(KEY_FILE)
    client = bigquery.Client(project=PROJECT_ID, credentials=credentials)
else:
    client = bigquery.Client(project=PROJECT_ID)

@dataclass
class AlertRecord:
    """Validated shape for agent_alerts BigQuery rows. Matches the table schema in init_tables.py."""
    id: str
    business_id: str
    created_at: str          # ISO 8601 string; BQ autodetects as TIMESTAMP
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

def run_query(sql: str) -> list[dict]:
    rows = client.query(sql).result()
    return [dict(row) for row in rows]

def run_query_safe(sql: str, params: list) -> list[dict]:
    """Execute a parameterized BigQuery query to prevent SQL injection."""
    job_config = bigquery.QueryJobConfig(query_parameters=params)
    rows = client.query(sql, job_config=job_config).result()
    return [dict(row) for row in rows]

def query_recent_events(hours: int = 24) -> list[dict]:
    sql = f"""
        SELECT id, source, headline, location_name, lat, lon, severity_raw,
               CAST(published_at AS STRING) as published_at
        FROM `{PROJECT_ID}.{DATASET}.disruption_events`
        WHERE published_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
        ORDER BY published_at DESC
        LIMIT 50
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("hours", "INT64", hours),
    ])

def query_business_suppliers(business_id: str) -> list[dict]:
    sql = f"""
        SELECT id, supplier_name, country, product_category, annual_spend_usd
        FROM `{PROJECT_ID}.{DATASET}.business_suppliers`
        WHERE business_id = @business_id
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
    ])

def query_pending_orders(business_id: str) -> list[dict]:
    """Return pending client orders (demand side) for a business."""
    sql = f"""
        SELECT id, client_id, product_category, quantity, order_value_usd,
               CAST(required_by_date AS STRING) as required_by_date, status
        FROM `{PROJECT_ID}.{DATASET}.pending_orders`
        WHERE business_id = @business_id
          AND status = 'pending'
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
    ])

def query_alternative_suppliers(product_category: str,
                                  exclude_country: str) -> list[dict]:
    sql = f"""
        SELECT id, name, country, product_category,
               moq, lead_time_days, unit_price_usd, reliability_score
        FROM `{PROJECT_ID}.{DATASET}.alternative_suppliers`
        WHERE product_category = @product_category
        AND country != @exclude_country
        ORDER BY reliability_score DESC
        LIMIT 5
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("product_category", "STRING", product_category),
        bigquery.ScalarQueryParameter("exclude_country",  "STRING", exclude_country),
    ])

def query_port_status(port_name: str) -> list[dict]:
    sql = f"""
        SELECT port_id, port_name, congestion_score,
               vessel_delay_hours, strike_flag
        FROM `{PROJECT_ID}.{DATASET}.port_activity`
        WHERE LOWER(port_name) LIKE CONCAT('%', LOWER(@port_name), '%')
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("port_name", "STRING", port_name),
    ])

def query_calibration_with_recency(event_type: str, region: str, days_lookback: int = 180) -> dict:
    """
    Fetch calibration records for similar events.
    Apply exponential decay weighting: EXP(-0.693 * days_ago / 180)
    Returns: weighted_baseline_severity, confidence_score, record_count
    """
    sql = f"""
        SELECT 
            severity_scored,
            actual_delay_days,
            hallucination_score,
            relevance_score,
            helpfulness_score,
            reasoning_score,
            TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), TIMESTAMP(created_at), DAY) as days_ago
        FROM `{PROJECT_ID}.{DATASET}.agent_calibration`
        WHERE event_type = @event_type
        AND region = @region
        AND severity_scored IS NOT NULL
        AND actual_delay_days IS NOT NULL
        AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), TIMESTAMP(created_at), DAY) <= @days_lookback
        ORDER BY created_at DESC
    """
    records = run_query_safe(sql, [
        bigquery.ScalarQueryParameter("event_type",    "STRING", event_type),
        bigquery.ScalarQueryParameter("region",        "STRING", region),
        bigquery.ScalarQueryParameter("days_lookback", "INT64",  days_lookback),
    ])
    
    if not records:
        return {
            "weighted_baseline_severity": 5.0,  # neutral default
            "confidence_score": 0.0,
            "record_count": 0,
            "days_weighted_avg": 0
        }
    
    # Apply recency weighting: EXP(-0.693 * days_ago / 180) → half-life = 180 days
    import math
    total_weight = 0
    weighted_severity = 0
    weighted_days = 0
    accuracy_scores = []
    
    for record in records:
        days_ago = record.get("days_ago", 0)
        weight = math.exp(-0.693 * days_ago / 180)  # Half-life 180 days
        
        severity = record.get("severity_scored", 5.0)
        weighted_severity += severity * weight
        weighted_days += days_ago * weight
        total_weight += weight
        
        # Average accuracy metrics
        accuracy_scores.append({
            "hallucination": record.get("hallucination_score", 0.1),
            "relevance": record.get("relevance_score", 0.85),
            "helpfulness": record.get("helpfulness_score", 0.80),
            "reasoning": record.get("reasoning_score", 0.80),
        })
    
    baseline_severity = weighted_severity / total_weight if total_weight > 0 else 5.0
    weighted_days_avg = weighted_days / total_weight if total_weight > 0 else 0
    
    # Confidence = function of record count + average accuracy
    avg_accuracy = (
        (1 - sum(s["hallucination"] for s in accuracy_scores) / len(accuracy_scores)) * 0.3 +
        sum(s["relevance"] for s in accuracy_scores) / len(accuracy_scores) * 0.3 +
        sum(s["helpfulness"] for s in accuracy_scores) / len(accuracy_scores) * 0.2 +
        sum(s["reasoning"] for s in accuracy_scores) / len(accuracy_scores) * 0.2
    )
    confidence_score = min(0.95, (len(records) / 10) * avg_accuracy)  # Scales with record count
    
    return {
        "weighted_baseline_severity": round(baseline_severity, 2),
        "confidence_score": round(confidence_score, 2),
        "record_count": len(records),
        "days_weighted_avg": round(weighted_days_avg, 1)
    }

def query_shipments_at_risk(
    business_id: str,
    supplier_ids: list[str],
    window_days: int = 30,
) -> list[dict]:
    """Return inbound shipments from affected suppliers arriving within window_days."""
    if not supplier_ids:
        return []
    sql = f"""
        SELECT id, supplier_id, product_category, quantity, shipment_value_usd,
               CAST(expected_arrival_date AS STRING) as expected_arrival_date,
               origin_port, destination_port, status
        FROM `{PROJECT_ID}.{DATASET}.shipment_timetable`
        WHERE business_id = @business_id
          AND supplier_id IN UNNEST(@supplier_ids)
          AND status = 'in_transit'
          AND expected_arrival_date <= DATE_ADD(CURRENT_DATE(), INTERVAL @window_days DAY)
        ORDER BY expected_arrival_date ASC
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("business_id",  "STRING", business_id),
        bigquery.ArrayQueryParameter("supplier_ids",  "STRING", supplier_ids),
        bigquery.ScalarQueryParameter("window_days",  "INT64",  window_days),
    ])


def query_business_suppliers_by_country(business_id: str, country: str) -> list[dict]:
    """Get all suppliers from business operating in specific country."""
    sql = f"""
        SELECT id, supplier_name, product_category, annual_spend_usd
        FROM `{PROJECT_ID}.{DATASET}.business_suppliers`
        WHERE business_id = @business_id
        AND LOWER(country) = LOWER(@country)
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
        bigquery.ScalarQueryParameter("country",     "STRING", country),
    ])

def query_weather_alerts_by_region(region: str, hours_back: int = 48) -> list[dict]:
    """Get active weather alerts for region (last N hours)."""
    sql = f"""
        SELECT id, region, alert_type, severity, affected_ports,
               CAST(start_time AS STRING) as start_time,
               CAST(end_time AS STRING) as end_time
        FROM `{PROJECT_ID}.{DATASET}.weather_alerts`
        WHERE LOWER(region) LIKE CONCAT('%', LOWER(@region), '%')
        AND start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours_back HOUR)
        ORDER BY severity DESC
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("region",    "STRING", region),
        bigquery.ScalarQueryParameter("hours_back", "INT64", hours_back),
    ])

def query_recent_weather_alerts(hours_back: int = 48) -> list[dict]:
    """Get ALL active weather alerts (last N hours) - no region filter."""
    sql = f"""
        SELECT id, region, alert_type, severity, affected_ports,
               CAST(start_time AS STRING) as start_time,
               CAST(end_time AS STRING) as end_time
        FROM `{PROJECT_ID}.{DATASET}.weather_alerts`
        WHERE start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours_back HOUR)
        ORDER BY severity DESC, start_time DESC
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("hours_back", "INT64", hours_back),
    ])

def query_tariff_updates(days_back: int = 30) -> list[dict]:
    """
    Get recent tariff updates effective within last N days.
    Returns tariff rate changes that affect supplier costs.
    """
    sql = f"""
        SELECT id, country_of_origin, product_category, tariff_rate_percentage,
               CAST(effective_date AS STRING) as effective_date, description
        FROM `{PROJECT_ID}.{DATASET}.tariff_updates`
        WHERE effective_date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days_back DAY)
        ORDER BY effective_date DESC
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("days_back", "INT64", days_back),
    ])

def query_inventory(business_id: str) -> list[dict]:
    """Get current inventory levels for a business."""
    sql = f"""
        SELECT product_category, inventory_value_usd
        FROM `{PROJECT_ID}.{DATASET}.inventory`
        WHERE business_id = @business_id
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
    ])

def query_completed_orders_by_supplier(supplier_id: str) -> list[dict]:
    """Get all completed orders for a supplier to compute reliability metrics."""
    sql = f"""
        SELECT supplier_id, delay_days, defective_items_count, status,
               CAST(expected_delivery_date AS STRING) AS expected_delivery_date,
               CAST(actual_delivery_date AS STRING) AS actual_delivery_date
        FROM `{PROJECT_ID}.{DATASET}.completed_orders`
        WHERE supplier_id = @supplier_id
          AND status = 'delivered'
        ORDER BY expected_delivery_date DESC
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("supplier_id", "STRING", supplier_id),
    ])

def query_supplier_reviews(supplier_id: str) -> list[dict]:
    """Get all reviews for a supplier."""
    sql = f"""
        SELECT supplier_id, rating, review_text,
               CAST(review_date AS STRING) AS review_date
        FROM `{PROJECT_ID}.{DATASET}.supplier_reviews`
        WHERE supplier_id = @supplier_id
        ORDER BY review_date DESC
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("supplier_id", "STRING", supplier_id),
    ])

def query_completed_orders_by_suppliers(supplier_ids: list) -> dict:
    """Batch-fetch completed orders for many suppliers in a single query.

    Returns a dict mapping supplier_id -> list of completed-order rows, so callers
    can avoid an N+1 query loop. Keys are guaranteed to exist for every requested id.
    """
    if not supplier_ids:
        return {}
    sql = f"""
        SELECT supplier_id, delay_days, defective_items_count, status,
               CAST(expected_delivery_date AS STRING) AS expected_delivery_date,
               CAST(actual_delivery_date AS STRING) AS actual_delivery_date
        FROM `{PROJECT_ID}.{DATASET}.completed_orders`
        WHERE supplier_id IN UNNEST(@supplier_ids)
          AND status = 'delivered'
        ORDER BY expected_delivery_date DESC
    """
    rows = run_query_safe(sql, [
        bigquery.ArrayQueryParameter("supplier_ids", "STRING", supplier_ids),
    ])
    grouped: dict = {sid: [] for sid in supplier_ids}
    for r in rows:
        grouped.setdefault(r["supplier_id"], []).append(r)
    return grouped

def query_supplier_reviews_by_suppliers(supplier_ids: list) -> dict:
    """Batch-fetch reviews for many suppliers in a single query.

    Returns a dict mapping supplier_id -> list of review rows.
    """
    if not supplier_ids:
        return {}
    sql = f"""
        SELECT supplier_id, rating, review_text,
               CAST(review_date AS STRING) AS review_date
        FROM `{PROJECT_ID}.{DATASET}.supplier_reviews`
        WHERE supplier_id IN UNNEST(@supplier_ids)
        ORDER BY review_date DESC
    """
    rows = run_query_safe(sql, [
        bigquery.ArrayQueryParameter("supplier_ids", "STRING", supplier_ids),
    ])
    grouped: dict = {sid: [] for sid in supplier_ids}
    for r in rows:
        grouped.setdefault(r["supplier_id"], []).append(r)
    return grouped

def query_supplier_timetable(business_id: str) -> list[dict]:
    """Return active inbound shipments for a business from the shipment_timetable."""
    sql = f"""
        SELECT
            st.id AS shipment_id,
            st.supplier_id,
            bs.supplier_name,
            bs.country,
            st.product_category,
            st.shipment_value_usd,
            st.quantity,
            st.origin_port,
            st.destination_port,
            CAST(st.dispatched_date AS STRING) AS dispatched_date,
            CAST(st.expected_arrival_date AS STRING) AS eta_date,
            CAST(st.dispatched_date AS STRING) AS dispatch_timestamp,
            CAST(st.expected_arrival_date AS STRING) AS estimated_arrival,
            st.status
        FROM `{PROJECT_ID}.{DATASET}.shipment_timetable` st
        JOIN `{PROJECT_ID}.{DATASET}.business_suppliers` bs
          ON st.supplier_id = bs.id
        WHERE st.business_id = @business_id
          AND st.status = 'in_transit'
        ORDER BY st.expected_arrival_date ASC
    """
    return run_query_safe(sql, [
        bigquery.ScalarQueryParameter("business_id", "STRING", business_id),
    ])

def save_alert(alert: dict):
    """Validate alert shape then save to BigQuery via CSV load."""
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

    table_ref = f"{PROJECT_ID}.{DATASET}.agent_alerts"
    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"save_alert: BigQuery streaming insert failed — {errors}")

def save_calibration_approval(business_id: str, supplier_name: str,
                               approved: bool, rejection_reason: str = None):
    """Write an owner approval decision to the agent_calibration table."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    row = {
        "id": f"approval-{now.strftime('%Y%m%d%H%M%S')}",
        "event_type": "owner_approval",
        "region": business_id,
        "supplier_recommended": supplier_name,
        "owner_approved": approved,
        "rejection_reason": rejection_reason or "",
        "calibration_applied": False,
        "created_at": now.isoformat(),
    }
    table_ref = f"{PROJECT_ID}.{DATASET}.agent_calibration"
    errors = client.insert_rows_json(table_ref, [row])
    if errors:
        raise RuntimeError(f"save_calibration_approval: BigQuery streaming insert failed — {errors}")

def update_calibration_outcomes():
    """
    Stage 3: For agent_calibration records that are 30+ days old, owner-approved,
    and missing actual outcomes, look up completed_orders for the recommended supplier
    and write back actual_delay_days, supplier_delivered, and accuracy scores via DML UPDATE.
    """
    pending_sql = f"""
        SELECT id, supplier_recommended, created_at, delay_days_predicted
        FROM `{PROJECT_ID}.{DATASET}.agent_calibration`
        WHERE owner_approved = TRUE
          AND actual_delay_days IS NULL
          AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), created_at, DAY) >= 30
    """
    pending = run_query(pending_sql)

    if not pending:
        print("[CALIBRATION] No records ready for outcome update.")
        return

    for record in pending:
        rec_id = record["id"]
        supplier_name = record.get("supplier_recommended", "")
        alert_date = str(record.get("created_at", ""))[:10]
        predicted_delay = int(record.get("delay_days_predicted") or 0)

        orders_sql = f"""
            SELECT delay_days
            FROM `{PROJECT_ID}.{DATASET}.completed_orders`
            WHERE supplier_id IN (
                SELECT id FROM `{PROJECT_ID}.{DATASET}.business_suppliers`
                WHERE supplier_name = @supplier_name
            )
            AND ordered_date >= DATE(@alert_date)
            LIMIT 5
        """
        deliveries = run_query_safe(orders_sql, [
            bigquery.ScalarQueryParameter("supplier_name", "STRING", supplier_name),
            bigquery.ScalarQueryParameter("alert_date",    "STRING", alert_date),
        ])

        if not deliveries:
            continue

        actual_delays = [d.get("delay_days") or 0 for d in deliveries]
        avg_actual_delay = round(sum(actual_delays) / len(actual_delays), 1)
        delivered = all(d.get("delay_days") is not None for d in deliveries)

        delay_error = abs(avg_actual_delay - predicted_delay)
        hallucination = round(min(delay_error / max(predicted_delay, 1), 1.0), 3)
        reasoning = round(max(0.0, 1.0 - hallucination), 3)

        update_sql = f"""
            UPDATE `{PROJECT_ID}.{DATASET}.agent_calibration`
            SET
                actual_delay_days   = @actual_delay,
                supplier_delivered  = @delivered,
                hallucination_score = @hallucination,
                reasoning_score     = @reasoning,
                relevance_score     = 0.85,
                helpfulness_score   = 0.85,
                calibration_applied = TRUE
            WHERE id = @rec_id
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("actual_delay",  "INT64",   int(avg_actual_delay)),
            bigquery.ScalarQueryParameter("delivered",     "BOOL",    delivered),
            bigquery.ScalarQueryParameter("hallucination", "FLOAT64", hallucination),
            bigquery.ScalarQueryParameter("reasoning",     "FLOAT64", reasoning),
            bigquery.ScalarQueryParameter("rec_id",        "STRING",  rec_id),
        ])
        client.query(update_sql, job_config=job_config).result()
        print(f"[CALIBRATION] Updated record {rec_id}: actual_delay={avg_actual_delay}d, delivered={delivered}")

def acknowledge_alert(alert_id: str):
    """Set agent_alerts.status = 'acknowledged' for the given alert ID."""
    sql = f"""
        UPDATE `{PROJECT_ID}.{DATASET}.agent_alerts`
        SET status = 'acknowledged'
        WHERE id = @alert_id
    """
    job_config = bigquery.QueryJobConfig(query_parameters=[
        bigquery.ScalarQueryParameter("alert_id", "STRING", alert_id),
    ])
    client.query(sql, job_config=job_config).result()

def check_duplicate_alert(business_id: str, disruption_id: str, hours: int = 24) -> bool:
    """Return True if an alert for this disruption was already fired within `hours`."""
    rows = run_query_safe(f"""
        SELECT COUNT(*) as cnt
        FROM `{PROJECT_ID}.{DATASET}.agent_alerts`
        WHERE business_id = @business_id
          AND disruption_id = @disruption_id
          AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), created_at, HOUR) < @hours
    """, [
        bigquery.ScalarQueryParameter("business_id",   "STRING", business_id),
        bigquery.ScalarQueryParameter("disruption_id", "STRING", disruption_id),
        bigquery.ScalarQueryParameter("hours",         "INT64",  hours),
    ])
    return bool(rows and rows[0].get("cnt", 0) > 0)
