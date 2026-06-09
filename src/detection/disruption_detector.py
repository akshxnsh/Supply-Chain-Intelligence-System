from datetime import datetime, timedelta, timezone
import json
from typing import Dict, Any
from src.ingestion.bq_client import (
    query_recent_events,
    query_business_suppliers,
    query_recent_weather_alerts,
    query_port_status,
    query_tariff_updates,
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
    tariffs = query_tariff_updates(days_back=30)  # New tariffs

    # Load active shipments up front: needed both for location-based checks and to
    # scope the port-status query to only the ports this business actually touches.
    from src.prediction.utils import (
        affected_weather_checkpoints,
        checkpoint_is_current_or_upcoming,
        extract_matching_route_checkpoints,
        fetch_shipment_schedule,
        match_news_to_shipment,
        split_route,
    )
    shipments = fetch_shipment_schedule(business_id)

    # Only query port activity for the origin/destination ports on active shipments,
    # rather than scanning the entire port_activity table.
    relevant_ports = set()
    for sh in shipments:
        for key in ("origin_port", "destination_port"):
            pn = sh.get(key)
            if pn and pn != "Domestic":
                relevant_ports.add(pn)
        for checkpoint in split_route(sh.get("route") or ""):
            if checkpoint and checkpoint != "Domestic":
                relevant_ports.add(checkpoint)
    port_data = []
    for pn in relevant_ports:
        port_data.extend(query_port_status(pn))
    
    # ── Create lookup maps for fast matching ──────────────────────────────────
    affected_by_location = {}  # country → list of disruption signals
    affected_by_weather = {}   # region → list of weather signals
    affected_by_port = {}      # country/port → list of port signals
    affected_by_tariff = {}    # (country, product) → tariff info
    
    # Parse disruption events by country (keep for macro‑level news)
    for d in disruptions:
        location_name = d.get("location_name", "").lower()
        country_hint = location_name.split(",")[-1].strip().lower() if location_name else ""
        if country_hint:
            affected_by_location.setdefault(country_hint, []).append({
                "type": "disruption_event",
                "headline": d.get("headline", "Unknown"),
                "location_name": d.get("location_name", ""),
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

    # Build a map of supplier_id -> supplier info for quick lookup
    supplier_map = {s["id"]: s for s in business_supp}

    # Prepare a dict to accumulate signals per supplier
    supplier_signals: Dict[str, Dict[str, Any]] = {}

    now = datetime.now(timezone.utc)

    # ---------------------------------------------------------------------
    # 1. Process each active shipment for weather/port/news signals
    # ---------------------------------------------------------------------
    for shipment in shipments:
        supp_id = shipment.get("supplier_id")
        supp = supplier_map.get(supp_id)
        if not supp:
            continue
        supp_country = supp.get("country", "").lower()
        supp_product = supp.get("product_category", "").lower()
        # Initialise entry if not present
        if supp_id not in supplier_signals:
            supplier_signals[supp_id] = {
                "supplier_id": supp_id,
                "supplier_name": supp.get("supplier_name"),
                "country": supp_country,
                "product_category": supp_product,
                "signals": set(),
                "signal_details": [],
                "tariff_cost_impact_usd": 0.0,
            }
        entry = supplier_signals[supp_id]

        # Weather check: only current/upcoming route checkpoints should fire.
        weather_hits = []
        for weather in weather_alerts:
            for checkpoint in affected_weather_checkpoints(weather):
                if checkpoint_is_current_or_upcoming(checkpoint, shipment, now):
                    weather_hits.append(checkpoint)
        if weather_hits:
            entry["signals"].add("weather_alert")
            entry["signal_details"].append(
                f"Weather alert affecting route checkpoint(s): {', '.join(sorted(set(weather_hits)))}"
            )

        # Port activity check: suppress disruptions at checkpoints already passed.
        port_hits = []
        for port in port_data:
            if not (port.get("strike_flag") or port.get("congestion_score", 0) > 5.0):
                continue
            port_name = port.get("port_name", "")
            if checkpoint_is_current_or_upcoming(port_name, shipment, now):
                port_hits.append(port_name)
        if port_hits:
            entry["signals"].add("port_activity")
            entry["signal_details"].append(
                f"Port activity affecting route checkpoint(s): {', '.join(sorted(set(port_hits)))}"
            )

        # News check – only flag when headline mentions the current port and the port is affected
        for news_item in disruptions:
            if match_news_to_shipment(news_item, shipment, now, weather_alerts, port_data):
                entry["signals"].add("news_port")
                entry["signal_details"].append(f"News: {news_item.get('headline', '')}")

    # ---------------------------------------------------------------------
    # 2. Macro‑level news (country‑based) – keep existing behaviour
    # ---------------------------------------------------------------------
    shipments_by_supplier: Dict[str, list] = {}
    for shipment in shipments:
        shipments_by_supplier.setdefault(shipment.get("supplier_id"), []).append(shipment)

    for supp in business_supp:
        supp_id = supp.get("id")
        supp_country = supp.get("country", "").lower()
        if supp_country in affected_by_location:
            active_signals = []
            for sig in affected_by_location[supp_country]:
                signal_text = f"{sig.get('headline', '')} {sig.get('location_name', '')}"
                for shipment in shipments_by_supplier.get(supp_id, []):
                    route_mentions = extract_matching_route_checkpoints(signal_text, shipment)
                    if route_mentions:
                        if any(
                            checkpoint_is_current_or_upcoming(checkpoint, shipment, now)
                            for checkpoint in route_mentions
                        ):
                            active_signals.append(sig)
                        continue
                    active_signals.append(sig)
            if not active_signals:
                continue
            entry = supplier_signals.setdefault(supp_id, {
                "supplier_id": supp_id,
                "supplier_name": supp.get("supplier_name"),
                "country": supp_country,
                "product_category": supp.get("product_category", "").lower(),
                "signals": set(),
                "signal_details": [],
                "tariff_cost_impact_usd": 0.0,
            })
            entry["signals"].add("disruption_event")
            for sig in active_signals:
                entry["signal_details"].append(f"{sig['headline']} (severity: {sig['severity']})")

    # ---------------------------------------------------------------------
    # 3. Tariff impact
    # ---------------------------------------------------------------------
    # Tariffs affect supplier-side supply cost. Use inbound shipments, not
    # pending client orders, because pending_orders is demand-side data.
    for supp in business_supp:
        supp_id = supp.get("id")
        supp_country = supp.get("country", "").lower()
        supp_product = supp.get("product_category", "").lower()
        tariff_key = (supp_country, supp_product)
        if tariff_key in affected_by_tariff:
            entry = supplier_signals.setdefault(supp_id, {
                "supplier_id": supp_id,
                "supplier_name": supp.get("supplier_name"),
                "country": supp_country,
                "product_category": supp_product,
                "signals": set(),
                "signal_details": [],
                "tariff_cost_impact_usd": 0.0,
            })
            tariff_info = affected_by_tariff[tariff_key]
            entry["signals"].add("tariff_update")
            tariff_rate = tariff_info["tariff_rate"]
            cost_impact = 0.0
            for shipment in shipments_by_supplier.get(supp_id, []):
                shipment_value = shipment.get("shipment_value_usd", 0)
                cost_impact += shipment_value * (tariff_rate / 100)
            entry["tariff_cost_impact_usd"] = round(cost_impact, 2)
            entry["signal_details"].append(
                f"Tariff +{tariff_rate}% effective {tariff_info['effective_date']} (est. +${cost_impact:.2f} inbound shipment cost)"
            )

    # ---------------------------------------------------------------------
    # Build final list
    # ---------------------------------------------------------------------
    for entry in supplier_signals.values():
        if entry["signals"]:
            affected_suppliers.append({
                "supplier_id": entry["supplier_id"],
                "supplier_name": entry["supplier_name"],
                "country": entry["country"],
                "product_category": entry["product_category"],
                "signals": list(entry["signals"]),
                "signal_details": entry["signal_details"],
                "tariff_cost_impact_usd": entry["tariff_cost_impact_usd"],
                "total_signals_count": len(entry["signals"]),
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
