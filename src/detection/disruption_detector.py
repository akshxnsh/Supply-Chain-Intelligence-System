from datetime import datetime, timedelta
import json
from src.ingestion.bq_client import (
    query_recent_events,
    query_business_suppliers,
    query_recent_weather_alerts,
    query_port_status,
    query_tariff_updates,
    query_pending_orders_by_supplier,
)

def detect_disruptions(business_id: str = "demo-business-001") -> str:
    """
    MULTI-SIGNAL MASTER DISRUPTION DETECTION: Cross-reference ALL signal layers.
    
    Signals analyzed:
    1. Disruption Events (news, geopolitical, infrastructure)
    2. Weather Alerts (hurricanes, storms, extreme conditions)
    3. Port Activity (congestion, strikes, delays)
    4. Tariff Updates (cost increases affecting supplier economics)
    
    Cross-references each signal against business_suppliers to identify:
    - Suppliers affected by location-based disruptions
    - Suppliers affected by weather in their region
    - Suppliers shipping through affected ports
    - Suppliers whose costs increase due to new tariffs
    
    Returns: affected_suppliers with signal sources and financial impact.
    """
    # ── Fetch all signal sources ──────────────────────────────────────────────
    disruptions = query_recent_events(hours=24)  # News + events
    business_supp = query_business_suppliers(business_id=business_id)
    weather_alerts = query_recent_weather_alerts(hours=48)  # Weather warnings
    port_data = query_port_status()  # Port congestion + strikes
    tariffs = query_tariff_updates(days_back=30)  # New tariffs
    
    # ── Create lookup maps for fast matching ──────────────────────────────────
    affected_by_location = {}  # country → list of disruption signals
    affected_by_weather = {}   # region → list of weather signals
    affected_by_port = {}      # country/port → list of port signals
    affected_by_tariff = {}    # (country, product) → tariff info
    
    # Parse disruption events by country
    for d in disruptions:
        location_name = d.get("location_name", "").lower()
        country_hint = location_name.split(",")[-1].strip().lower() if location_name else ""
        if country_hint:
            if country_hint not in affected_by_location:
                affected_by_location[country_hint] = []
            affected_by_location[country_hint].append({
                "type": "disruption_event",
                "headline": d.get("headline", "Unknown"),
                "severity": d.get("severity_raw", 5.0)
            })
    
    # Parse weather alerts by region
    for w in weather_alerts:
        region = w.get("region", "").lower()
        if region:
            if region not in affected_by_weather:
                affected_by_weather[region] = []
            affected_by_weather[region].append({
                "type": "weather_alert",
                "alert_type": w.get("alert_type", "Unknown"),
                "severity": w.get("severity", 5.0),
                "affected_ports": w.get("affected_ports", "")
            })
    
    # Parse port activity (strikes, congestion)
    for p in port_data:
        port_name = p.get("port_name", "").lower()
        strike_flag = p.get("strike_flag", False)
        congestion = p.get("congestion_score", 0)
        if strike_flag or congestion > 5.0:  # Strike or high congestion
            if port_name not in affected_by_port:
                affected_by_port[port_name] = []
            affected_by_port[port_name].append({
                "type": "port_activity",
                "strike_flag": strike_flag,
                "congestion_score": congestion,
                "delay_hours": p.get("vessel_delay_hours", 0)
            })
    
    # Parse tariff updates by country + product category
    for t in tariffs:
        country = t.get("country_of_origin", "").lower()
        product_cat = t.get("product_category", "").lower()
        key = (country, product_cat)
        affected_by_tariff[key] = {
            "type": "tariff_update",
            "tariff_rate": t.get("tariff_rate_percentage", 0),
            "effective_date": t.get("effective_date", ""),
            "description": t.get("description", "")
        }
    
    # ── Cross-reference all signals against business suppliers ────────────────
    affected_suppliers = []
    
    for supp in business_supp:
        supp_id = supp.get("id")
        supp_name = supp.get("supplier_name")
        supp_country = supp.get("country", "").lower()
        supp_product = supp.get("product_category", "").lower()
        
        signals_hit = []
        signal_details = []
        cost_impact_usd = 0
        
        # Check 1: Location-based disruption (news, geopolitical)
        if supp_country in affected_by_location:
            for sig in affected_by_location[supp_country]:
                signals_hit.append("disruption_event")
                signal_details.append(f"{sig['headline']} (severity: {sig['severity']})")
        
        # Check 2: Weather alert in supplier region
        if supp_country in affected_by_weather:
            for sig in affected_by_weather[supp_country]:
                signals_hit.append("weather_alert")
                signal_details.append(f"{sig['alert_type']} alert (severity: {sig['severity']})")
        
        # Check 3: Port where supplier ships from
        for port_name, port_sigs in affected_by_port.items():
            for sig in port_sigs:
                if sig["strike_flag"] or sig["congestion_score"] > 5.0:
                    signals_hit.append("port_activity")
                    port_signal = "Strike" if sig["strike_flag"] else f"Congestion {sig['congestion_score']}"
                    signal_details.append(f"Port {port_name}: {port_signal} ({sig['delay_hours']}hrs delay)")
        
        # Check 4: Tariff increases affecting supplier costs
        tariff_key = (supp_country, supp_product)
        if tariff_key in affected_by_tariff:
            tariff_info = affected_by_tariff[tariff_key]
            signals_hit.append("tariff_update")
            tariff_rate = tariff_info["tariff_rate"]
            
            # Calculate cost impact on pending orders from this supplier
            pending = query_pending_orders_by_supplier(business_id, supp_id)
            for order in pending:
                order_value = order.get("order_value_usd", 0)
                cost_increase = order_value * (tariff_rate / 100)
                cost_impact_usd += cost_increase
            
            signal_details.append(f"Tariff +{tariff_rate}% effective {tariff_info['effective_date']} (est. +${cost_impact_usd:.2f} cost)")
        
        # Only add supplier if at least one signal triggered
        if signals_hit:
            affected_suppliers.append({
                "supplier_id": supp_id,
                "supplier_name": supp_name,
                "country": supp_country,
                "product_category": supp_product,
                "signals": list(set(signals_hit)),  # Unique signal types
                "signal_details": signal_details,
                "tariff_cost_impact_usd": round(cost_impact_usd, 2),
                "total_signals_count": len(signals_hit)
            })
    
    return json.dumps({
        "affected_suppliers": affected_suppliers,
        "total_affected": len(affected_suppliers),
        "total_cost_impact_usd": round(sum(s["tariff_cost_impact_usd"] for s in affected_suppliers), 2),
        "signals_analyzed": {
            "disruption_events": len(disruptions),
            "weather_alerts": len(weather_alerts),
            "port_activity": len([p for p in port_data if p.get("strike_flag") or p.get("congestion_score", 0) > 5.0]),
            "tariff_updates": len(tariffs)
        }
    }, default=str)