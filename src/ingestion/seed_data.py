from datetime import datetime, timedelta
import os, csv, tempfile
from dotenv import load_dotenv
from google.cloud import bigquery

from src.ingestion.bq_client import client

load_dotenv()

PROJECT_ID = "akshxnsh-supplychain"
DATASET = "supply_chain"

def load_rows(
    table_id: str,
    rows: list[dict],
    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
):
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
        write_disposition=write_disposition,
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
        # auto_parts — Mid-Atlantic Auto Parts Distribution LLC, primary port: Port of Baltimore
        {"id": "sup-001", "business_id": "demo-business-001", "supplier_name": "Bavarian Parts GmbH",      "country": "Germany",     "product_category": "auto_parts", "annual_spend_usd": 340000},
        {"id": "sup-002", "business_id": "demo-business-001", "supplier_name": "Hyundai Mobis Trade",       "country": "South Korea", "product_category": "auto_parts", "annual_spend_usd": 280000},
        {"id": "sup-003", "business_id": "demo-business-001", "supplier_name": "Guangzhou Auto Components", "country": "China",       "product_category": "auto_parts", "annual_spend_usd": 195000},
        {"id": "sup-004", "business_id": "demo-business-001", "supplier_name": "Harrisburg Auto Supply",    "country": "USA",         "product_category": "auto_parts", "annual_spend_usd": 120000},
        {"id": "sup-005", "business_id": "demo-business-001", "supplier_name": "Ontario Parts Exports",     "country": "Canada",      "product_category": "auto_parts", "annual_spend_usd": 95000},
        # fasteners
        {"id": "sup-006", "business_id": "demo-business-001", "supplier_name": "Dallas Fasteners Inc",      "country": "USA",         "product_category": "fasteners",  "annual_spend_usd": 40000},
        {"id": "sup-007", "business_id": "demo-business-001", "supplier_name": "Seoul Components Ltd",      "country": "South Korea", "product_category": "fasteners",  "annual_spend_usd": 35000},
        {"id": "sup-008", "business_id": "demo-business-001", "supplier_name": "Mumbai Parts Exports",      "country": "India",       "product_category": "fasteners",  "annual_spend_usd": 28000},
    ]
    load_rows("business_suppliers", rows)

def seed_pending_orders():
    today = datetime.utcnow()
    # Client orders — what customers have ordered from the business (demand side)
    rows = [
        {"id": "co-001", "business_id": "demo-business-001", "client_id": "client-alpha",   "product_category": "auto_parts", "quantity": 1460, "order_value_usd": 58400,  "required_by_date": (today + timedelta(days=14)).strftime("%Y-%m-%d"), "status": "pending"},
        {"id": "co-002", "business_id": "demo-business-001", "client_id": "client-beta",    "product_category": "auto_parts", "quantity": 1030, "order_value_usd": 41200,  "required_by_date": (today + timedelta(days=18)).strftime("%Y-%m-%d"), "status": "pending"},
        {"id": "co-003", "business_id": "demo-business-001", "client_id": "client-gamma",   "product_category": "auto_parts", "quantity": 1950, "order_value_usd": 78000,  "required_by_date": (today + timedelta(days=21)).strftime("%Y-%m-%d"), "status": "pending"},
        {"id": "co-004", "business_id": "demo-business-001", "client_id": "client-delta",   "product_category": "auto_parts", "quantity": 615,  "order_value_usd": 24600,  "required_by_date": (today + timedelta(days=25)).strftime("%Y-%m-%d"), "status": "pending"},
        {"id": "co-005", "business_id": "demo-business-001", "client_id": "client-epsilon", "product_category": "fasteners",         "quantity": 3000, "order_value_usd": 3600,  "required_by_date": (today + timedelta(days=8)).strftime("%Y-%m-%d"),  "status": "pending"},
        {"id": "co-006", "business_id": "demo-business-001", "client_id": "client-zeta",    "product_category": "fasteners",         "quantity": 2000, "order_value_usd": 2400,  "required_by_date": (today + timedelta(days=14)).strftime("%Y-%m-%d"), "status": "pending"},
    ]
    load_rows("pending_orders", rows)


def seed_shipment_timetable():
    today = datetime.utcnow()
    def shipment_row(
        shipment_id,
        business_id,
        supplier_id,
        product_category,
        quantity,
        shipment_value_usd,
        origin_port,
        destination_port,
        etd,
        eta,
        route,
    ):
        return {
            "id": shipment_id,
            "business_id": business_id,
            "supplier_id": supplier_id,
            "product_category": product_category,
            "quantity": quantity,
            "shipment_value_usd": shipment_value_usd,
            "origin_port": origin_port,
            "destination_port": destination_port,
            "dispatched_date": etd.strftime("%Y-%m-%d"),
            "expected_arrival_date": eta.strftime("%Y-%m-%d"),
            "etd": etd.strftime("%Y-%m-%dT%H:%M:%S"),
            "eta": eta.strftime("%Y-%m-%dT%H:%M:%S"),
            "journey_time_hours": round((eta - etd).total_seconds() / 3600, 1),
            "route": route,
            "status": "in_transit",
        }

    # Inbound supplier shipments — Baltimore bridge collapse scenario (demo-business-001)
    rows = [
        # auto_parts from international suppliers — all routed through Port of Baltimore (at risk)
        shipment_row("shp-001", "demo-business-001", "sup-001", "auto_parts", 4550, 182000, "Port of Hamburg",      "Port of Baltimore", today - timedelta(days=12), today + timedelta(days=7),  "Port of Hamburg > English Channel > Atlantic Crossing > Port of Baltimore"),
        shipment_row("shp-002", "demo-business-001", "sup-002", "auto_parts", 3200, 128000, "Port of Busan",        "Port of Baltimore", today - timedelta(days=14), today + timedelta(days=5),  "Port of Busan > Pacific Crossing > Port of Los Angeles > Port of Baltimore"),
        shipment_row("shp-003", "demo-business-001", "sup-003", "auto_parts", 1700,  68000, "Port of Shanghai",     "Port of Baltimore", today - timedelta(days=18), today + timedelta(days=9),  "Port of Shanghai > Singapore Strait > Pacific Crossing > Port of Los Angeles > Port of Baltimore"),
        # auto_parts rerouted to Port of Virginia — safe (avoids bridge closure)
        shipment_row("shp-005", "demo-business-001", "sup-005", "auto_parts", 2800, 112000, "Port of Montreal",     "Port of Virginia",  today - timedelta(days=5),  today + timedelta(days=8),  "Port of Montreal > Atlantic Coast > Port of Virginia"),
        # fasteners from US domestic (at risk — routed via Port of Baltimore)
        shipment_row("shp-006", "demo-business-001", "sup-006", "fasteners",  7000,   8400, "Port of Houston",      "Port of Baltimore", today - timedelta(days=1),  today + timedelta(days=7),  "Port of Houston > Memphis Rail Hub > Port of Baltimore"),
        # fasteners from Korea — one at risk, one rerouted to Port of Virginia
        shipment_row("shp-007", "demo-business-001", "sup-007", "fasteners",  5565,   6200, "Port of Busan",        "Port of Baltimore", today - timedelta(days=3),  today + timedelta(days=9),  "Port of Busan > Pacific Crossing > Port of Los Angeles > Port of Baltimore"),
        shipment_row("shp-008", "demo-business-001", "sup-007", "fasteners",  2800,   3100, "Port of Busan",        "Port of Virginia",  today - timedelta(days=6),  today + timedelta(days=10), "Port of Busan > Pacific Crossing > Port of Los Angeles > Port of Virginia"),
    ]
    load_rows("shipment_timetable", rows)

def seed_alternative_suppliers():
    rows = [
        # auto_parts alternatives — domestic USA options rank highest for speed
        {"id": "alt-001", "name": "Harrisburg Auto Parts",     "country": "USA",         "product_category": "auto_parts", "moq": 500,  "lead_time_days": 3,  "unit_price_usd": 4.50, "reliability_score": 9.5, "geographic_risk_score": 9.5},
        {"id": "alt-002", "name": "Richmond Auto Supply",       "country": "USA",         "product_category": "auto_parts", "moq": 300,  "lead_time_days": 4,  "unit_price_usd": 4.20, "reliability_score": 9.2, "geographic_risk_score": 9.5},
        {"id": "alt-003", "name": "Detroit Auto Distributors",  "country": "USA",         "product_category": "auto_parts", "moq": 400,  "lead_time_days": 5,  "unit_price_usd": 3.90, "reliability_score": 8.9, "geographic_risk_score": 9.5},
        {"id": "alt-004", "name": "Atlanta Parts Supply",       "country": "USA",         "product_category": "auto_parts", "moq": 350,  "lead_time_days": 5,  "unit_price_usd": 4.10, "reliability_score": 8.7, "geographic_risk_score": 9.5},
        {"id": "alt-005", "name": "Ontario Auto Components",    "country": "Canada",      "product_category": "auto_parts", "moq": 600,  "lead_time_days": 8,  "unit_price_usd": 4.00, "reliability_score": 9.0, "geographic_risk_score": 9.0},
        {"id": "alt-006", "name": "Saltillo Auto Parts MX",    "country": "Mexico",      "product_category": "auto_parts", "moq": 500,  "lead_time_days": 7,  "unit_price_usd": 3.75, "reliability_score": 8.4, "geographic_risk_score": 8.5},
        {"id": "alt-007", "name": "Warsaw Auto Components",     "country": "Poland",      "product_category": "auto_parts", "moq": 400,  "lead_time_days": 14, "unit_price_usd": 3.80, "reliability_score": 8.1, "geographic_risk_score": 7.5},
        {"id": "alt-008", "name": "Ankara Parts Export",        "country": "Turkey",      "product_category": "auto_parts", "moq": 700,  "lead_time_days": 12, "unit_price_usd": 3.60, "reliability_score": 8.3, "geographic_risk_score": 7.0},
        {"id": "alt-009", "name": "Pune Auto Components",       "country": "India",       "product_category": "auto_parts", "moq": 1000, "lead_time_days": 20, "unit_price_usd": 3.50, "reliability_score": 7.5, "geographic_risk_score": 6.0},
        {"id": "alt-010", "name": "Taipei Auto Parts",          "country": "Taiwan",      "product_category": "auto_parts", "moq": 500,  "lead_time_days": 16, "unit_price_usd": 4.00, "reliability_score": 8.6, "geographic_risk_score": 7.5},
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
        {"port_id": "port-001", "port_name": "Port of Houston",    "congestion_score": 8.5,  "vessel_delay_hours": 72.0,   "strike_flag": True,  "updated_at": now},
        {"port_id": "port-002", "port_name": "Port of Los Angeles", "congestion_score": 3.2,  "vessel_delay_hours": 12.0,   "strike_flag": False, "updated_at": now},
        {"port_id": "port-003", "port_name": "Port of Long Beach",  "congestion_score": 2.8,  "vessel_delay_hours": 8.0,    "strike_flag": False, "updated_at": now},
        {"port_id": "port-004", "port_name": "Port of Seattle",     "congestion_score": 2.1,  "vessel_delay_hours": 4.0,    "strike_flag": False, "updated_at": now},
        # Port of New York sees elevated congestion as overflow from Baltimore closure
        {"port_id": "port-005", "port_name": "Port of New York",    "congestion_score": 6.8,  "vessel_delay_hours": 36.0,   "strike_flag": False, "updated_at": now},
        {"port_id": "port-006", "port_name": "Port of Savannah",    "congestion_score": 2.9,  "vessel_delay_hours": 6.0,    "strike_flag": False, "updated_at": now},
        {"port_id": "port-007", "port_name": "Port of Miami",       "congestion_score": 2.2,  "vessel_delay_hours": 5.0,    "strike_flag": False, "updated_at": now},
        {"port_id": "port-008", "port_name": "Port of Shanghai",    "congestion_score": 4.1,  "vessel_delay_hours": 18.0,   "strike_flag": False, "updated_at": now},
        {"port_id": "port-009", "port_name": "Port of Shenzhen",    "congestion_score": 3.8,  "vessel_delay_hours": 14.0,   "strike_flag": False, "updated_at": now},
        {"port_id": "port-010", "port_name": "Port of Rotterdam",   "congestion_score": 2.5,  "vessel_delay_hours": 6.0,    "strike_flag": False, "updated_at": now},
        # Baltimore bridge collapse — port closed indefinitely (77-day historical closure)
        {"port_id": "port-011", "port_name": "Port of Baltimore",   "congestion_score": 10.0, "vessel_delay_hours": 1848.0, "strike_flag": True,  "updated_at": now},
        # Alternate East Coast ports receiving diverted Baltimore traffic
        {"port_id": "port-012", "port_name": "Port of Virginia",    "congestion_score": 7.2,  "vessel_delay_hours": 48.0,   "strike_flag": False, "updated_at": now},
        {"port_id": "port-013", "port_name": "Port of Brunswick",   "congestion_score": 5.8,  "vessel_delay_hours": 24.0,   "strike_flag": False, "updated_at": now},
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
        },
        {
            "id": "evt-002",
            "source": "news_api",
            "headline": "Francis Scott Key Bridge collapses after container ship strike — Port of Baltimore closed indefinitely",
            "location_name": "Baltimore, Maryland, USA",
            "lat": 39.2837,
            "lon": -76.5817,
            "severity_raw": 9.5,
            "published_at": now,
            "inserted_at": now,
        },
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
        # Event 6: East Coast port disruption — historical anchor for Baltimore scenario
        {
            "id": "calib-006",
            "event_type": "port_disruption",
            "region": "East Coast, Maryland",
            "severity_scored": 8.8,
            "delay_days_predicted": 77,
            "supplier_recommended": "Harrisburg Auto Parts",
            "exposure_calculated": 310000.0,
            "owner_approved": True,
            "owner_override": False,
            "rejection_reason": None,
            "actual_delay_days": 77,
            "supplier_delivered": True,
            "hallucination_score": 0.05,
            "relevance_score": 0.94,
            "helpfulness_score": 0.91,
            "reasoning_score": 0.88,
            "calibration_applied": True,
            "weighted_baseline": 8.8,
            "created_at": (datetime.utcnow() - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%S"),
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
            "product_category": "auto_parts",
            "tariff_rate_percentage": 25.0,
            "effective_date": str(ten_days_ago),
            "description": "Section 301 tariff on Chinese auto parts — 25% rate, affects Guangzhou Auto Components",
            "created_at": now,
        },
        {
            "id": "tariff-002",
            "country_of_origin": "South Korea",
            "product_category": "auto_parts",
            "tariff_rate_percentage": 12.5,
            "effective_date": str(ten_days_ago),
            "description": "Automotive tariff on Korean auto parts — 12.5% rate, affects Hyundai Mobis Trade",
            "created_at": now,
        },
        {
            "id": "tariff-003",
            "country_of_origin": "South Korea",
            "product_category": "fasteners",
            "tariff_rate_percentage": 12.5,
            "effective_date": str(thirty_days_ago),
            "description": "Automotive tariff extension to fasteners — 12.5% rate",
            "created_at": now,
        },
        {
            "id": "tariff-004",
            "country_of_origin": "Mexico",
            "product_category": "auto_parts",
            "tariff_rate_percentage": 5.0,
            "effective_date": str(thirty_days_ago),
            "description": "USMCA adjustment tariff — 5% on auto parts from Mexico",
            "created_at": now,
        },
    ]
    load_rows("tariff_updates", rows)

def seed_inventory():
    """Seed inventory data by product category."""
    now = datetime.utcnow().isoformat()
    rows = [
        {"id": "inv-001", "business_id": "demo-business-001", "product_category": "auto_parts", "inventory_value_usd": 87000.0,  "updated_at": now},
        {"id": "inv-002", "business_id": "demo-business-001", "product_category": "fasteners",  "inventory_value_usd": 12500.0, "updated_at": now},
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
        {"id": "co-016", "business_id": "demo-business-001", "supplier_id": "alt-002", "order_value_usd": 8500,  "ordered_date": d(110),"expected_delivery_date": d(99), "actual_delivery_date": d(99), "delay_days": 0,  "defective_items_count": 2,  "status": "delivered"},
        # alt-004 (Monterrey Industrial MX): good but tariff risk
        {"id": "co-017", "business_id": "demo-business-001", "supplier_id": "alt-004", "order_value_usd": 11000, "ordered_date": d(130),"expected_delivery_date": d(121),"actual_delivery_date": d(121),"delay_days": 0,  "defective_items_count": 2,  "status": "delivered"},
    ]
    load_rows("completed_orders", rows)

def seed_supplier_reviews():
    """Seed supplier reviews for qualitative reliability signal."""
    now = datetime.utcnow().isoformat()
    def ts(days_ago): return (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
    rows = [
        {"id": "rev-001", "supplier_id": "sup-001", "business_id": "demo-business-001", "rating": 4.2, "review_text": "Bavarian Parts GmbH delivers quality German-engineered components. One late shipment last quarter.",  "review_date": ts(30)},
        {"id": "rev-002", "supplier_id": "sup-001", "business_id": "demo-business-001", "rating": 4.5, "review_text": "Excellent precision parts, competitive pricing from Germany.",                                      "review_date": ts(90)},
        {"id": "rev-003", "supplier_id": "sup-002", "business_id": "demo-business-001", "rating": 4.8, "review_text": "Hyundai Mobis Trade is very reliable, always on time. Highly recommended.",                          "review_date": ts(20)},
        {"id": "rev-004", "supplier_id": "sup-002", "business_id": "demo-business-001", "rating": 4.7, "review_text": "Consistent quality, fast response to issues. Korean automotive standards.",                           "review_date": ts(75)},
        {"id": "rev-005", "supplier_id": "sup-003", "business_id": "demo-business-001", "rating": 3.1, "review_text": "Guangzhou Auto Components pricing is good but delays are a regular issue.",                           "review_date": ts(40)},
        {"id": "rev-006", "supplier_id": "sup-003", "business_id": "demo-business-001", "rating": 3.5, "review_text": "Mixed experience with Guangzhou Auto. Quality control needs improvement.",                            "review_date": ts(110)},
        {"id": "rev-007", "supplier_id": "sup-006", "business_id": "demo-business-001", "rating": 4.9, "review_text": "Best fastener supplier we have worked with, zero defects.",                                           "review_date": ts(15)},
        {"id": "rev-008", "supplier_id": "sup-007", "business_id": "demo-business-001", "rating": 4.3, "review_text": "Seoul Components delivers solid quality. Lead time from Korea is a bit long.",                        "review_date": ts(60)},
        {"id": "rev-009", "supplier_id": "alt-001", "business_id": "demo-business-001", "rating": 4.7, "review_text": "Harrisburg Auto Parts is exceptional — 3-day lead time, zero delays in 2 orders.",                   "review_date": ts(45)},
        {"id": "rev-010", "supplier_id": "alt-002", "business_id": "demo-business-001", "rating": 4.4, "review_text": "Richmond Auto Supply delivered on time with minor quality note on one order.",                        "review_date": ts(70)},
        {"id": "rev-011", "supplier_id": "alt-004", "business_id": "demo-business-001", "rating": 4.4, "review_text": "Atlanta Parts Supply is cost-effective and punctual. Good domestic option.",                          "review_date": ts(80)},
    ]
    load_rows("supplier_reviews", rows)

def seed_all():
    print("🌱 Seeding BigQuery tables...\n")
    seed_business_suppliers()
    seed_pending_orders()
    seed_shipment_timetable()
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


if __name__ == "__main__":
    seed_all()
