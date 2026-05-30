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
    revenue_loss = round(total * 0.08, 2)
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

def generate_customer_email(customer_count: int, original_eta: str,
                             revised_eta: str, delay_days: int,
                             disruption_type: str) -> str:
    email = f"""
Subject: Important Update: Delivery Delay Notification

Dear Valued Customer,

We are writing to inform you of a delay affecting your pending order.

Due to {disruption_type}, our primary supplier has been disrupted.
We have already secured an alternative supplier to fulfill your order.

Original delivery date: {original_eta}
Revised delivery date:  {revised_eta} ({delay_days} day delay)

We sincerely apologize for this inconvenience. We are working
around the clock to minimize the impact on your business.

Please contact us directly if you have any questions.

Best regards,
Lone Star Roofing Supply
"""
    return json.dumps({
        "email_draft": email,
        "recipients_count": customer_count
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
                    "quantity":         types.Schema(type=types.Type.INTEGER),
                    "unit_price":       types.Schema(type=types.Type.NUMBER),
                    "required_by":      types.Schema(type=types.Type.STRING),
                },
                required=["supplier_name", "supplier_country", "product",
                          "quantity", "unit_price", "required_by"]
            )
        ),
        types.FunctionDeclaration(
            name="generate_customer_email",
            description="Draft a professional delay notification email for "
                        "affected customers.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "customer_count":  types.Schema(type=types.Type.INTEGER),
                    "original_eta":    types.Schema(type=types.Type.STRING),
                    "revised_eta":     types.Schema(type=types.Type.STRING),
                    "delay_days":      types.Schema(type=types.Type.INTEGER),
                    "disruption_type": types.Schema(type=types.Type.STRING),
                },
                required=["customer_count", "original_eta", "revised_eta",
                          "delay_days", "disruption_type"]
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
    "generate_customer_email":    generate_customer_email,
}