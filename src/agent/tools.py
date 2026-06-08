import json

from src.detection.disruption_detector import detect_disruptions
from src.exposure.calculator import calculate_impact
from src.ingestion.bq_client import (
    query_alternative_suppliers,
    query_business_suppliers,
    query_calibration_with_recency,
    query_inventory,
    query_pending_orders,
    query_port_status,
    query_recent_events,
    query_recent_weather_alerts,
    query_supplier_reviews,
    query_tariff_updates,
    save_alert,
)
from src.suppliers.scorer import score_suppliers


def get_recent_disruptions(hours: int = 24) -> str:
    """Fetch recent disruption events from BigQuery."""
    return json.dumps(query_recent_events(hours=hours), default=str)


def get_business_suppliers(business_id: str) -> str:
    """Get the suppliers registered for a business."""
    return json.dumps(query_business_suppliers(business_id=business_id), default=str)


def get_pending_orders(business_id: str) -> str:
    """Get pending orders for a business."""
    return json.dumps(query_pending_orders(business_id=business_id), default=str)


def search_alternative_suppliers(
    product_category: str,
    exclude_country: str,
) -> str:
    """Find alternative suppliers while excluding a disrupted country."""
    rows = query_alternative_suppliers(
        product_category=product_category,
        exclude_country=exclude_country,
    )
    return json.dumps(rows, default=str)


def get_port_status(port_name: str) -> str:
    """Get congestion, strike, and vessel-delay data for a port."""
    return json.dumps(query_port_status(port_name=port_name), default=str)


def get_port_activity(port_name: str) -> str:
    """ADK-facing alias for port activity lookup."""
    return get_port_status(port_name)


def get_inventory(business_id: str) -> str:
    """Return current on-hand inventory levels by product category."""
    return json.dumps(query_inventory(business_id), default=str)


def get_weather_alerts(hours_back: int = 48) -> str:
    """Return recent weather alerts across all monitored regions."""
    return json.dumps(
        query_recent_weather_alerts(hours_back=hours_back),
        default=str,
    )


def get_tariff_updates(days_back: int = 30) -> str:
    """Return recent tariff changes."""
    return json.dumps(query_tariff_updates(days_back=days_back), default=str)


def get_supplier_reviews(supplier_id: str) -> str:
    """Return historical reviews for a supplier."""
    return json.dumps(query_supplier_reviews(supplier_id), default=str)


def calculate_exposure(order_values: list, delay_days: int) -> str:
    """Estimate at-risk value and revenue loss for delayed orders."""
    total = sum(order_values)
    revenue_loss = round(total * 0.08, 2)
    return json.dumps(
        {
            "at_risk_usd": total,
            "estimated_revenue_loss": revenue_loss,
            "delay_days": delay_days,
            "affected_orders": len(order_values),
        }
    )


def generate_purchase_order(
    supplier_name: str,
    supplier_country: str,
    product: str,
    quantity: int,
    unit_price: float,
    required_by: str,
    business_id: str = "demo-business-001",
) -> str:
    """Draft a purchase order without placing the order."""
    from src.agent.business_registry import get_business

    business = get_business(business_id)
    company_name = business.get("name", "Our Company")
    total = quantity * unit_price
    purchase_order = f"""
PURCHASE ORDER
==============
From: {company_name}
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
    return json.dumps(
        {"purchase_order": purchase_order, "total_value": total}
    )


def generate_owner_email(
    disruption_summary: str,
    affected_supplier: str,
    exposure_usd: float,
    estimated_loss_usd: float,
    delay_days: int,
    recommended_alternative: str,
    po_quantity: int,
    po_total_value: float,
    business_id: str = "demo-business-001",
) -> str:
    """Draft the existing owner notification email."""
    from src.agent.business_registry import get_business

    business = get_business(business_id)
    recipient = business.get("contact_email", "owner@company.com")
    contact_name = business.get("contact_name", "Management")
    company_name = business.get("name", "Our Company")
    email = f"""
Subject: URGENT: Supply Chain Disruption Alert & Action Required

Dear {company_name} {contact_name},

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
Please review and approve the drafted Purchase Order and corresponding actions via your dashboard.

Best regards,
Supply Chain Disruption Intelligence Agent
"""
    return json.dumps({"email_draft": email, "recipient": recipient})


def query_calibration_baseline(event_type: str, region: str) -> str:
    """Query the 180-day recency-weighted historical calibration baseline."""
    baseline = query_calibration_with_recency(
        event_type,
        region,
        days_lookback=180,
    )
    return json.dumps(baseline, default=str)


def detect_black_swan(
    disruption_events: list,
    weather_alerts: list,
    port_congestion_list: list,
) -> str:
    """Detect a multi-signal anomaly using the existing z-score logic."""
    news_volume = len(disruption_events)
    port_congestion = len(
        [
            port
            for port in port_congestion_list
            if port.get("congestion_score", 0) > 5.0
        ]
    )

    try:
        import statistics

        from src.ingestion.bq_client import run_query

        calibration = run_query(
            """
            SELECT severity_scored
            FROM `akshxnsh-supplychain.supply_chain.agent_calibration`
            WHERE severity_scored IS NOT NULL
            ORDER BY created_at DESC
            LIMIT 50
            """
        )
        scores = [
            row["severity_scored"]
            for row in calibration
            if row.get("severity_scored") is not None
        ]
        if len(scores) >= 5:
            news_mean = statistics.mean(scores)
            news_std = max(statistics.stdev(scores), 0.5)
        else:
            news_mean, news_std = 8.0, 2.5
    except Exception as exc:
        news_mean, news_std = 8.0, 2.5
        print(f"[BLACK_SWAN] Calibration baseline query failed ({exc}).")

    port_mean, port_std = 3.0, 1.5
    news_zscore = (news_volume - news_mean) / news_std if news_std > 0 else 0
    port_zscore = (port_congestion - port_mean) / port_std if port_std > 0 else 0

    anomaly_flags = []
    if news_zscore > 2.5:
        anomaly_flags.append("news_volume_spike")
    if port_zscore > 2.5:
        anomaly_flags.append("port_congestion_spike")

    return json.dumps(
        {
            "is_anomaly": len(anomaly_flags) >= 2,
            "z_scores": {
                "news": round(news_zscore, 2),
                "port_congestion": round(port_zscore, 2),
            },
            "triggered_signals": anomaly_flags,
            "weather_alert_count": len(weather_alerts),
        },
        default=str,
    )


def save_alert_record(
    alert_id: str,
    business_id: str,
    created_at: str,
    disruption_id: str,
    severity_score: float,
    exposure_usd: float,
    actions_json: str = "[]",
    status: str = "active",
) -> dict:
    """Persist a validated alert through the existing BigQuery layer."""
    save_alert(
        {
            "id": alert_id,
            "business_id": business_id,
            "created_at": created_at,
            "disruption_id": disruption_id,
            "severity_score": severity_score,
            "exposure_usd": exposure_usd,
            "actions_json": actions_json,
            "status": status,
        }
    )
    return {"saved": True, "alert_id": alert_id}
