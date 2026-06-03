from datetime import datetime, timedelta
import os, csv, tempfile
from dotenv import load_dotenv
from google.cloud import bigquery

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
    # quantity and primary_unit_price_usd allow exact per-unit cost comparisons vs alternate suppliers
    rows = [
        {"id": "ord-001", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 28400, "quantity": 5900, "primary_unit_price_usd": 4.81, "eta_date": (today + timedelta(days=4)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-002", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 15200, "quantity": 3160, "primary_unit_price_usd": 4.81, "eta_date": (today + timedelta(days=6)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-003", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 9800,  "quantity": 2036, "primary_unit_price_usd": 4.81, "eta_date": (today + timedelta(days=8)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-004", "business_id": "demo-business-001", "supplier_id": "sup-002", "order_value_usd": 22000, "quantity": 4490, "primary_unit_price_usd": 4.90, "eta_date": (today + timedelta(days=5)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-005", "business_id": "demo-business-001", "supplier_id": "sup-002", "order_value_usd": 11500, "quantity": 2347, "primary_unit_price_usd": 4.90, "eta_date": (today + timedelta(days=10)).strftime("%Y-%m-%d"), "status": "pending"},
        {"id": "ord-006", "business_id": "demo-business-001", "supplier_id": "sup-003", "order_value_usd": 18700, "quantity": 4230, "primary_unit_price_usd": 4.42, "eta_date": (today + timedelta(days=14)).strftime("%Y-%m-%d"), "status": "pending"},
        {"id": "ord-007", "business_id": "demo-business-001", "supplier_id": "sup-006", "order_value_usd": 8400,  "quantity": 7000, "primary_unit_price_usd": 1.20, "eta_date": (today + timedelta(days=7)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "ord-008", "business_id": "demo-business-001", "supplier_id": "sup-007", "order_value_usd": 6200,  "quantity": 5565, "primary_unit_price_usd": 1.11, "eta_date": (today + timedelta(days=9)).strftime("%Y-%m-%d"),  "status": "pending"},
    ]
    load_rows("pending_orders", rows)

def seed_alternative_suppliers():
    rows = [
        {"id": "alt-001", "name": "Memphis Steel Supply",       "country": "USA",         "product_category": "roofing_materials", "moq": 500,  "lead_time_days": 8,  "unit_price_usd": 4.82, "reliability_score": 9.2, "geographic_risk_score": 9.0},
        {"id": "alt-002", "name": "Atlanta Hardware Co",        "country": "USA",         "product_category": "roofing_materials", "moq": 300,  "lead_time_days": 11, "unit_price_usd": 4.80, "reliability_score": 8.8, "geographic_risk_score": 9.0},
        {"id": "alt-003", "name": "Chicago Metal Distributors", "country": "USA",         "product_category": "roofing_materials", "moq": 400,  "lead_time_days": 10, "unit_price_usd": 4.95, "reliability_score": 8.5, "geographic_risk_score": 9.0},
        {"id": "alt-004", "name": "Monterrey Industrial MX",   "country": "Mexico",      "product_category": "roofing_materials", "moq": 600,  "lead_time_days": 9,  "unit_price_usd": 4.60, "reliability_score": 8.7, "geographic_risk_score": 9.0},
        {"id": "alt-005", "name": "Toronto Steel Works",        "country": "Canada",      "product_category": "roofing_materials", "moq": 350,  "lead_time_days": 12, "unit_price_usd": 5.10, "reliability_score": 9.0, "geographic_risk_score": 9.0},
        {"id": "alt-006", "name": "Hanoi Metal Exports",        "country": "Vietnam",     "product_category": "roofing_materials", "moq": 800,  "lead_time_days": 18, "unit_price_usd": 3.90, "reliability_score": 7.8, "geographic_risk_score": 6.5},
        {"id": "alt-007", "name": "Taipei Hardware Ltd",        "country": "Taiwan",      "product_category": "roofing_materials", "moq": 700,  "lead_time_days": 15, "unit_price_usd": 4.20, "reliability_score": 8.3, "geographic_risk_score": 7.5},
        {"id": "alt-008", "name": "Pune Steel Exports",         "country": "India",       "product_category": "roofing_materials", "moq": 1000, "lead_time_days": 21, "unit_price_usd": 3.70, "reliability_score": 7.5, "geographic_risk_score": 6.0},
        {"id": "alt-009", "name": "Busan Components Co",        "country": "South Korea", "product_category": "roofing_materials", "moq": 500,  "lead_time_days": 16, "unit_price_usd": 4.40, "reliability_score": 8.6, "geographic_risk_score": 8.0},
        {"id": "alt-010", "name": "Warsaw Metal Works",         "country": "Poland",      "product_category": "roofing_materials", "moq": 400,  "lead_time_days": 14, "unit_price_usd": 4.65, "reliability_score": 8.1, "geographic_risk_score": 7.5},
        {"id": "alt-011", "name": "Phoenix Fasteners USA",      "country": "USA",         "product_category": "fasteners",         "moq": 200,  "lead_time_days": 7,  "unit_price_usd": 1.20, "reliability_score": 9.1, "geographic_risk_score": 9.0},
        {"id": "alt-012", "name": "Detroit Parts Supply",       "country": "USA",         "product_category": "fasteners",         "moq": 150,  "lead_time_days": 9,  "unit_price_usd": 1.18, "reliability_score": 8.9, "geographic_risk_score": 9.0},
        {"id": "alt-013", "name": "Guadalajara Fasteners",      "country": "Mexico",      "product_category": "fasteners",         "moq": 300,  "lead_time_days": 8,  "unit_price_usd": 0.98, "reliability_score": 8.4, "geographic_risk_score": 9.0},
        {"id": "alt-014", "name": "Taipei Precision Parts",     "country": "Taiwan",      "product_category": "fasteners",         "moq": 400,  "lead_time_days": 14, "unit_price_usd": 1.05, "reliability_score": 8.7, "geographic_risk_score": 7.5},
        {"id": "alt-015", "name": "Bangkok Industrial Parts",   "country": "Thailand",    "product_category": "fasteners",         "moq": 500,  "lead_time_days": 17, "unit_price_usd": 0.88, "reliability_score": 7.9, "geographic_risk_score": 6.5},
        {"id": "alt-016", "name": "Penang Components",          "country": "Malaysia",    "product_category": "fasteners",         "moq": 450,  "lead_time_days": 15, "unit_price_usd": 0.92, "reliability_score": 8.2, "geographic_risk_score": 6.5},
        {"id": "alt-017", "name": "Lodz Fastener Works",        "country": "Poland",      "product_category": "fasteners",         "moq": 250,  "lead_time_days": 13, "unit_price_usd": 1.10, "reliability_score": 8.0, "geographic_risk_score": 7.5},
        {"id": "alt-018", "name": "Chennai Parts Export",       "country": "India",       "product_category": "fasteners",         "moq": 600,  "lead_time_days": 19, "unit_price_usd": 0.82, "reliability_score": 7.6, "geographic_risk_score": 6.0},
        {"id": "alt-019", "name": "Osaka Precision Co",         "country": "Japan",       "product_category": "fasteners",         "moq": 300,  "lead_time_days": 16, "unit_price_usd": 1.35, "reliability_score": 9.3, "geographic_risk_score": 8.5},
        {"id": "alt-020", "name": "Incheon Parts Ltd",          "country": "South Korea", "product_category": "fasteners",         "moq": 350,  "lead_time_days": 14, "unit_price_usd": 1.15, "reliability_score": 8.8, "geographic_risk_score": 8.0},
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

def seed_weather_alerts():
    """Seed weather alerts table (typically populated by Fivetran)."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        {
            "id": "weather-001",
            "region": "Gulf Coast, Texas",
            "alert_type": "Hurricane Warning",
            "severity": 8.5,
            "start_time": now,
            "end_time": (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%S"),
            "affected_ports": "Port of Houston, Port of Texas City, Port of Corpus Christi",
            "created_at": now,
        },
        {
            "id": "weather-002",
            "region": "Southeast Asia",
            "alert_type": "Monsoon Warning",
            "severity": 6.2,
            "start_time": now,
            "end_time": (datetime.utcnow() + timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%S"),
            "affected_ports": "Port of Shanghai, Port of Hong Kong, Port of Singapore",
            "created_at": now,
        },
        {
            "id": "weather-003",
            "region": "West Coast, USA",
            "alert_type": "Storm Advisory",
            "severity": 4.1,
            "start_time": now,
            "end_time": (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
            "affected_ports": "Port of Los Angeles, Port of Long Beach",
            "created_at": now,
        },
    ]
    load_rows("weather_alerts", rows)

def seed_agent_calibration():
    """Seed agent calibration table with 3-stage historical data for self-improvement loop."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        # Event 1: Hurricane in Houston (Stage 1 & 2 & 3)
        {
            "id": "calib-001",
            "event_type": "disruption_detection",
            "region": "Gulf Coast, Texas",
            # Stage 1: Alert fires
            "severity_scored": 8.5,
            "delay_days_predicted": 14,
            "supplier_recommended": "Memphis Steel Supply",
            "exposure_calculated": 53400.0,
            "owner_approved": True,
            # Stage 2: Owner decision
            "owner_override": False,
            "rejection_reason": None,
            # Stage 3: Outcome (30 days later)
            "actual_delay_days": 13,
            "supplier_delivered": True,
            # Accuracy metrics
            "hallucination_score": 0.1,
            "relevance_score": 0.95,
            "helpfulness_score": 0.92,
            "reasoning_score": 0.88,
            # Calibration
            "calibration_applied": True,
            "weighted_baseline": 8.2,
            "created_at": now,
        },
        # Event 2: Port Strike Shanghai (Stage 1 & 2 & 3)
        {
            "id": "calib-002",
            "event_type": "port_disruption",
            "region": "East China Sea, Shanghai",
            "severity_scored": 7.2,
            "delay_days_predicted": 10,
            "supplier_recommended": "Taipei Hardware Ltd",
            "exposure_calculated": 18700.0,
            "owner_approved": True,
            "owner_override": False,
            "rejection_reason": None,
            "actual_delay_days": 11,
            "supplier_delivered": True,
            "hallucination_score": 0.05,
            "relevance_score": 0.93,
            "helpfulness_score": 0.90,
            "reasoning_score": 0.85,
            "calibration_applied": True,
            "weighted_baseline": 7.0,
            "created_at": now,
        },
        # Event 3: Monsoon Warning SE Asia (Stage 1 & 2 & 3)
        {
            "id": "calib-003",
            "event_type": "weather_alert",
            "region": "Southeast Asia, Thailand",
            "severity_scored": 6.2,
            "delay_days_predicted": 8,
            "supplier_recommended": "Bangkok Industrial Parts",
            "exposure_calculated": 9200.0,
            "owner_approved": True,
            "owner_override": True,
            "rejection_reason": "Owner had inventory to cover",
            "actual_delay_days": 7,
            "supplier_delivered": True,
            "hallucination_score": 0.15,
            "relevance_score": 0.87,
            "helpfulness_score": 0.84,
            "reasoning_score": 0.82,
            "calibration_applied": True,
            "weighted_baseline": 6.0,
            "created_at": now,
        },
        # Event 4: False alarm - minor weather event
        {
            "id": "calib-004",
            "event_type": "weather_alert",
            "region": "West Coast, California",
            "severity_scored": 3.5,
            "delay_days_predicted": 2,
            "supplier_recommended": None,
            "exposure_calculated": 0.0,
            "owner_approved": False,
            "owner_override": False,
            "rejection_reason": "No suppliers affected",
            "actual_delay_days": 1,
            "supplier_delivered": True,
            "hallucination_score": 0.02,
            "relevance_score": 0.98,
            "helpfulness_score": 0.95,
            "reasoning_score": 0.96,
            "calibration_applied": True,
            "weighted_baseline": 3.2,
            "created_at": now,
        },
        # Event 5: Over-estimated risk
        {
            "id": "calib-005",
            "event_type": "disruption_detection",
            "region": "India, Chennai Port",
            "severity_scored": 7.8,
            "delay_days_predicted": 12,
            "supplier_recommended": "Chennai Parts Export",
            "exposure_calculated": 12400.0,
            "owner_approved": True,
            "owner_override": False,
            "rejection_reason": None,
            "actual_delay_days": 3,
            "supplier_delivered": True,
            "hallucination_score": 0.25,
            "relevance_score": 0.80,
            "helpfulness_score": 0.75,
            "reasoning_score": 0.78,
            "calibration_applied": True,
            "weighted_baseline": 7.5,
            "created_at": now,
        },
    ]
    load_rows("agent_calibration", rows)

def seed_tariff_updates():
    """
    Seed tariff updates affecting supplier costs.
    Realistic scenario: Recent US trade tensions with China + Vietnam.
    """
    now = datetime.utcnow().isoformat()
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).date()
    ten_days_ago = (datetime.utcnow() - timedelta(days=10)).date()
    
    rows = [
        {
            "id": "tariff-001",
            "country_of_origin": "China",
            "product_category": "roofing_materials",
            "tariff_rate_percentage": 25.0,
            "effective_date": str(ten_days_ago),
            "description": "Section 301 tariff on Chinese steel products - 25% rate effective immediately",
            "created_at": now,
        },
        {
            "id": "tariff-002",
            "country_of_origin": "Vietnam",
            "product_category": "roofing_materials",
            "tariff_rate_percentage": 15.0,
            "effective_date": str(ten_days_ago),
            "description": "Retaliatory tariff on Vietnamese imports - 15% rate",
            "created_at": now,
        },
        {
            "id": "tariff-003",
            "country_of_origin": "South Korea",
            "product_category": "fasteners",
            "tariff_rate_percentage": 12.5,
            "effective_date": str(thirty_days_ago),
            "description": "Automotive tariff extension to fasteners - 12.5% rate",
            "created_at": now,
        },
        {
            "id": "tariff-004",
            "country_of_origin": "Mexico",
            "product_category": "roofing_materials",
            "tariff_rate_percentage": 5.0,
            "effective_date": str(thirty_days_ago),
            "description": "USMCA adjustment tariff - 5% on steel products",
            "created_at": now,
        },
    ]
    load_rows("tariff_updates", rows)

def seed_inventory():
    """Seed inventory data by product category."""
    now = datetime.utcnow().isoformat()
    rows = [
        {"id": "inv-001", "business_id": "demo-business-001", "product_category": "roofing_materials", "inventory_value_usd": 15000.0, "updated_at": now},
        {"id": "inv-002", "business_id": "demo-business-001", "product_category": "fasteners", "inventory_value_usd": 5000.0, "updated_at": now},
    ]
    load_rows("inventory", rows)

def seed_completed_orders():
    """Seed historical completed orders for dynamic supplier reliability calculation."""
    today = datetime.utcnow().date()
    def d(days_ago): return str(today - timedelta(days=days_ago))
    rows = [
        # sup-001 (Texas Gulf Imports): generally reliable, 1 late delivery
        {"id": "co-001", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 24000, "ordered_date": d(90), "expected_delivery_date": d(76), "actual_delivery_date": d(76), "delay_days": 0,  "defective_items_count": 0,  "status": "delivered"},
        {"id": "co-002", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 18500, "ordered_date": d(75), "expected_delivery_date": d(61), "actual_delivery_date": d(58), "delay_days": -3, "defective_items_count": 0,  "status": "delivered"},
        {"id": "co-003", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 31000, "ordered_date": d(60), "expected_delivery_date": d(46), "actual_delivery_date": d(53), "delay_days": 7,  "defective_items_count": 12, "status": "delivered"},
        {"id": "co-004", "business_id": "demo-business-001", "supplier_id": "sup-001", "order_value_usd": 27000, "ordered_date": d(45), "expected_delivery_date": d(31), "actual_delivery_date": d(31), "delay_days": 0,  "defective_items_count": 0,  "status": "delivered"},
        # sup-002 (Houston Steel Supply): very reliable, no delays
        {"id": "co-005", "business_id": "demo-business-001", "supplier_id": "sup-002", "order_value_usd": 20000, "ordered_date": d(80), "expected_delivery_date": d(66), "actual_delivery_date": d(65), "delay_days": -1, "defective_items_count": 0,  "status": "delivered"},
        {"id": "co-006", "business_id": "demo-business-001", "supplier_id": "sup-002", "order_value_usd": 15000, "ordered_date": d(55), "expected_delivery_date": d(41), "actual_delivery_date": d(41), "delay_days": 0,  "defective_items_count": 0,  "status": "delivered"},
        {"id": "co-007", "business_id": "demo-business-001", "supplier_id": "sup-002", "order_value_usd": 22000, "ordered_date": d(35), "expected_delivery_date": d(21), "actual_delivery_date": d(21), "delay_days": 0,  "defective_items_count": 3,  "status": "delivered"},
        # sup-003 (Guangzhou Metal Works): occasional delays, cost-effective
        {"id": "co-008", "business_id": "demo-business-001", "supplier_id": "sup-003", "order_value_usd": 16000, "ordered_date": d(100),"expected_delivery_date": d(79), "actual_delivery_date": d(82), "delay_days": 3,  "defective_items_count": 20, "status": "delivered"},
        {"id": "co-009", "business_id": "demo-business-001", "supplier_id": "sup-003", "order_value_usd": 19000, "ordered_date": d(70), "expected_delivery_date": d(49), "actual_delivery_date": d(60), "delay_days": 11, "defective_items_count": 35, "status": "delivered"},
        # sup-006 (Dallas Fasteners): perfect record
        {"id": "co-010", "business_id": "demo-business-001", "supplier_id": "sup-006", "order_value_usd": 7500,  "ordered_date": d(65), "expected_delivery_date": d(58), "actual_delivery_date": d(57), "delay_days": -1, "defective_items_count": 0,  "status": "delivered"},
        {"id": "co-011", "business_id": "demo-business-001", "supplier_id": "sup-006", "order_value_usd": 9200,  "ordered_date": d(40), "expected_delivery_date": d(33), "actual_delivery_date": d(33), "delay_days": 0,  "defective_items_count": 0,  "status": "delivered"},
        # sup-007 (Seoul Components): reliable but longer lead time
        {"id": "co-012", "business_id": "demo-business-001", "supplier_id": "sup-007", "order_value_usd": 5800,  "ordered_date": d(95), "expected_delivery_date": d(77), "actual_delivery_date": d(79), "delay_days": 2,  "defective_items_count": 5,  "status": "delivered"},
        {"id": "co-013", "business_id": "demo-business-001", "supplier_id": "sup-007", "order_value_usd": 6600,  "ordered_date": d(50), "expected_delivery_date": d(32), "actual_delivery_date": d(32), "delay_days": 0,  "defective_items_count": 0,  "status": "delivered"},
        # alt-001 (Memphis Steel Supply): for alternative suppliers too
        {"id": "co-014", "business_id": "demo-business-001", "supplier_id": "alt-001", "order_value_usd": 12000, "ordered_date": d(120),"expected_delivery_date": d(112),"actual_delivery_date": d(112),"delay_days": 0,  "defective_items_count": 0,  "status": "delivered"},
        {"id": "co-015", "business_id": "demo-business-001", "supplier_id": "alt-001", "order_value_usd": 9000,  "ordered_date": d(85), "expected_delivery_date": d(77), "actual_delivery_date": d(76), "delay_days": -1, "defective_items_count": 0,  "status": "delivered"},
        # alt-002 (Atlanta Hardware Co): slight delay history
        {"id": "co-016", "business_id": "demo-business-001", "supplier_id": "alt-002", "order_value_usd": 8500,  "ordered_date": d(110),"expected_delivery_date": d(99), "actual_delivery_date": d(103),"delay_days": 4,  "defective_items_count": 8,  "status": "delivered"},
        # alt-004 (Monterrey Industrial MX): good but tariff risk
        {"id": "co-017", "business_id": "demo-business-001", "supplier_id": "alt-004", "order_value_usd": 11000, "ordered_date": d(130),"expected_delivery_date": d(121),"actual_delivery_date": d(121),"delay_days": 0,  "defective_items_count": 2,  "status": "delivered"},
    ]
    load_rows("completed_orders", rows)

def seed_supplier_reviews():
    """Seed supplier reviews for qualitative reliability signal."""
    now = datetime.utcnow().isoformat()
    def ts(days_ago): return (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
    rows = [
        {"id": "rev-001", "supplier_id": "sup-001", "business_id": "demo-business-001", "rating": 4.2, "review_text": "Good supplier overall, one late shipment last quarter.",      "review_date": ts(30)},
        {"id": "rev-002", "supplier_id": "sup-001", "business_id": "demo-business-001", "rating": 4.5, "review_text": "Excellent quality and competitive pricing.",                 "review_date": ts(90)},
        {"id": "rev-003", "supplier_id": "sup-002", "business_id": "demo-business-001", "rating": 4.8, "review_text": "Very reliable, always on time. Highly recommended.",          "review_date": ts(20)},
        {"id": "rev-004", "supplier_id": "sup-002", "business_id": "demo-business-001", "rating": 4.7, "review_text": "Consistent quality, fast response to issues.",               "review_date": ts(75)},
        {"id": "rev-005", "supplier_id": "sup-003", "business_id": "demo-business-001", "rating": 3.1, "review_text": "Prices are good but delays are a regular issue.",            "review_date": ts(40)},
        {"id": "rev-006", "supplier_id": "sup-003", "business_id": "demo-business-001", "rating": 3.5, "review_text": "Mixed experience. Quality control needs improvement.",        "review_date": ts(110)},
        {"id": "rev-007", "supplier_id": "sup-006", "business_id": "demo-business-001", "rating": 4.9, "review_text": "Best fastener supplier we have worked with, zero defects.",   "review_date": ts(15)},
        {"id": "rev-008", "supplier_id": "sup-007", "business_id": "demo-business-001", "rating": 4.3, "review_text": "Korean supplier, good quality. Lead time a bit long.",        "review_date": ts(60)},
        {"id": "rev-009", "supplier_id": "alt-001", "business_id": "demo-business-001", "rating": 4.7, "review_text": "Memphis Steel is exceptional. Zero delays in 2 orders.",     "review_date": ts(45)},
        {"id": "rev-010", "supplier_id": "alt-002", "business_id": "demo-business-001", "rating": 3.9, "review_text": "Atlanta Hardware was 4 days late but quality was okay.",     "review_date": ts(70)},
        {"id": "rev-011", "supplier_id": "alt-004", "business_id": "demo-business-001", "rating": 4.4, "review_text": "Monterrey Industrial is cost-effective and punctual.",        "review_date": ts(80)},
    ]
    load_rows("supplier_reviews", rows)

if __name__ == "__main__":
    print("🌱 Seeding BigQuery tables...\n")
    seed_business_suppliers()
    seed_pending_orders()
    seed_alternative_suppliers()
    seed_port_activity()
    seed_disruption_events()
    seed_weather_alerts()
    seed_agent_calibration()
    seed_tariff_updates()
    seed_inventory()
    seed_completed_orders()
    seed_supplier_reviews()
    print("\n✅ ALL SEED DATA LOADED — BigQuery ready")