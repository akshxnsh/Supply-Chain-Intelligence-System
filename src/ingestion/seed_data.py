from datetime import datetime, timedelta
import os, csv, tempfile
from dotenv import load_dotenv

from src.ingestion.bq_client import client

load_dotenv()

PROJECT_ID = "akshxnsh-supplychain"
DATASET = "supply_chain"

def load_rows(table_id: str, rows: list[dict]):
    """Load rows via CSV — works in BigQuery Sandbox (no streaming needed)."""
    table_ref = f"{PROJECT_ID}.{DATASET}.{table_id}"

    # Write rows to a temp CSV file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv',
                                     delete=False, newline='') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        tmp_path = f.name

    # Load CSV into BigQuery
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,
    )

    with open(tmp_path, "rb") as f:
        job = client.load_table_from_file(f, table_ref, job_config=job_config)

    job.result()  # Wait for job to complete
    os.unlink(tmp_path)

    table = client.get_table(table_ref)
    print(f"✅ {table.num_rows} rows loaded into {table_id}")

def seed_business_suppliers():
    rows = [
        {"id": "sup-001", "business_id": "demo-business-001", "supplier_name": "Texas Gulf Imports",    "country": "USA",         "product_category": "roofing_materials", "annual_spend_usd": 180000},
        {"id": "sup-002", "business_id": "demo-business-001", "supplier_name": "Houston Steel Supply",  "country": "USA",         "product_category": "roofing_materials", "annual_spend_usd": 120000},
        {"id": "sup-003", "business_id": "demo-business-001", "supplier_name": "Guangzhou Metal Works", "country": "China",       "product_category": "roofing_materials", "annual_spend_usd": 95000},
        {"id": "sup-004", "business_id": "demo-business-001", "supplier_name": "Vietnam Hardware Co",   "country": "Vietnam",     "product_category": "roofing_materials", "annual_spend_usd": 60000},
        {"id": "sup-005", "business_id": "demo-business-001", "supplier_name": "Monterrey Steel MX",   "country": "Mexico",      "product_category": "roofing_materials", "annual_spend_usd": 75000},
        {"id": "sup-006", "business_id": "demo-business-001", "supplier_name": "Dallas Fasteners Inc",  "country": "USA",         "product_category": "fasteners",         "annual_spend_usd": 40000},
        {"id": "sup-007", "business_id": "demo-business-001", "supplier_name": "Seoul Components Ltd",  "country": "South Korea", "product_category": "fasteners",         "annual_spend_usd": 35000},
        {"id": "sup-008", "business_id": "demo-business-001", "supplier_name": "Mumbai Parts Exports",  "country": "India",       "product_category": "fasteners",         "annual_spend_usd": 28000},
    ]
    load_rows("business_suppliers", rows)

def seed_pending_orders():
    today = datetime.utcnow()
    rows = [
        {"id": "ord-001", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 28400, "eta_date": (today + timedelta(days=4)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-002", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 15200, "eta_date": (today + timedelta(days=6)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-003", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 9800,  "eta_date": (today + timedelta(days=8)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-004", "business_id": "demo-business-001", "supplier_id": "sup-002", "order_value_usd": 22000, "eta_date": (today + timedelta(days=5)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-005", "business_id": "demo-business-001", "supplier_id": "sup-002", "order_value_usd": 11500, "eta_date": (today + timedelta(days=10)).strftime("%Y-%m-%d"), "status": "pending"},
        {"id": "ord-006", "business_id": "demo-business-001", "supplier_id": "sup-003", "order_value_usd": 18700, "eta_date": (today + timedelta(days=14)).strftime("%Y-%m-%d"), "status": "pending"},
        {"id": "ord-007", "business_id": "demo-business-001", "supplier_id": "sup-006", "order_value_usd": 8400,  "eta_date": (today + timedelta(days=7)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-008", "business_id": "demo-business-001", "supplier_id": "sup-007", "order_value_usd": 6200,  "eta_date": (today + timedelta(days=9)).strftime("%Y-%m-%d"),  "status": "pending"},
    ]
    load_rows("pending_orders", rows)

def seed_alternative_suppliers():
    rows = [
        {"id": "alt-001", "name": "Memphis Steel Supply",       "country": "USA",         "product_category": "roofing_materials", "moq": 500,  "lead_time_days": 8,  "unit_price_usd": 4.82, "reliability_score": 9.2},
        {"id": "alt-002", "name": "Atlanta Hardware Co",        "country": "USA",         "product_category": "roofing_materials", "moq": 300,  "lead_time_days": 11, "unit_price_usd": 4.80, "reliability_score": 8.8},
        {"id": "alt-003", "name": "Chicago Metal Distributors", "country": "USA",         "product_category": "roofing_materials", "moq": 400,  "lead_time_days": 10, "unit_price_usd": 4.95, "reliability_score": 8.5},
        {"id": "alt-004", "name": "Monterrey Industrial MX",   "country": "Mexico",      "product_category": "roofing_materials", "moq": 600,  "lead_time_days": 9,  "unit_price_usd": 4.60, "reliability_score": 8.7},
        {"id": "alt-005", "name": "Toronto Steel Works",        "country": "Canada",      "product_category": "roofing_materials", "moq": 350,  "lead_time_days": 12, "unit_price_usd": 5.10, "reliability_score": 9.0},
        {"id": "alt-006", "name": "Hanoi Metal Exports",        "country": "Vietnam",     "product_category": "roofing_materials", "moq": 800,  "lead_time_days": 18, "unit_price_usd": 3.90, "reliability_score": 7.8},
        {"id": "alt-007", "name": "Taipei Hardware Ltd",        "country": "Taiwan",      "product_category": "roofing_materials", "moq": 700,  "lead_time_days": 15, "unit_price_usd": 4.20, "reliability_score": 8.3},
        {"id": "alt-008", "name": "Pune Steel Exports",         "country": "India",       "product_category": "roofing_materials", "moq": 1000, "lead_time_days": 21, "unit_price_usd": 3.70, "reliability_score": 7.5},
        {"id": "alt-009", "name": "Busan Components Co",        "country": "South Korea", "product_category": "roofing_materials", "moq": 500,  "lead_time_days": 16, "unit_price_usd": 4.40, "reliability_score": 8.6},
        {"id": "alt-010", "name": "Warsaw Metal Works",         "country": "Poland",      "product_category": "roofing_materials", "moq": 400,  "lead_time_days": 14, "unit_price_usd": 4.65, "reliability_score": 8.1},
        {"id": "alt-011", "name": "Phoenix Fasteners USA",      "country": "USA",         "product_category": "fasteners",         "moq": 200,  "lead_time_days": 7,  "unit_price_usd": 1.20, "reliability_score": 9.1},
        {"id": "alt-012", "name": "Detroit Parts Supply",       "country": "USA",         "product_category": "fasteners",         "moq": 150,  "lead_time_days": 9,  "unit_price_usd": 1.18, "reliability_score": 8.9},
        {"id": "alt-013", "name": "Guadalajara Fasteners",      "country": "Mexico",      "product_category": "fasteners",         "moq": 300,  "lead_time_days": 8,  "unit_price_usd": 0.98, "reliability_score": 8.4},
        {"id": "alt-014", "name": "Taipei Precision Parts",     "country": "Taiwan",      "product_category": "fasteners",         "moq": 400,  "lead_time_days": 14, "unit_price_usd": 1.05, "reliability_score": 8.7},
        {"id": "alt-015", "name": "Bangkok Industrial Parts",   "country": "Thailand",    "product_category": "fasteners",         "moq": 500,  "lead_time_days": 17, "unit_price_usd": 0.88, "reliability_score": 7.9},
        {"id": "alt-016", "name": "Penang Components",          "country": "Malaysia",    "product_category": "fasteners",         "moq": 450,  "lead_time_days": 15, "unit_price_usd": 0.92, "reliability_score": 8.2},
        {"id": "alt-017", "name": "Lodz Fastener Works",        "country": "Poland",      "product_category": "fasteners",         "moq": 250,  "lead_time_days": 13, "unit_price_usd": 1.10, "reliability_score": 8.0},
        {"id": "alt-018", "name": "Chennai Parts Export",       "country": "India",       "product_category": "fasteners",         "moq": 600,  "lead_time_days": 19, "unit_price_usd": 0.82, "reliability_score": 7.6},
        {"id": "alt-019", "name": "Osaka Precision Co",         "country": "Japan",       "product_category": "fasteners",         "moq": 300,  "lead_time_days": 16, "unit_price_usd": 1.35, "reliability_score": 9.3},
        {"id": "alt-020", "name": "Incheon Parts Ltd",          "country": "South Korea", "product_category": "fasteners",         "moq": 350,  "lead_time_days": 14, "unit_price_usd": 1.15, "reliability_score": 8.8},
    ]
    load_rows("alternative_suppliers", rows)

def seed_port_activity():
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        {"port_id": "port-001", "port_name": "Port of Houston",    "congestion_score": 8.5, "vessel_delay_hours": 72.0, "strike_flag": True,  "updated_at": now},
        {"port_id": "port-002", "port_name": "Port of Los Angeles", "congestion_score": 3.2, "vessel_delay_hours": 12.0, "strike_flag": False, "updated_at": now},
        {"port_id": "port-003", "port_name": "Port of Long Beach",  "congestion_score": 2.8, "vessel_delay_hours": 8.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-004", "port_name": "Port of Seattle",     "congestion_score": 2.1, "vessel_delay_hours": 4.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-005", "port_name": "Port of New York",    "congestion_score": 3.5, "vessel_delay_hours": 10.0, "strike_flag": False, "updated_at": now},
        {"port_id": "port-006", "port_name": "Port of Savannah",    "congestion_score": 2.9, "vessel_delay_hours": 6.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-007", "port_name": "Port of Miami",       "congestion_score": 2.2, "vessel_delay_hours": 5.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-008", "port_name": "Port of Shanghai",    "congestion_score": 4.1, "vessel_delay_hours": 18.0, "strike_flag": False, "updated_at": now},
        {"port_id": "port-009", "port_name": "Port of Shenzhen",    "congestion_score": 3.8, "vessel_delay_hours": 14.0, "strike_flag": False, "updated_at": now},
        {"port_id": "port-010", "port_name": "Port of Rotterdam",   "congestion_score": 2.5, "vessel_delay_hours": 6.0,  "strike_flag": False, "updated_at": now},
    ]
    load_rows("port_activity", rows)

def seed_disruption_events():
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        {
            "id": "evt-001",
            "source": "weather_api",
            "headline": "Category 3 Hurricane approaching Port of Houston — landfall expected in 18 hours",
            "location_name": "Houston, Texas, USA",
            "lat": 29.7604,
            "lon": -95.3698,
            "severity_raw": 8.5,
            "published_at": now,
            "inserted_at": now,
        }
    ]
    load_rows("disruption_events", rows)

if __name__ == "__main__":
    print("🌱 Seeding BigQuery tables...\n")
    seed_business_suppliers()
    seed_pending_orders()
    seed_alternative_suppliers()
    seed_port_activity()
    seed_disruption_events()
    print("\n✅ ALL SEED DATA LOADED — BigQuery ready")