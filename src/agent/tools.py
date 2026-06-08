from google.genai import types
from src.ingestion.bq_client import (
    query_recent_events,
    query_business_suppliers,
    query_pending_orders,
    query_alternative_suppliers,
    query_port_status,
    query_calibration_with_recency,
    query_pending_orders_at_risk,
    query_pending_orders_by_supplier,
    query_business_suppliers_by_country,
    query_weather_alerts_by_region,
    query_recent_weather_alerts,
    query_tariff_updates,
    query_inventory,
    query_completed_orders_by_supplier,
    query_supplier_reviews,
)
import json

# ── Tool Handler Functions ────────────────────────────────────────────────────

def get_recent_disruptions(hours: int = 24) -> str:
    results = query_recent_events(hours=hours)
    return json.dumps(results, default=str)

def get_business_suppliers(business_id: str) -> str:
    results = query_business_suppliers(business_id=business_id)
    return json.dumps(results, default=str)

def get_pending_orders(business_id: str) -> str:
    results = query_pending_orders(business_id=business_id)
    return json.dumps(results, default=str)

def search_alternative_suppliers(product_category: str,
                                   exclude_country: str) -> str:
    results = query_alternative_suppliers(
        product_category=product_category,
        exclude_country=exclude_country
    )
    return json.dumps(results, default=str)

def get_port_status(port_name: str) -> str:
    results = query_port_status(port_name=port_name)
    return json.dumps(results, default=str)

def calculate_exposure(order_values: list, delay_days: int) -> str:
    total = sum(order_values)
    revenue_loss = round(total * 0.08, 2)
    return json.dumps({
        "at_risk_usd": total,
        "estimated_revenue_loss": revenue_loss,
        "delay_days": delay_days,
        "affected_orders": len(order_values),
    })

def score_suppliers(candidates: list, calibration_baseline: float = None) -> str:
    """
    Score and rank alternative suppliers using weighted formula.
    Reliability is computed dynamically from completed_orders (on-time rate + defect rate)
    and supplier_reviews (average rating). Falls back to static score if no history.
    Formula: lead_time*0.30 + price*0.25 + dynamic_reliability*0.25 + geographic_risk*0.20
    """
    scored = []
    for s in candidates:
        supplier_id = s.get("id", "")

        # ── Dynamic reliability from order history ────────────────────────────
        completed = query_completed_orders_by_supplier(supplier_id)
        reviews   = query_supplier_reviews(supplier_id)

        if completed:
            on_time_count   = sum(1 for o in completed if (o.get("delay_days") or 0) <= 0)
            on_time_rate    = on_time_count / len(completed)          # 0.0 – 1.0
            avg_defects     = sum((o.get("defective_items_count") or 0) for o in completed) / len(completed)
            defect_penalty  = min(avg_defects * 0.05, 2.0)           # max 2-point penalty
            history_score   = (on_time_rate * 10) - defect_penalty    # 0 – 10
        else:
            history_score   = s.get("reliability_score", 5.0)         # static fallback
            on_time_rate    = None
            avg_defects     = None

        if reviews:
            avg_rating      = sum(r.get("rating", 3.0) for r in reviews) / len(reviews)
            review_score    = (avg_rating / 5.0) * 10                 # normalise to 0–10
        else:
            review_score    = s.get("reliability_score", 5.0)         # static fallback
            avg_rating      = None

        # Blend: 60% history-based, 40% review-based (or pure fallback if neither)
        if completed and reviews:
            dynamic_reliability = (history_score * 0.60) + (review_score * 0.40)
        elif completed:
            dynamic_reliability = history_score
        elif reviews:
            dynamic_reliability = review_score
        else:
            dynamic_reliability = s.get("reliability_score", 5.0)

        dynamic_reliability = round(max(0, min(10, dynamic_reliability)), 2)

        # ── Other scoring dimensions ──────────────────────────────────────────
        lead_score  = max(0, 10 - (s.get("lead_time_days", 30) - 7) * 0.3)
        price_score = max(0, 10 - s.get("unit_price_usd", 5) * 0.5)
        geo_risk    = s.get("geographic_risk_score", 7.0)

        total = (lead_score          * 0.30 +
                 price_score         * 0.25 +
                 dynamic_reliability * 0.25 +
                 geo_risk            * 0.20)

        scored.append({
            **s,
            "dynamic_reliability_score": dynamic_reliability,
            "on_time_rate": on_time_rate,
            "avg_defects_per_order": round(avg_defects, 2) if avg_defects is not None else None,
            "avg_review_rating": round(avg_rating, 2) if avg_rating is not None else None,
            "completed_orders_count": len(completed),
            "reviews_count": len(reviews),
            "total_score": round(total, 2),
        })

    scored.sort(key=lambda x: x["total_score"], reverse=True)
    return json.dumps(scored[:3], default=str)

def generate_purchase_order(supplier_name: str, supplier_country: str,
                             product: str, quantity: int,
                             unit_price: float, required_by: str) -> str:
    total = quantity * unit_price
    po = f"""
PURCHASE ORDER
==============
From: Lone Star Roofing Supply, Dallas TX
To:   {supplier_name}, {supplier_country}

Product:        {product}
Quantity:       {quantity} units
Unit Price:     ${unit_price:.2f}
Total Value:    ${total:,.2f}
Required By:    {required_by}
Payment Terms:  Net 30

Note: This order is placed due to supply chain disruption
      at our primary supplier. Please confirm availability
      and delivery timeline by return email.
"""
    return json.dumps({"purchase_order": po, "total_value": total})

def generate_owner_email(disruption_summary: str,
                         affected_supplier: str,
                         exposure_usd: float,
                         estimated_loss_usd: float,
                         delay_days: int,
                         recommended_alternative: str,
                         po_quantity: int,
                         po_total_value: float) -> str:
    email = f"""
Subject: URGENT: Supply Chain Disruption Alert & Action Required

Dear Lone Star Roofing Supply Management,

This is an automated alert regarding a detected supply chain disruption that requires your immediate attention and approval.

DISRUPTION DETAILS:
-------------------
{disruption_summary}

IMPACT ON OPERATIONS:
--------------------
* Affected Primary Supplier: {affected_supplier}
* Estimated Delay:           {delay_days} days
* Total Value at Risk:       ${exposure_usd:,.2f}
* Estimated Revenue Loss:    ${estimated_loss_usd:,.2f}

PROPOSED MITIGATION SOLUTION:
----------------------------
We have identified and scored alternative suppliers. The recommended alternative is:
* Recommended Supplier:      {recommended_alternative}

We have drafted a minimal-loss Purchase Order to fulfill near-future orders and keep the business running:
* Order Quantity:            {po_quantity} units
* PO Total Value:            ${po_total_value:,.2f}

ACTION REQUIRED:
----------------
Please review and approve the drafted Purchase Order and corresponding actions via your Streamlit dashboard.

Best regards,
Supply Chain Disruption Intelligence Agent
"""
    return json.dumps({
        "email_draft": email,
        "recipient": "owner@lonestarroofing.com"
    })
# ── New Multi-Signal Detection Tools ──────────────────────────────────────────

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
    from datetime import datetime, timedelta
    
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
                    port_status = "Strike" if sig["strike_flag"] else f"Congestion {sig['congestion_score']}"
                    signal_details.append(f"Port {port_name}: {port_status} ({sig['delay_hours']}hrs delay)")
        
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

def calculate_impact(business_id: str, affected_supplier_ids: list, disruption_date: str) -> str:
    """
    Calculate actual financial impact on pending orders and predicted loss if no action taken.
    Returns: exposure_usd, affected_orders_count, inventory_coverage_status, expected_loss_usd
    """
    if not affected_supplier_ids:
        return json.dumps({
            "exposure_usd": 0, "affected_orders": 0, "inventory_covers": True, 
            "severity_adjustment": 1.0, "expected_loss_usd": 0
        })
    
    # ── Map suppliers to product_category ─────────────────────────────────────
    business_supp = query_business_suppliers(business_id=business_id)
    supp_cat_map = {s["id"]: s["product_category"] for s in business_supp if "id" in s and "product_category" in s}
    
    # ── Aggregate orders at risk by category─────────────────────────────────
    total_exposure = 0
    exposure_by_cat = {}
    affected_orders_list = []
    
    all_at_risk = query_pending_orders_at_risk(business_id, disruption_date, window_days=30)
    for order in all_at_risk:
        supp_id = order.get("supplier_id")
        if supp_id in affected_supplier_ids:
            val = order.get("order_value_usd", 0)
            total_exposure += val
            cat = supp_cat_map.get(supp_id, "unknown")
            exposure_by_cat[cat] = exposure_by_cat.get(cat, 0) + val
            affected_orders_list.append(order)
            
    # ── Evaluate against actual inventory table ──────────────────────────────
    inventory_data = query_inventory(business_id)
    inventory_map = {i["product_category"]: i["inventory_value_usd"] for i in inventory_data}
    
    inventory_covers = True
    expected_loss_usd = 0
    shortfall_details = []
    
    for cat, exp in exposure_by_cat.items():
        inv_val = inventory_map.get(cat, 0)
        if inv_val < exp:
            inventory_covers = False
            shortfall = exp - inv_val
            # High loss for shortfall portion (missed sales, rush premiums)
            expected_loss_usd += (shortfall * 1.50) + (inv_val * 0.15)
            shortfall_details.append(f"{cat}: Shortfall ${shortfall:,.2f}")
        else:
            # Minor loss (carrying costs, minor delays, overhead) for covered portion
            expected_loss_usd += (exp * 0.15)
    
    severity_adjustment = 0.5 if inventory_covers else 1.5
    
    return json.dumps({
        "exposure_usd": round(total_exposure, 2),
        "affected_orders": len(affected_orders_list),
        "inventory_covers": inventory_covers,
        "severity_adjustment": severity_adjustment,
        "expected_loss_usd": round(expected_loss_usd, 2),
        "predictive_loss_reasoning": "Inventory covers orders." if inventory_covers else f"Inventory depleted. {'; '.join(shortfall_details)} High risk of lost sales."
    }, default=str)

def query_calibration_baseline(event_type: str, region: str) -> str:
    """
    Query historical calibration for similar events.
    Returns: baseline_severity, confidence_score, historical_accuracy
    """
    baseline_data = query_calibration_with_recency(event_type, region, days_lookback=180)
    return json.dumps(baseline_data, default=str)

def detect_black_swan(disruption_events: list, weather_alerts: list, 
                     port_congestion_list: list) -> str:
    """
    Detect anomalies: if 2+ independent signals spike simultaneously → anomaly.
    Computes z-scores for news volume, port congestion, freight rates.
    """
    # Simple z-score calculation (in production, use 180-day historical baseline)
    news_volume = len(disruption_events)
    port_congestion = len([p for p in port_congestion_list if p.get("congestion_score", 0) > 5.0])
    
    # Hardcoded baseline for now (would fetch from aggregation table in production)
    news_mean, news_std = 8.0, 2.5  # Typical daily disruption events
    port_mean, port_std = 3.0, 1.5   # Typical congested ports
    
    news_zscore = (news_volume - news_mean) / news_std if news_std > 0 else 0
    port_zscore = (port_congestion - port_mean) / port_std if port_std > 0 else 0
    
    anomaly_flags = []
    if news_zscore > 2.5:
        anomaly_flags.append("news_volume_spike")
    if port_zscore > 2.5:
        anomaly_flags.append("port_congestion_spike")
    
    is_anomaly = len(anomaly_flags) >= 2
    
    return json.dumps({
        "is_anomaly": is_anomaly,
        "z_scores": {
            "news": round(news_zscore, 2),
            "port_congestion": round(port_zscore, 2)
        },
        "triggered_signals": anomaly_flags
    }, default=str)
# ── Tool Definitions for Gemini ───────────────────────────────────────────────

TOOL_DEFINITIONS = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="get_recent_disruptions",
            description="Fetch recent disruption events from BigQuery. "
                        "Returns news, weather, and port disruption events.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "hours": types.Schema(
                        type=types.Type.INTEGER,
                        description="How many hours back to look. Default 24."
                    )
                }
            )
        ),
        types.FunctionDeclaration(
            name="get_business_suppliers",
            description="Get the list of suppliers for a specific business.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "business_id": types.Schema(
                        type=types.Type.STRING,
                        description="The business ID to look up suppliers for."
                    )
                },
                required=["business_id"]
            )
        ),
        types.FunctionDeclaration(
            name="get_pending_orders",
            description="Get all pending orders for a business with ETAs "
                        "and order values.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "business_id": types.Schema(
                        type=types.Type.STRING,
                        description="The business ID to fetch orders for."
                    )
                },
                required=["business_id"]
            )
        ),
        types.FunctionDeclaration(
            name="search_alternative_suppliers",
            description="Search BigQuery for alternative suppliers by product "
                        "category, excluding a disrupted country.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "product_category": types.Schema(
                        type=types.Type.STRING,
                        description="Product category e.g. roofing_materials"
                    ),
                    "exclude_country": types.Schema(
                        type=types.Type.STRING,
                        description="Country to exclude from results."
                    )
                },
                required=["product_category", "exclude_country"]
            )
        ),
        types.FunctionDeclaration(
            name="get_port_status",
            description="Check congestion, strike flags, and vessel delays "
                        "for a specific port.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "port_name": types.Schema(
                        type=types.Type.STRING,
                        description="Name of the port e.g. Port of Houston"
                    )
                },
                required=["port_name"]
            )
        ),
        types.FunctionDeclaration(
            name="calculate_exposure",
            description="Calculate financial exposure in USD given a list of "
                        "at-risk order values and estimated delay days.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "order_values": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.NUMBER),
                        description="List of order values in USD"
                    ),
                    "delay_days": types.Schema(
                        type=types.Type.INTEGER,
                        description="Estimated delay in days"
                    )
                },
                required=["order_values", "delay_days"]
            )
        ),
        types.FunctionDeclaration(
            name="score_suppliers",
            description="Score and rank a list of alternative supplier "
                        "candidates. Returns top 3 ranked by score.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "candidates": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.OBJECT),
                        description="List of supplier dicts from "
                                    "search_alternative_suppliers"
                    )
                },
                required=["candidates"]
            )
        ),
        types.FunctionDeclaration(
            name="generate_purchase_order",
            description="Generate a ready-to-send purchase order for an "
                        "alternative supplier.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "supplier_name":    types.Schema(type=types.Type.STRING),
                    "supplier_country": types.Schema(type=types.Type.STRING),
                    "product":          types.Schema(type=types.Type.STRING),
                    "quantity":         types.Schema(
                        type=types.Type.INTEGER,
                        description="The quantity to order. Must be calculated as: max(ceil(total_at_risk_order_value / alternative_supplier_unit_price), alternative_supplier_moq) to minimize cost/loss."
                    ),
                    "unit_price":       types.Schema(type=types.Type.NUMBER),
                    "required_by":      types.Schema(type=types.Type.STRING),
                },
                required=["supplier_name", "supplier_country", "product",
                          "quantity", "unit_price", "required_by"]
            )
        ),
        types.FunctionDeclaration(
            name="generate_owner_email",
            description="Draft a professional disruption notification and mitigation alert email for the business owner.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "disruption_summary": types.Schema(type=types.Type.STRING, description="Summary of the disruption event"),
                    "affected_supplier": types.Schema(type=types.Type.STRING, description="Name of the affected primary supplier"),
                    "exposure_usd": types.Schema(type=types.Type.NUMBER, description="Total value of at-risk orders in USD"),
                    "estimated_loss_usd": types.Schema(type=types.Type.NUMBER, description="Estimated revenue/operational loss in USD"),
                    "delay_days": types.Schema(type=types.Type.INTEGER, description="Estimated delay in days"),
                    "recommended_alternative": types.Schema(type=types.Type.STRING, description="Name and country of the recommended alternative supplier"),
                    "po_quantity": types.Schema(type=types.Type.INTEGER, description="Minimum quantity in the drafted purchase order"),
                    "po_total_value": types.Schema(type=types.Type.NUMBER, description="Total cost of the purchase order in USD"),
                },
                required=["disruption_summary", "affected_supplier", "exposure_usd",
                          "estimated_loss_usd", "delay_days", "recommended_alternative",
                          "po_quantity", "po_total_value"]
            )
        ),
        types.FunctionDeclaration(
            name="detect_disruptions",
            description="Multi-signal disruption detection: cross-reference disruption events, weather alerts, and port activity against business suppliers. Returns list of affected suppliers and their risk factors.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "business_id": types.Schema(
                        type=types.Type.STRING,
                        description="Business ID to check disruptions for"
                    )
                },
                required=["business_id"]
            )
        ),
        types.FunctionDeclaration(
            name="calculate_impact",
            description="Calculate financial impact on pending orders given a list of affected suppliers. Returns exposure summary, inventory coverage status, and the predicted expected_loss_usd if no alternate supplier is chosen.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "business_id": types.Schema(type=types.Type.STRING),
                    "affected_supplier_ids": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.STRING),
                        description="List of supplier IDs affected by disruption"
                    ),
                    "disruption_date": types.Schema(
                        type=types.Type.STRING,
                        description="Date of disruption (YYYY-MM-DD format) to filter orders within 30-day window"
                    )
                },
                required=["business_id", "affected_supplier_ids", "disruption_date"]
            )
        ),
        types.FunctionDeclaration(
            name="query_calibration_baseline",
            description="Query historical calibration data for similar past events. Returns recency-weighted baseline severity and confidence score for this event type + region.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "event_type": types.Schema(type=types.Type.STRING, description="Event type e.g. 'disruption_detection', 'weather_alert', 'port_disruption'"),
                    "region": types.Schema(type=types.Type.STRING, description="Geographic region e.g. 'Gulf Coast, Texas'")
                },
                required=["event_type", "region"]
            )
        ),
        types.FunctionDeclaration(
            name="detect_black_swan",
            description="Detect unprecedented disruption anomalies. Computes z-scores across multiple signal types. If 2+ signals exceed 2.5 std dev → anomaly detected.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "disruption_events": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.OBJECT),
                        description="List of disruption_events from last 24 hours"
                    ),
                    "weather_alerts": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.OBJECT),
                        description="List of weather_alerts from last 48 hours"
                    ),
                    "port_congestion_list": types.Schema(
                        type=types.Type.ARRAY,
                        items=types.Schema(type=types.Type.OBJECT),
                        description="List of port_activity records with congestion scores"
                    )
                },
                required=["disruption_events", "weather_alerts", "port_congestion_list"]
            )
        ),
    ]
)

# Map function names to actual callables
TOOL_HANDLERS = {
    "get_recent_disruptions":     get_recent_disruptions,
    "get_business_suppliers":     get_business_suppliers,
    "get_pending_orders":         get_pending_orders,
    "search_alternative_suppliers": search_alternative_suppliers,
    "get_port_status":            get_port_status,
    "calculate_exposure":         calculate_exposure,
    "score_suppliers":            score_suppliers,
    "generate_purchase_order":    generate_purchase_order,
    "generate_owner_email":       generate_owner_email,
    "detect_disruptions":         detect_disruptions,
    "calculate_impact":           calculate_impact,
    "query_calibration_baseline": query_calibration_baseline,
    "detect_black_swan":          detect_black_swan,
}