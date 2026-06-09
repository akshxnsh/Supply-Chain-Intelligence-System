"""
BigQuery Table Initialization Script
Ensures all required tables exist with proper schemas.
Handles all 8+ tables from the Supply Chain Intelligence System.
"""

from google.cloud import bigquery
from google.oauth2 import service_account
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

# ── Table Schemas ─────────────────────────────────────────────────────────────

DISRUPTION_EVENTS_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("source", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("headline", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("location_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("lat", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("lon", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("severity_raw", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("published_at", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("inserted_at", "TIMESTAMP", mode="REQUIRED"),
]

WEATHER_ALERTS_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("region", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("alert_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("severity", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("start_time", "TIMESTAMP", mode="REQUIRED"),
    bigquery.SchemaField("end_time", "TIMESTAMP", mode="NULLABLE"),
    bigquery.SchemaField("affected_ports", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]

ALTERNATIVE_SUPPLIERS_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("country", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("product_category", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("moq", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("lead_time_days", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("unit_price_usd", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("reliability_score", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("geographic_risk_score", "FLOAT", mode="NULLABLE"),
]

BUSINESS_SUPPLIERS_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("business_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("supplier_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("country", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("product_category", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("annual_spend_usd", "FLOAT", mode="NULLABLE"),
]

PENDING_ORDERS_SCHEMA = [
    bigquery.SchemaField("id",               "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("business_id",      "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("client_id",        "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("product_category", "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("quantity",         "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("order_value_usd",  "FLOAT",   mode="REQUIRED"),
    bigquery.SchemaField("required_by_date", "DATE",    mode="REQUIRED"),
    bigquery.SchemaField("status",           "STRING",  mode="REQUIRED"),
]

SHIPMENT_TIMETABLE_SCHEMA = [
    bigquery.SchemaField("id",                    "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("business_id",           "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("supplier_id",           "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("product_category",      "STRING",  mode="REQUIRED"),
    bigquery.SchemaField("quantity",              "INTEGER", mode="REQUIRED"),
    bigquery.SchemaField("shipment_value_usd",    "FLOAT",   mode="REQUIRED"),
    bigquery.SchemaField("origin_port",           "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("destination_port",      "STRING",  mode="NULLABLE"),
    bigquery.SchemaField("dispatched_date",       "DATE",    mode="NULLABLE"),
    bigquery.SchemaField("expected_arrival_date", "DATE",    mode="REQUIRED"),
    bigquery.SchemaField("status",                "STRING",  mode="REQUIRED"),
]

AGENT_ALERTS_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("business_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("disruption_id", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("severity_score", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("exposure_usd", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("actions_json", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("status", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]

AGENT_CALIBRATION_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("event_type", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("region", "STRING", mode="NULLABLE"),
    # Stage 1: Alert fires
    bigquery.SchemaField("severity_scored", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("delay_days_predicted", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("supplier_recommended", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("exposure_calculated", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("owner_approved", "BOOLEAN", mode="NULLABLE"),
    # Stage 2: Owner decision
    bigquery.SchemaField("owner_override", "BOOLEAN", mode="NULLABLE"),
    bigquery.SchemaField("rejection_reason", "STRING", mode="NULLABLE"),
    # Stage 3: Outcome (30 days later)
    bigquery.SchemaField("actual_delay_days", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("supplier_delivered", "BOOLEAN", mode="NULLABLE"),
    # Accuracy metrics
    bigquery.SchemaField("hallucination_score", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("relevance_score", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("helpfulness_score", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("reasoning_score", "FLOAT", mode="NULLABLE"),
    # Calibration application
    bigquery.SchemaField("calibration_applied", "BOOLEAN", mode="NULLABLE"),
    bigquery.SchemaField("weighted_baseline", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]

PHOENIX_TRACES_SCHEMA = [
    bigquery.SchemaField("trace_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("span_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("tool_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("input_json", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("output_json", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("latency_ms", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("token_count", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]

PORT_ACTIVITY_SCHEMA = [
    bigquery.SchemaField("port_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("port_name", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("congestion_score", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("vessel_delay_hours", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("strike_flag", "BOOLEAN", mode="NULLABLE"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
]

TARIFF_UPDATES_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("country_of_origin", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("product_category", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("tariff_rate_percentage", "FLOAT", mode="REQUIRED"),
    bigquery.SchemaField("effective_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("description", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("created_at", "TIMESTAMP", mode="REQUIRED"),
]

INVENTORY_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("business_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("product_category", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("inventory_value_usd", "FLOAT", mode="REQUIRED"),
    bigquery.SchemaField("updated_at", "TIMESTAMP", mode="REQUIRED"),
]

COMPLETED_ORDERS_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("business_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("supplier_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("order_value_usd", "FLOAT", mode="REQUIRED"),
    bigquery.SchemaField("ordered_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("expected_delivery_date", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("actual_delivery_date", "DATE", mode="NULLABLE"),
    bigquery.SchemaField("delay_days", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("defective_items_count", "INTEGER", mode="NULLABLE"),
    bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
]

SUPPLIER_REVIEWS_SCHEMA = [
    bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("supplier_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("business_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("rating", "FLOAT", mode="REQUIRED"),
    bigquery.SchemaField("review_text", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("review_date", "TIMESTAMP", mode="REQUIRED"),
]

# ── Table Definitions ─────────────────────────────────────────────────────────

TABLES = {
    "disruption_events": {
        "schema": DISRUPTION_EVENTS_SCHEMA,
        "description": "Disruption events from Fivetran NewsAPI (auto-syncs every 15 min)",
        "source": "Fivetran NewsAPI connector"
    },
    "weather_alerts": {
        "schema": WEATHER_ALERTS_SCHEMA,
        "description": "Weather alerts from Fivetran OpenWeatherMap (auto-syncs every 60 min)",
        "source": "Fivetran OpenWeatherMap connector"
    },
    "alternative_suppliers": {
        "schema": ALTERNATIVE_SUPPLIERS_SCHEMA,
        "description": "Alternative suppliers database from CSV seed loader",
        "source": "CSV seed loader (supplier_db_seed.json)"
    },
    "business_suppliers": {
        "schema": BUSINESS_SUPPLIERS_SCHEMA,
        "description": "Business supplier relationships from manual seed / QuickBooks",
        "source": "Manual seed / QuickBooks"
    },
    "pending_orders": {
        "schema": PENDING_ORDERS_SCHEMA,
        "description": "Client orders placed with the business (demand side) — from Shopify or manual seed",
        "source": "Manual seed / Shopify"
    },
    "shipment_timetable": {
        "schema": SHIPMENT_TIMETABLE_SCHEMA,
        "description": "Inbound supplier shipments in transit to the business (supply side)",
        "source": "ERP / manual seed"
    },
    "agent_alerts": {
        "schema": AGENT_ALERTS_SCHEMA,
        "description": "Alerts generated by the supply chain agent",
        "source": "Supply Chain Agent (loop.py -> save_alert())"
    },
    "agent_calibration": {
        "schema": AGENT_CALIBRATION_SCHEMA,
        "description": "Self-improvement loop calibration data (NEW)",
        "source": "Self-improvement loop"
    },
    "phoenix_traces": {
        "schema": PHOENIX_TRACES_SCHEMA,
        "description": "Arize Phoenix tracing data for observability",
        "source": "Arize Phoenix local instance"
    },
    "port_activity": {
        "schema": PORT_ACTIVITY_SCHEMA,
        "description": "Port congestion and delay monitoring data",
        "source": "Seed data"
    },
    "tariff_updates": {
        "schema": TARIFF_UPDATES_SCHEMA,
        "description": "Tariff rate changes affecting suppliers by country and product category",
        "source": "Trade regulatory updates (Fivetran or manual seed)"
    },
    "inventory": {
        "schema": INVENTORY_SCHEMA,
        "description": "Current on-hand inventory levels and values by product category",
        "source": "ERP/WMS integration or manual seed"
    },
    "completed_orders": {
        "schema": COMPLETED_ORDERS_SCHEMA,
        "description": "Historical completed orders with actual vs expected delivery dates for reliability scoring",
        "source": "Order management system or manual seed"
    },
    "supplier_reviews": {
        "schema": SUPPLIER_REVIEWS_SCHEMA,
        "description": "Subjective supplier reviews and ratings from past transactions",
        "source": "Business owner manual input or ERP"
    },
}

# ── Table Creation ────────────────────────────────────────────────────────────

def create_table_if_not_exists(table_id: str, schema: list, description: str = "") -> bool:
    """Create a table if it doesn't already exist."""
    table_ref = f"{PROJECT_ID}.{DATASET}.{table_id}"
    
    try:
        client.get_table(table_ref)
        print(f"✅ {table_id} already exists")
        return False
    except Exception:
        table = bigquery.Table(table_ref, schema=schema)
        table.description = description
        client.create_table(table)
        print(f"✨ Created {table_id}")
        return True

def list_all_tables() -> list[str]:
    """List all tables in the dataset."""
    tables = client.list_tables(DATASET)
    return [table.table_id for table in tables]

def verify_all_tables() -> dict:
    """Verify all tables exist and return status."""
    existing = set(list_all_tables())
    expected = set(TABLES.keys())
    
    return {
        "existing": existing,
        "expected": expected,
        "missing": expected - existing,
        "extra": existing - expected,
        "all_present": expected.issubset(existing),
    }

def init_all_tables():
    """Initialize all required tables."""
    print(f"\n🔧 Initializing BigQuery tables for {PROJECT_ID}.{DATASET}...\n")
    
    created_count = 0
    for table_id, table_config in TABLES.items():
        if create_table_if_not_exists(table_id, table_config["schema"], table_config["description"]):
            created_count += 1
    
    print(f"\n📊 Summary:")
    print(f"   Tables created: {created_count}")
    print(f"   Tables already existed: {len(TABLES) - created_count}")
    print(f"   Total expected tables: {len(TABLES)}")

def verify_tables():
    """Verify all tables exist and report status."""
    print(f"\n📋 Verifying BigQuery tables for {PROJECT_ID}.{DATASET}...\n")
    
    status = verify_all_tables()
    
    print(f"✅ Expected tables: {len(status['expected'])}")
    print(f"   {', '.join(sorted(status['expected']))}\n")
    
    print(f"✅ Existing tables: {len(status['existing'])}")
    if status['existing']:
        print(f"   {', '.join(sorted(status['existing']))}\n")
    
    if status['missing']:
        print(f"❌ Missing tables: {len(status['missing'])}")
        print(f"   {', '.join(sorted(status['missing']))}\n")
        return False
    
    if status['extra']:
        print(f"⚠️  Extra tables (not in schema): {len(status['extra'])}")
        print(f"   {', '.join(sorted(status['extra']))}\n")
    
    if status['all_present']:
        print("✅ All required tables exist!")
        return True
    else:
        print("❌ Some required tables are missing")
        return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        verify_tables()
    else:
        init_all_tables()
        verify_tables()
