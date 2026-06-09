"""
Table Verification & Data Flow Audit.

Documents what data goes where and which code paths read/write each table.
"""

from src.ingestion.init_tables import verify_all_tables


DATA_FLOW = {
    "disruption_events": {
        "status": "WIRED",
        "source": "Fivetran NewsAPI connector",
        "populated_by": "External via Fivetran",
        "queried_by": [
            "src.ingestion.bq_client.query_recent_events",
            "src.detection.disruption_detector.detect_disruptions",
            "src.agent.tools.detect_black_swan",
        ],
        "written_by": [],
        "columns": [
            "id", "source", "headline", "location_name", "lat", "lon",
            "severity_raw", "published_at", "inserted_at",
        ],
        "notes": "Primary external signal for location-based disruption detection.",
    },
    "weather_alerts": {
        "status": "WIRED",
        "source": "Fivetran OpenWeatherMap connector / seed data",
        "populated_by": "External via Fivetran or src.ingestion.seed_data.seed_weather_alerts",
        "queried_by": [
            "src.ingestion.bq_client.query_recent_weather_alerts",
            "src.detection.disruption_detector.detect_disruptions",
            "src.agent.tools.detect_black_swan",
        ],
        "written_by": [],
        "columns": [
            "id", "region", "alert_type", "severity", "start_time",
            "end_time", "affected_ports", "created_at",
        ],
        "notes": "Used to match weather disruptions against active shipment ports.",
    },
    "alternative_suppliers": {
        "status": "WIRED",
        "source": "CSV/manual seed data",
        "populated_by": "src.ingestion.seed_data.seed_alternative_suppliers",
        "queried_by": [
            "src.ingestion.bq_client.query_alternative_suppliers",
            "src.agent.tools.search_alternative_suppliers",
            "src.suppliers.scorer.score_suppliers",
        ],
        "written_by": [],
        "columns": [
            "id", "name", "country", "product_category", "moq",
            "lead_time_days", "unit_price_usd", "reliability_score",
            "geographic_risk_score",
        ],
        "notes": "Candidate supplier pool for mitigation purchase orders.",
    },
    "business_suppliers": {
        "status": "WIRED",
        "source": "Manual seed / ERP / QuickBooks",
        "populated_by": "src.ingestion.seed_data.seed_business_suppliers and seed_business_002",
        "queried_by": [
            "src.ingestion.bq_client.query_business_suppliers",
            "src.detection.disruption_detector.detect_disruptions",
            "src.dashboard.api.get_suppliers",
        ],
        "written_by": [],
        "columns": [
            "id", "business_id", "supplier_name", "country",
            "product_category", "annual_spend_usd",
        ],
        "notes": "Supplier relationship hub for disruption matching.",
    },
    "pending_orders": {
        "status": "WIRED",
        "source": "Shopify / CRM / manual seed",
        "populated_by": "src.ingestion.seed_data.seed_pending_orders and seed_business_002",
        "queried_by": [
            "src.ingestion.bq_client.query_pending_orders",
            "src.agent.tools.get_pending_orders",
            "src.exposure.calculator.calculate_impact",
        ],
        "written_by": [],
        "columns": [
            "id", "business_id", "client_id", "product_category",
            "quantity", "order_value_usd", "required_by_date", "status",
        ],
        "notes": "Demand-side table: client/customer orders the business must fulfill. It is intentionally not supplier-linked.",
    },
    "shipment_timetable": {
        "status": "WIRED",
        "source": "ERP / freight tracker / manual seed",
        "populated_by": "src.ingestion.seed_data.seed_shipment_timetable and seed_business_002",
        "queried_by": [
            "src.ingestion.bq_client.query_supplier_timetable",
            "src.ingestion.bq_client.query_shipments_at_risk",
            "src.prediction.utils.fetch_shipment_schedule",
            "src.detection.disruption_detector.detect_disruptions",
            "src.exposure.calculator.calculate_impact",
        ],
        "written_by": [],
        "columns": [
            "id", "business_id", "supplier_id", "product_category",
            "quantity", "shipment_value_usd", "origin_port",
            "destination_port", "dispatched_date", "expected_arrival_date",
            "status",
        ],
        "notes": "Supply-side table: inbound supplier shipments used for supplier disruption exposure and port/weather matching.",
    },
    "port_activity": {
        "status": "WIRED",
        "source": "Port data feed / seed data",
        "populated_by": "src.ingestion.seed_data.seed_port_activity",
        "queried_by": [
            "src.ingestion.bq_client.query_port_status",
            "src.detection.disruption_detector.detect_disruptions",
            "src.agent.tools.detect_black_swan",
        ],
        "written_by": [],
        "columns": [
            "port_id", "port_name", "congestion_score",
            "vessel_delay_hours", "strike_flag", "updated_at",
        ],
        "notes": "Used for port strike/congestion signal matching.",
    },
    "tariff_updates": {
        "status": "WIRED",
        "source": "Trade regulatory feed / manual seed",
        "populated_by": "src.ingestion.seed_data.seed_tariff_updates",
        "queried_by": [
            "src.ingestion.bq_client.query_tariff_updates",
            "src.detection.disruption_detector.detect_disruptions",
        ],
        "written_by": [],
        "columns": [
            "id", "country_of_origin", "product_category",
            "tariff_rate_percentage", "effective_date", "description",
            "created_at",
        ],
        "notes": "Tariff cost is calculated against inbound shipment value, not client orders.",
    },
    "inventory": {
        "status": "WIRED",
        "source": "ERP / WMS / manual seed",
        "populated_by": "src.ingestion.seed_data.seed_inventory and seed_business_002",
        "queried_by": [
            "src.ingestion.bq_client.query_inventory",
            "src.agent.tools.get_inventory",
            "src.exposure.calculator.calculate_impact",
        ],
        "written_by": [],
        "columns": [
            "id", "business_id", "product_category",
            "inventory_value_usd", "updated_at",
        ],
        "notes": "Inventory is the buffer that reduces impact when it covers pending client demand.",
    },
    "agent_alerts": {
        "status": "WIRED",
        "source": "Supply Chain Intelligence Agent",
        "populated_by": "src.ingestion.bq_client.save_alert",
        "queried_by": [
            "src.dashboard.api.get_alerts",
            "src.dashboard.api.get_all_alerts",
        ],
        "written_by": [
            "src.agent.tools.save_alert_record",
            "src.agent.runtime._persist_alert_if_new",
        ],
        "columns": [
            "id", "business_id", "disruption_id", "severity_score",
            "exposure_usd", "actions_json", "status", "created_at",
        ],
        "notes": "Agent-generated alerts displayed in the dashboard.",
    },
    "agent_calibration": {
        "status": "WIRED",
        "source": "Historical recommendation outcomes",
        "populated_by": "src.ingestion.seed_data.seed_agent_calibration",
        "queried_by": [
            "src.ingestion.bq_client.query_calibration_with_recency",
            "src.agent.tools.query_calibration_baseline",
        ],
        "written_by": [
            "src.ingestion.bq_client.save_calibration_approval",
            "src.ingestion.bq_client.update_calibration_outcomes",
        ],
        "columns": [
            "id", "event_type", "region", "severity_scored",
            "delay_days_predicted", "supplier_recommended",
            "exposure_calculated", "owner_approved", "owner_override",
            "rejection_reason", "actual_delay_days", "supplier_delivered",
            "hallucination_score", "relevance_score", "helpfulness_score",
            "reasoning_score", "calibration_applied", "weighted_baseline",
            "created_at",
        ],
        "notes": "Used to calibrate future recommendation confidence.",
    },
    "phoenix_traces": {
        "status": "WIRED",
        "source": "Arize Phoenix / OpenTelemetry",
        "populated_by": "Phoenix instrumentation",
        "queried_by": ["Phoenix dashboard"],
        "written_by": ["Phoenix instrumentation"],
        "columns": [
            "trace_id", "span_id", "tool_name", "input_json",
            "output_json", "latency_ms", "token_count", "created_at",
        ],
        "notes": "Observability table for agent/model/tool traces.",
    },
    "completed_orders": {
        "status": "WIRED",
        "source": "Order management history / manual seed",
        "populated_by": "src.ingestion.seed_data.seed_completed_orders",
        "queried_by": [
            "src.ingestion.bq_client.query_completed_orders_by_suppliers",
            "src.suppliers.scorer.score_suppliers",
        ],
        "written_by": [],
        "columns": [
            "id", "business_id", "supplier_id", "order_value_usd",
            "ordered_date", "expected_delivery_date", "actual_delivery_date",
            "delay_days", "defective_items_count", "status",
        ],
        "notes": "Historical supply-side orders used for supplier reliability scoring.",
    },
    "supplier_reviews": {
        "status": "WIRED",
        "source": "Owner/ERP review history / manual seed",
        "populated_by": "src.ingestion.seed_data.seed_supplier_reviews",
        "queried_by": [
            "src.ingestion.bq_client.query_supplier_reviews_by_suppliers",
            "src.suppliers.scorer.score_suppliers",
        ],
        "written_by": [],
        "columns": [
            "id", "supplier_id", "business_id", "rating",
            "review_text", "review_date",
        ],
        "notes": "Qualitative supplier reliability signal.",
    },
}


def print_verification_report():
    """Print a comprehensive verification report."""
    print("\n" + "=" * 80)
    print("SUPPLY CHAIN INTELLIGENCE SYSTEM - TABLE VERIFICATION REPORT")
    print("=" * 80)

    status = verify_all_tables()
    print("\nTABLE EXISTENCE STATUS:")
    print(
        f"   Expected: {len(status['expected'])} | "
        f"Existing: {len(status['existing'])} | "
        f"Missing: {len(status['missing'])}"
    )

    if status["missing"]:
        print("\n   MISSING TABLES:")
        for table in sorted(status["missing"]):
            print(f"      - {table}")
    else:
        print("   All expected tables exist.")

    print("\n" + "-" * 80)
    print("DATA FLOW & WIRING VERIFICATION:")
    print("-" * 80)

    for table_id, flow in sorted(DATA_FLOW.items()):
        print(f"\n{flow['status']} {table_id.upper()}")
        print(f"   Source: {flow['source']}")

        populated_by = flow["populated_by"]
        if isinstance(populated_by, list):
            for populator in populated_by:
                print(f"   Populated by: {populator}")
        else:
            print(f"   Populated by: {populated_by}")

        if flow["queried_by"]:
            print("   Queried by:")
            for querier in flow["queried_by"]:
                print(f"      - {querier}")

        if flow["written_by"]:
            print("   Written by:")
            for writer in flow["written_by"]:
                print(f"      - {writer}")

        print(f"   Columns: {', '.join(flow['columns'])}")
        print(f"   Note: {flow['notes']}")

    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(f"   Tables documented: {len(DATA_FLOW)}")
    print(f"   All expected tables exist: {status['all_present']}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    print_verification_report()
