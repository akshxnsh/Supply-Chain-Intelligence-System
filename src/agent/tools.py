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

# Import relocated logic
from src.detection.disruption_detector import detect_disruptions
from src.exposure.calculator import calculate_impact
from src.suppliers.scorer import score_suppliers

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
    news_volume = len(disruption_events)
    port_congestion = len([p for p in port_congestion_list if p.get("congestion_score", 0) > 5.0])
    
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
            description="Check congestion, strike flags, and vessel delays for a specific port.",
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
        # Additional function declarations can be added here as needed.
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
