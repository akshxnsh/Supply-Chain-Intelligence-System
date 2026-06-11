"""
Seed BigQuery with a HEALTHY pre-incident baseline for demo-business-001
(Mid-Atlantic Auto Parts Distribution LLC).

This represents the world BEFORE the Francis Scott Key Bridge collapse:
  - Ports healthy (Port of Baltimore congestion ~2.5, no strikes anywhere)
  - No Baltimore disruption event in the feed
  - Inventory comfortably covers pending client demand
  - Shipments in_transit on their normal routes (no rerouting story yet)
  - Tariffs present but on origin/category pairs that match NO active supplier,
    so the disruption detector flags zero suppliers

A simulation run against this state produces:
    { "alert_fired": false, "black_swan_detected": false,
      "exposure_usd": 0, "affected_suppliers": [] }

WHY this guarantees "no alert": calculate_impact() short-circuits to exposure 0
when affected_supplier_ids is empty, and the root agent only fires an alert when
at least one shipment is affected. detect_disruptions() flags a supplier only via
(a) a port with congestion > 5.0 or a strike, (b) a weather alert on a current/
upcoming route checkpoint, (c) a news headline mentioning a current/upcoming route
checkpoint, (d) a disruption event whose country matches a supplier, or (e) a tariff
whose (country, product) matches a supplier. The baseline below satisfies NONE of
these, so affected_suppliers == [].

THE INCIDENT DATASET lives in src/ingestion/seed_data.py. It is delivered to
BigQuery later by the FreshnessAgent (Fivetran connector sync -> Neon Postgres
google_sheets schema -> sync_postgres_to_bigquery, which WRITE_TRUNCATE-replaces
each table). Because every baseline auto_parts shipment is destined for Port of
Baltimore, a refresh of disruption_events ALONE is sufficient to flip the scenario:
the Baltimore headline then matches the upcoming "Port of Baltimore" checkpoint on
those shipments and the alert fires. Refreshing port_activity / shipment_timetable /
tariff_updates completes the full incident picture (congestion 10.0, 1848h delay,
reroutes, exposure figures). For a deterministic demo, drive the transition with the
FreshnessAgent's direct sync tool (sync_postgres_table_to_bigquery), which bypasses
the staleness gate; the staleness-gated path (refresh_all_stale_tables) instead waits
out each table's freshness window (30–60 min for the signal tables).
"""

from datetime import datetime, timedelta

from src.ingestion.seed_data import (
    load_rows,
    seed_business_suppliers,
    seed_pending_orders,
    seed_alternative_suppliers,
    seed_completed_orders,
    seed_supplier_reviews,
    seed_agent_calibration,
)


def _shipment_row(
    shipment_id,
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
        "business_id": "demo-business-001",
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


def seed_shipment_timetable_baseline():
    """Active inbound shipments on NORMAL routes — all in_transit, none blocked.

    Auto-parts shipments are destined for Port of Baltimore (the business's
    primary port), which is HEALTHY in the baseline. No rerouting story yet.
    """
    today = datetime.utcnow()
    rows = [
        # auto_parts — international suppliers inbound to the primary port (healthy)
        _shipment_row("shp-001", "sup-001", "auto_parts", 4550, 182000, "Port of Hamburg",   "Port of Baltimore", today - timedelta(days=12), today + timedelta(days=7),  "Port of Hamburg > English Channel > Atlantic Crossing > Port of Baltimore"),
        _shipment_row("shp-002", "sup-002", "auto_parts", 3200, 128000, "Port of Busan",     "Port of Baltimore", today - timedelta(days=14), today + timedelta(days=5),  "Port of Busan > Pacific Crossing > Port of Los Angeles > Port of Baltimore"),
        _shipment_row("shp-003", "sup-003", "auto_parts", 1700,  68000, "Port of Shanghai",  "Port of Baltimore", today - timedelta(days=18), today + timedelta(days=9),  "Port of Shanghai > Singapore Strait > Pacific Crossing > Port of Los Angeles > Port of Baltimore"),
        _shipment_row("shp-005", "sup-005", "auto_parts", 2800, 112000, "Port of Montreal",  "Port of Baltimore", today - timedelta(days=5),  today + timedelta(days=8),  "Port of Montreal > Atlantic Coast > Port of Baltimore"),
        # fasteners — domestic + international inbound to the primary port (healthy)
        _shipment_row("shp-006", "sup-006", "fasteners",  7000,   8400, "Port of Houston",   "Port of Baltimore", today - timedelta(days=1),  today + timedelta(days=7),  "Port of Houston > Memphis Rail Hub > Port of Baltimore"),
        _shipment_row("shp-007", "sup-007", "fasteners",  5565,   6200, "Port of Busan",     "Port of Baltimore", today - timedelta(days=3),  today + timedelta(days=9),  "Port of Busan > Pacific Crossing > Port of Los Angeles > Port of Baltimore"),
    ]
    load_rows("shipment_timetable", rows)


def seed_port_activity_baseline():
    """Every port healthy: congestion < 5.0, no strikes. Port of Baltimore normal."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        {"port_id": "port-001", "port_name": "Port of Houston",     "congestion_score": 3.0, "vessel_delay_hours": 8.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-002", "port_name": "Port of Los Angeles", "congestion_score": 3.2, "vessel_delay_hours": 12.0, "strike_flag": False, "updated_at": now},
        {"port_id": "port-003", "port_name": "Port of Long Beach",  "congestion_score": 2.8, "vessel_delay_hours": 8.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-004", "port_name": "Port of Seattle",     "congestion_score": 2.1, "vessel_delay_hours": 4.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-005", "port_name": "Port of New York",    "congestion_score": 3.1, "vessel_delay_hours": 9.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-006", "port_name": "Port of Savannah",    "congestion_score": 2.9, "vessel_delay_hours": 6.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-008", "port_name": "Port of Shanghai",    "congestion_score": 4.1, "vessel_delay_hours": 18.0, "strike_flag": False, "updated_at": now},
        {"port_id": "port-010", "port_name": "Port of Rotterdam",   "congestion_score": 2.5, "vessel_delay_hours": 6.0,  "strike_flag": False, "updated_at": now},
        # Primary port — healthy in the pre-incident baseline
        {"port_id": "port-011", "port_name": "Port of Baltimore",   "congestion_score": 2.5, "vessel_delay_hours": 6.0,  "strike_flag": False, "updated_at": now},
        {"port_id": "port-012", "port_name": "Port of Virginia",    "congestion_score": 2.8, "vessel_delay_hours": 8.0,  "strike_flag": False, "updated_at": now},
    ]
    load_rows("port_activity", rows)


def seed_disruption_events_baseline():
    """A single inert background event so the feed is live but flags nobody.

    Location country (Netherlands) matches no supplier; the headline names no
    checkpoint on any active route, so neither the macro-country path nor the
    news_port path fires.
    """
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        {
            "id": "evt-baseline-001",
            "source": "news_api",
            "headline": "Routine maintenance completed at Port of Rotterdam ahead of schedule",
            "location_name": "Rotterdam, Netherlands",
            "lat": 51.9244,
            "lon": 4.4777,
            "severity_raw": 2.0,
            "published_at": now,
            "inserted_at": now,
        },
    ]
    load_rows("disruption_events", rows)


def seed_weather_alerts_baseline():
    """A single low-severity weather advisory affecting ports off every active route."""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    rows = [
        {
            "id": "weather-baseline-001",
            "region": "Southeast Asia",
            "alert_type": "Light Rain Advisory",
            "severity": 3.0,
            "start_time": now,
            "end_time": (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
            "affected_ports": "Port of Singapore, Port of Hong Kong",
            "created_at": now,
        },
    ]
    load_rows("weather_alerts", rows)


def seed_tariff_updates_baseline():
    """Tariffs present but on origin/category pairs that match NO active supplier.

    Active supplier (country, product) pairs are: (Germany|South Korea|China|USA|
    Canada, auto_parts) and (USA|South Korea|India, fasteners). None of the rows
    below match, so detect_disruptions() adds zero tariff signals.
    """
    now = datetime.utcnow().isoformat()
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).date()
    ten_days_ago = (datetime.utcnow() - timedelta(days=10)).date()
    rows = [
        {"id": "tariff-001", "country_of_origin": "Mexico",  "product_category": "auto_parts", "tariff_rate_percentage": 5.0, "effective_date": str(ten_days_ago),    "description": "USMCA adjustment — 5% on auto parts from Mexico (no active Mexican supplier)", "created_at": now},
        {"id": "tariff-002", "country_of_origin": "Vietnam", "product_category": "fasteners",  "tariff_rate_percentage": 3.0, "effective_date": str(thirty_days_ago), "description": "Trade adjustment — 3% on fasteners from Vietnam (no active Vietnamese supplier)", "created_at": now},
        {"id": "tariff-003", "country_of_origin": "Brazil",  "product_category": "auto_parts", "tariff_rate_percentage": 4.0, "effective_date": str(thirty_days_ago), "description": "Trade adjustment — 4% on auto parts from Brazil (no active Brazilian supplier)", "created_at": now},
    ]
    load_rows("tariff_updates", rows)


def seed_inventory_baseline():
    """Healthy on-hand stock that comfortably covers all pending client demand.

    Baseline pending demand: auto_parts $202,200, fasteners $6,000.
    """
    now = datetime.utcnow().isoformat()
    rows = [
        {"id": "inv-001", "business_id": "demo-business-001", "product_category": "auto_parts", "inventory_value_usd": 250000.0, "updated_at": now},
        {"id": "inv-002", "business_id": "demo-business-001", "product_category": "fasteners",  "inventory_value_usd": 20000.0,  "updated_at": now},
    ]
    load_rows("inventory", rows)


def seed_baseline():
    print("🌱 Seeding HEALTHY baseline (pre-incident) into BigQuery...\n")
    # Unchanged structural / historical tables — reused from the incident seeder.
    seed_business_suppliers()
    seed_pending_orders()
    seed_alternative_suppliers()
    seed_completed_orders()
    seed_supplier_reviews()
    seed_agent_calibration()
    # Healthy overrides for the signal / operational tables.
    seed_shipment_timetable_baseline()
    seed_port_activity_baseline()
    seed_disruption_events_baseline()
    seed_weather_alerts_baseline()
    seed_tariff_updates_baseline()
    seed_inventory_baseline()
    print("\n✅ BASELINE LOADED — BigQuery healthy, no Baltimore incident. Expect alert_fired = false.")


if __name__ == "__main__":
    seed_baseline()
