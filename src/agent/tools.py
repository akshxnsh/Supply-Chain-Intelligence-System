from google.genai import types
from src.ingestion.bq_client import (
    query_recent_events,
    query_business_suppliers,
    query_pending_orders,
    query_alternative_suppliers,
    query_port_status,
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
    revenue_loss = total * 0.08
    return json.dumps({
        "at_risk_usd": total,
        "estimated_revenue_loss": revenue_loss,
        "delay_days": delay_days,
        "affected_orders": len(order_values),
    })

def score_suppliers(candidates: list) -> str:
    """Score and rank alternative suppliers."""
    scored = []
    for s in candidates:
        lead_score  = max(0, 10 - (s.get("lead_time_days", 30) - 7) * 0.3)
        price_score = max(0, 10 - s.get("unit_price_usd", 5) * 0.5)
        rel_score   = s.get("reliability_score", 5)
        geo_score   = 9.0 if s.get("country") in [
            "USA", "Canada", "Mexico", "Germany", "Japan"
        ] else 7.0
        total = (lead_score * 0.30 + price_score * 0.25 +
                 rel_score  * 0.25 + geo_score   * 0.20)
        scored.append({**s, "total_score": round(total, 2)})
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
}