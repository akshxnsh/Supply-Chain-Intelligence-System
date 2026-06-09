import json
from src.ingestion.bq_client import (
    query_shipments_at_risk,
    query_pending_orders,
    query_inventory,
)


def calculate_impact(
    business_id: str,
    affected_supplier_ids: list[str],
    disruption_date: str,
    tariff_cost_impact_usd: float = 0.0,
) -> str:
    """
    Calculate financial impact of a supply disruption.

    Supply side  — query shipment_timetable for inbound shipments from affected
                   suppliers that won't arrive (exposure).
    Demand side  — query pending_orders for what the business's clients have
                   ordered and need fulfilled.
    Buffer       — query inventory to see if on-hand stock covers client demand.

    Impact is LOW when inventory covers all client orders; HIGH when the
    disrupted shipment creates a fulfilment shortfall.
    """
    if not affected_supplier_ids:
        return json.dumps({
            "exposure_usd": 0,
            "affected_shipments": 0,
            "inventory_covers": True,
            "severity_adjustment": 1.0,
            "expected_loss_usd": 0,
            "tariff_cost_included_usd": 0,
            "predictive_loss_reasoning": "No affected suppliers — no disruption impact.",
        })

    # ── Step 1: disrupted inbound shipments (supply side) ────────────────────
    shipments_at_risk = query_shipments_at_risk(
        business_id, affected_supplier_ids, window_days=30
    )
    at_risk_by_cat: dict[str, float] = {}
    for s in shipments_at_risk:
        cat = s.get("product_category", "unknown")
        at_risk_by_cat[cat] = at_risk_by_cat.get(cat, 0) + s.get("shipment_value_usd", 0)

    total_exposure = sum(at_risk_by_cat.values())

    # ── Step 2: client demand (demand side) ──────────────────────────────────
    client_orders = query_pending_orders(business_id)
    demand_by_cat: dict[str, float] = {}
    for o in client_orders:
        cat = o.get("product_category", "unknown")
        demand_by_cat[cat] = demand_by_cat.get(cat, 0) + o.get("order_value_usd", 0)

    # ── Step 3: on-hand inventory ─────────────────────────────────────────────
    inventory_data = query_inventory(business_id)
    inventory_map = {
        i["product_category"]: i["inventory_value_usd"] for i in inventory_data
    }

    # ── Step 4: per-category impact ───────────────────────────────────────────
    inventory_covers = True
    expected_loss_usd = 0.0
    shortfall_details: list[str] = []

    affected_categories = set(at_risk_by_cat.keys()) | set(demand_by_cat.keys())
    for cat in affected_categories:
        inv_val = inventory_map.get(cat, 0)
        client_demand = demand_by_cat.get(cat, 0)

        if inv_val >= client_demand:
            # Inventory fully covers client orders — only minor delay/carrying cost
            expected_loss_usd += at_risk_by_cat.get(cat, 0) * 0.15
        else:
            inventory_covers = False
            shortfall = client_demand - inv_val
            # Rush premium + missed sales on unmet client orders
            expected_loss_usd += (shortfall * 1.50) + (inv_val * 0.15)
            shortfall_details.append(
                f"{cat}: client demand ${client_demand:,.0f}, "
                f"inventory ${inv_val:,.0f}, shortfall ${shortfall:,.0f}"
            )

    severity_adjustment = 0.5 if inventory_covers else 1.5
    expected_loss_usd += tariff_cost_impact_usd

    reasoning = (
        "Inventory covers all pending client orders despite disruption."
        if inventory_covers
        else f"Inventory insufficient. {'; '.join(shortfall_details)}. High risk of client order failures."
    )

    return json.dumps({
        "exposure_usd": round(total_exposure, 2),
        "affected_shipments": len(shipments_at_risk),
        "inventory_covers": inventory_covers,
        "severity_adjustment": severity_adjustment,
        "expected_loss_usd": round(expected_loss_usd, 2),
        "tariff_cost_included_usd": round(tariff_cost_impact_usd, 2),
        "predictive_loss_reasoning": reasoning,
    }, default=str)