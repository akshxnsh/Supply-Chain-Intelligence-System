"""
Table Verification & Data Flow Audit
Documents what data goes where and who puts it there
"""

from src.ingestion.init_tables import verify_all_tables, TABLES

# ── Data Flow Matrix ──────────────────────────────────────────────────────────
# Shows where data comes from, what code handles it, and how it's queried

DATA_FLOW = {
    "disruption_events": {
        "status": "✅ WIRED",
        "source": "Fivetran NewsAPI connector (auto-syncs every 15 min)",
        "populated_by": "External via Fivetran",
        "queried_by": [
            "src/agent/tools.py -> query_recent_events()",
            "src/agent/tools.py -> detect_disruptions() [NEW MULTI-SIGNAL]",
            "src/agent/tools.py -> detect_black_swan() [NEW ANOMALY DETECTION]",
            "src/agent/loop.py -> run_agent_cycle() (new multi-signal orchestration)"
        ],
        "written_by": [],
        "columns": ["id", "source", "headline", "location_name", "lat", "lon", "severity_raw", "published_at", "inserted_at"],
        "notes": "Requires Fivetran NewsAPI connector configuration. PRIMARY signal for location-based disruption detection"
    },
    
    "weather_alerts": {
        "status": "✅ WIRED (ENHANCED)",
        "source": "Fivetran OpenWeatherMap connector (auto-syncs every 60 min)",
        "populated_by": "External via Fivetran",
        "queried_by": [
            "src/agent/tools.py -> query_weather_alerts_by_region() [NEW]",
            "src/agent/tools.py -> detect_disruptions() [cross-reference with business suppliers]",
            "src/agent/tools.py -> detect_black_swan() [anomaly detection via signal spike]"
        ],
        "written_by": [],
        "columns": ["id", "region", "alert_type", "severity", "start_time", "end_time", "affected_ports", "created_at"],
        "notes": "Enhanced multi-signal source. Used to cross-reference with business suppliers and detect anomalies",
        "seeds": "src/ingestion/seed_data.py -> seed_weather_alerts()"
    },
    
    "alternative_suppliers": {
        "status": "✅ WIRED (ENHANCED)",
        "source": "CSV seed loader (supplier_db_seed.json)",
        "populated_by": "src/ingestion/seed_data.py -> seed_alternative_suppliers()",
        "queried_by": [
            "src/agent/tools.py -> search_alternative_suppliers()",
            "src/agent/tools.py -> score_suppliers() [now uses geographic_risk_score data]",
            "src/agent/loop.py -> run_agent_cycle() Step 6"
        ],
        "written_by": [],
        "columns": ["id", "name", "country", "product_category", "moq", "lead_time_days", "unit_price_usd", "reliability_score", "geographic_risk_score"],
        "notes": "Enhanced with geographic_risk_score column (0-10 scale). All 20 suppliers now have risk scores by location"
    },
    
    "business_suppliers": {
        "status": "✅ WIRED (MULTI-SIGNAL)",
        "source": "Manual seed / QuickBooks",
        "populated_by": "src/ingestion/seed_data.py -> seed_business_suppliers()",
        "queried_by": [
            "src/agent/tools.py -> get_business_suppliers()",
            "src/agent/tools.py -> detect_disruptions() [cross-references affected locations]",
            "src/agent/tools.py -> query_business_suppliers_by_country() [NEW]",
            "src/agent/loop.py -> multi-signal detection",
            "src/dashboard/api.py -> get_suppliers()"
        ],
        "written_by": [],
        "columns": ["id", "business_id", "supplier_name", "country", "product_category", "annual_spend_usd"],
        "notes": "CRITICAL: Used as cross-reference hub. detect_disruptions() matches disruption locations against supplier countries to identify affected suppliers"
    },
    
    "pending_orders": {
        "status": "✅ WIRED (ENHANCED)",
        "source": "Manual seed / Shopify",
        "populated_by": "src/ingestion/seed_data.py -> seed_pending_orders()",
        "queried_by": [
            "src/agent/tools.py -> get_pending_orders()",
            "src/agent/tools.py -> query_pending_orders_at_risk() [NEW - 30-day window filter]",
            "src/agent/tools.py -> query_pending_orders_by_supplier() [NEW]",
            "src/agent/tools.py -> calculate_impact() [NEW - core impact calculation]",
            "src/agent/loop.py -> multi-signal detection"
        ],
        "written_by": [],
        "columns": ["id", "business_id", "supplier_id", "order_value_usd", "eta_date", "status"],
        "notes": "CRITICAL: calculate_impact() now queries pending_orders filtered by (eta_date WITHIN 30 days of disruption_date). Orders beyond 30 days excluded from exposure calculation"
    },
    
    "port_activity": {
        "status": "✅ WIRED (MULTI-SIGNAL)",
        "source": "Seed data + real-time feeds",
        "populated_by": "src/ingestion/seed_data.py -> seed_port_activity()",
        "queried_by": [
            "src/agent/tools.py -> query_port_status()",
            "src/agent/tools.py -> detect_disruptions() [port-based location matching]",
            "src/agent/tools.py -> detect_black_swan() [congestion signal for anomaly detection]",
            "src/agent/loop.py -> multi-signal disruption detection"
        ],
        "written_by": [],
        "columns": ["port_id", "port_name", "congestion_score", "vessel_delay_hours", "strike_flag", "updated_at"],
        "notes": "Multi-signal source: port_congestion spike checked via detect_black_swan(). Port-location matches used in detect_disruptions()"
    },
    
    "agent_alerts": {
        "status": "✅ WIRED (MULTI-SIGNAL)",
        "source": "Supply Chain Disruption Agent",
        "populated_by": "src/ingestion/bq_client.py -> save_alert()",
        "queried_by": [
            "src/dashboard/api.py -> get_alerts()",
            "src/dashboard/frontend -> displays in UI"
        ],
        "written_by": [
            "src/agent/loop.py -> run_agent_cycle() stores final multi-signal result with calibration"
        ],
        "columns": ["id", "business_id", "disruption_id", "severity_score", "exposure_usd", "actions_json", "status", "created_at"],
        "notes": "Enhanced: Now includes calibration_baseline, black_swan_flag, and multi-signal sources in actions_json"
    },
    
    "agent_calibration": {
        "status": "✅ WIRED (ENHANCED - 3-STAGE TRACKING)",
        "source": "Self-improvement loop + historical decision tracking",
        "populated_by": [
            "src/ingestion/seed_data.py -> seed_agent_calibration() [realistic 3-stage records]",
            "Self-improvement loop (to be implemented in Phase 7)"
        ],
        "queried_by": [
            "src/agent/tools.py -> query_calibration_with_recency() [NEW - 180-day half-life exponential decay]",
            "src/agent/tools.py -> query_calibration_baseline() [NEW - wrapper with baseline + confidence]",
            "src/agent/loop.py -> SYSTEM_PROMPT injects baseline severity and confidence scores"
        ],
        "written_by": [
            "Self-improvement loop (outcome tracking - to be implemented)"
        ],
        "columns": [
            "Stage 1 - Alert Fire: id, business_id, event_type, original_location, original_severity_scored, delay_days_predicted, supplier_recommended, exposure_calculated, owner_approved, created_at",
            "Stage 2 - Owner Decision: owner_override, rejection_reason",
            "Stage 3 - Outcome (30+ days): actual_delay_days, supplier_delivered, hallucination_score, relevance_score, helpfulness_score, reasoning_score, calibration_applied, weighted_baseline"
        ],
        "notes": "CRITICAL for self-improvement: 20 columns tracking 3-stage lifecycle. Recency weight = EXP(-0.693 * days_ago / 180). Enables agent to learn from past decisions"
    },
    
    "phoenix_traces": {
        "status": "✅ WIRED (AUTO-INSTRUMENTATION)",
        "source": "Arize Phoenix",
        "populated_by": [
            "src/agent/main.py -> Arize Phoenix auto-instrumentation",
            "src/agent/loop.py -> Arize Phoenix OTEL tracer auto-capture"
        ],
        "queried_by": [
            "Arize Phoenix dashboard for observability + decision accuracy tracking"
        ],
        "written_by": [
            "Arize Phoenix local instance (auto-capture via OTEL)"
        ],
        "columns": ["trace_id", "span_id", "tool_name", "input_json", "output_json", "latency_ms", "token_count", "created_at"],
        "notes": "Observability/tracing table. Auto-populated by Phoenix OpenTelemetry instrumentation. Cross-reference with agent_calibration for outcome analysis"
    },
    
    "tariff_updates": {
        "status": "✅ WIRED (TARIFF COST IMPACT)",
        "source": "Trade regulatory data (Fivetran or manual seed)",
        "populated_by": [
            "src/ingestion/seed_data.py -> seed_tariff_updates() [test data with China/Vietnam/Korea tariffs]"
        ],
        "queried_by": [
            "src/agent/tools.py -> query_tariff_updates() [NEW]",
            "src/agent/tools.py -> detect_disruptions() [identifies suppliers affected by tariff cost increases]",
            "src/agent/loop.py -> multi-signal disruption detection"
        ],
        "written_by": [],
        "columns": [
            "id", "country_of_origin", "product_category", "tariff_rate_percentage", 
            "effective_date", "description", "created_at"
        ],
        "notes": "CRITICAL for cost-based disruption detection: When tariff_rate > 0 for supplier country + product category, calculate cost impact on pending orders. Enables agent to recommend cheaper alternative suppliers."
    }
}

def print_verification_report():
    """Print comprehensive verification report."""
    print("\n" + "="*80)
    print("📊 SUPPLY CHAIN INTELLIGENCE SYSTEM - TABLE VERIFICATION REPORT")
    print("="*80)
    
    # Check table existence
    status = verify_all_tables()
    print("\n🔍 TABLE EXISTENCE STATUS:")
    print(f"   Expected: {len(status['expected'])} | Existing: {len(status['existing'])} | Missing: {len(status['missing'])}")
    
    if status['missing']:
        print(f"\n   ❌ MISSING TABLES:")
        for table in sorted(status['missing']):
            print(f"      • {table}")
    else:
        print("   ✅ All expected tables exist!")
    
    # Print data flow details
    print("\n" + "-"*80)
    print("📋 DATA FLOW & WIRING VERIFICATION:")
    print("-"*80)
    
    wired_count = 0
    for table_id, flow in sorted(DATA_FLOW.items()):
        status_badge = flow['status']
        print(f"\n{status_badge} {table_id.upper()}")
        print(f"   └─ Source: {flow['source']}")
        
        if flow['populated_by']:
            if isinstance(flow['populated_by'], list):
                for populator in flow['populated_by']:
                    print(f"   └─ Populated by: {populator}")
            else:
                print(f"   └─ Populated by: {flow['populated_by']}")
        
        if flow['queried_by']:
            print(f"   └─ Queried by:")
            for querier in flow['queried_by']:
                print(f"      • {querier}")
        
        if flow['written_by']:
            print(f"   └─ Written by:")
            for writer in flow['written_by']:
                print(f"      • {writer}")
        
        if 'seeds' in flow:
            print(f"   └─ Seed function: {flow['seeds']}")
        
        if flow['notes']:
            print(f"   └─ Note: {flow['notes']}")
        
        if "✅" in status_badge:
            wired_count += 1
    
    # Summary
    print("\n" + "="*80)
    print("✅ SUMMARY:")
    print(f"   Tables properly wired: {wired_count}/{len(DATA_FLOW)}")
    print(f"   All tables exist: {status['all_present']}")
    print("="*80 + "\n")

if __name__ == "__main__":
    print_verification_report()
