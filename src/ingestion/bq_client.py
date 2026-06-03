from google.cloud import bigquery
from google.oauth2 import service_account
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = "akshxnsh-supplychain"
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

def run_query(sql: str) -> list[dict]:
    rows = client.query(sql).result()
    return [dict(row) for row in rows]

def query_recent_events(hours: int = 24) -> list[dict]:
    since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    sql = f"""
        SELECT id, source, headline, location_name, lat, lon, severity_raw,
               CAST(published_at AS STRING) as published_at
        FROM `{PROJECT_ID}.{DATASET}.disruption_events`
        WHERE published_at >= '{since}'
        ORDER BY published_at DESC
        LIMIT 50
    """
    return run_query(sql)

def query_business_suppliers(business_id: str) -> list[dict]:
    sql = f"""
        SELECT id, supplier_name, country, product_category, annual_spend_usd
        FROM `{PROJECT_ID}.{DATASET}.business_suppliers`
        WHERE business_id = '{business_id}'
    """
    return run_query(sql)

def query_pending_orders(business_id: str) -> list[dict]:
    sql = f"""
        SELECT id, supplier_id, order_value_usd,
               CAST(eta_date AS STRING) as eta_date, status
        FROM `{PROJECT_ID}.{DATASET}.pending_orders`
        WHERE business_id = '{business_id}'
        AND status = 'pending'
    """
    return run_query(sql)

def query_alternative_suppliers(product_category: str,
                                  exclude_country: str) -> list[dict]:
    sql = f"""
        SELECT id, name, country, product_category,
               moq, lead_time_days, unit_price_usd, reliability_score
        FROM `{PROJECT_ID}.{DATASET}.alternative_suppliers`
        WHERE product_category = '{product_category}'
        AND country != '{exclude_country}'
        ORDER BY reliability_score DESC
        LIMIT 5
    """
    return run_query(sql)

def query_port_status(port_name: str) -> list[dict]:
    sql = f"""
        SELECT port_id, port_name, congestion_score,
               vessel_delay_hours, strike_flag
        FROM `{PROJECT_ID}.{DATASET}.port_activity`
        WHERE LOWER(port_name) LIKE LOWER('%{port_name}%')
        LIMIT 1
    """
    return run_query(sql)

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
        WHERE event_type = '{event_type}'
        AND region = '{region}'
        AND severity_scored IS NOT NULL
        AND actual_delay_days IS NOT NULL
        AND TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), TIMESTAMP(created_at), DAY) <= {days_lookback}
        ORDER BY created_at DESC
    """
    records = run_query(sql)
    
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

def query_pending_orders_at_risk(business_id: str, disruption_date: str, window_days: int = 30) -> list[dict]:
    """
    Fetch pending orders with eta_date within window days of disruption.
    Only orders that would be affected by disruption count as at-risk.
    """
    sql = f"""
        SELECT id, supplier_id, order_value_usd,
               CAST(eta_date AS STRING) as eta_date, status
        FROM `{PROJECT_ID}.{DATASET}.pending_orders`
        WHERE business_id = '{business_id}'
        AND status = 'pending'
        AND eta_date >= CAST('{disruption_date}' AS DATE)
        AND eta_date <= DATE_ADD(CAST('{disruption_date}' AS DATE), INTERVAL {window_days} DAY)
        ORDER BY eta_date ASC
    """
    return run_query(sql)

def query_pending_orders_by_supplier(business_id: str, supplier_id: str) -> list[dict]:
    """Get all pending orders from specific supplier."""
    sql = f"""
        SELECT id, order_value_usd,
               CAST(eta_date AS STRING) as eta_date, status
        FROM `{PROJECT_ID}.{DATASET}.pending_orders`
        WHERE business_id = '{business_id}'
        AND supplier_id = '{supplier_id}'
        AND status = 'pending'
        ORDER BY eta_date ASC
    """
    return run_query(sql)

def query_business_suppliers_by_country(business_id: str, country: str) -> list[dict]:
    """Get all suppliers from business operating in specific country."""
    sql = f"""
        SELECT id, supplier_name, product_category, annual_spend_usd
        FROM `{PROJECT_ID}.{DATASET}.business_suppliers`
        WHERE business_id = '{business_id}'
        AND LOWER(country) = LOWER('{country}')
    """
    return run_query(sql)

def query_weather_alerts_by_region(region: str, hours_back: int = 48) -> list[dict]:
    """Get active weather alerts for region (last N hours)."""
    sql = f"""
        SELECT id, region, alert_type, severity, affected_ports,
               CAST(start_time AS STRING) as start_time,
               CAST(end_time AS STRING) as end_time
        FROM `{PROJECT_ID}.{DATASET}.weather_alerts`
        WHERE LOWER(region) LIKE LOWER('%{region}%')
        AND start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours_back} HOUR)
        ORDER BY severity DESC
    """
    return run_query(sql)

def query_recent_weather_alerts(hours_back: int = 48) -> list[dict]:
    """Get ALL active weather alerts (last N hours) - no region filter."""
    sql = f"""
        SELECT id, region, alert_type, severity, affected_ports,
               CAST(start_time AS STRING) as start_time,
               CAST(end_time AS STRING) as end_time
        FROM `{PROJECT_ID}.{DATASET}.weather_alerts`
        WHERE start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours_back} HOUR)
        ORDER BY severity DESC, start_time DESC
    """
    return run_query(sql)

def query_tariff_updates(days_back: int = 30) -> list[dict]:
    """
    Get recent tariff updates effective within last N days.
    Returns tariff rate changes that affect supplier costs.
    """
    sql = f"""
        SELECT id, country_of_origin, product_category, tariff_rate_percentage,
               CAST(effective_date AS STRING) as effective_date, description
        FROM `{PROJECT_ID}.{DATASET}.tariff_updates`
        WHERE effective_date >= DATE_SUB(CURRENT_DATE(), INTERVAL {days_back} DAY)
        ORDER BY effective_date DESC
    """
    return run_query(sql)

def query_inventory(business_id: str) -> list[dict]:
    """Get current inventory levels for a business."""
    sql = f"""
        SELECT product_category, inventory_value_usd
        FROM `{PROJECT_ID}.{DATASET}.inventory`
        WHERE business_id = '{business_id}'
    """
    return run_query(sql)

def query_completed_orders_by_supplier(supplier_id: str) -> list[dict]:
    """Get all completed orders for a supplier to compute reliability metrics."""
    sql = f"""
        SELECT supplier_id, delay_days, defective_items_count, status,
               CAST(expected_delivery_date AS STRING) AS expected_delivery_date,
               CAST(actual_delivery_date AS STRING) AS actual_delivery_date
        FROM `{PROJECT_ID}.{DATASET}.completed_orders`
        WHERE supplier_id = '{supplier_id}'
          AND status = 'delivered'
        ORDER BY expected_delivery_date DESC
    """
    return run_query(sql)

def query_supplier_reviews(supplier_id: str) -> list[dict]:
    """Get all reviews for a supplier."""
    sql = f"""
        SELECT supplier_id, rating, review_text,
               CAST(review_date AS STRING) AS review_date
        FROM `{PROJECT_ID}.{DATASET}.supplier_reviews`
        WHERE supplier_id = '{supplier_id}'
        ORDER BY review_date DESC
    """
    return run_query(sql)

def save_alert(alert: dict):
    """Save agent alert to BigQuery via CSV load."""
    from google.cloud import bigquery
    import csv, tempfile
    table_ref = f"{PROJECT_ID}.{DATASET}.agent_alerts"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv',
                                     delete=False, newline='') as f:
        writer = csv.DictWriter(f, fieldnames=alert.keys())
        writer.writeheader()
        writer.writerow(alert)
        tmp_path = f.name
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        autodetect=True,
    )
    with open(tmp_path, "rb") as f:
        job = client.load_table_from_file(f, table_ref, job_config=job_config)
    job.result()
    import os; os.unlink(tmp_path)