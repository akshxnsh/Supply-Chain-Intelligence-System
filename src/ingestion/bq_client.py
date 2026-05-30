from google.cloud import bigquery
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

PROJECT_ID = "akshxnsh-supplychain"
DATASET = "supply_chain"
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