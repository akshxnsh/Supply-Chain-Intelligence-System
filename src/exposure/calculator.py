import json

from src.ingestion.bq_client import (
    query_inventory,
    query_pending_orders,
    query_shipments_at_risk,
)


def calculate_impact(
    business_id: str,
    affected_supplier_ids: list[str],
    disruption_date: str,
    tariff_cost_impact_usd: float = 0.0,
) -> str:
    """
    Calculate financial impact of a supply disruption.

    Supply side: shipment_timetable rows show inbound supplier shipments at risk.
    Demand side: pending_orders rows show client orders the business must fulfill.
    Buffer: inventory reduces impact when it can cover affected client demand.
    """
    if not affected_supplier_ids:
        return json.dumps({
            "exposure_usd": 0,
            "affected_shipments": 0,
            "pending_order_value_usd": 0,
            "inventory_coverage_usd": 0,
            "uncovered_demand_usd": 0,
            "inventory_covers": True,
            "severity_adjustment": 1.0,
            "expected_loss_usd": 0,
            "tariff_cost_included_usd": 0,
            "predictive_loss_reasoning": "No affected suppliers - no disruption impact.",
        })

    shipments_at_risk = query_shipments_at_risk(
        business_id, affected_supplier_ids, window_days=30
    )
    at_risk_by_cat: dict[str, float] = {}
    for shipment in shipments_at_risk:
        category = shipment.get("product_category", "unknown")
        at_risk_by_cat[category] = (
            at_risk_by_cat.get(category, 0)
            + shipment.get("shipment_value_usd", 0)
        )

    total_exposure = sum(at_risk_by_cat.values())

    client_orders = query_pending_orders(business_id)
    demand_by_cat: dict[str, float] = {}
    for order in client_orders:
        category = order.get("product_category", "unknown")
        demand_by_cat[category] = (
            demand_by_cat.get(category, 0)
            + order.get("order_value_usd", 0)
        )

    inventory_map = {
        row["product_category"]: row["inventory_value_usd"]
        for row in query_inventory(business_id)
    }

    inventory_covers = True
    expected_loss_usd = 0.0
    total_pending_order_value = 0.0
    total_inventory_coverage = 0.0
    total_uncovered_demand = 0.0
    shortfall_details: list[str] = []

    for category in set(at_risk_by_cat.keys()):
        inventory_value = inventory_map.get(category, 0)
        client_demand = demand_by_cat.get(category, 0)
        covered_demand = min(inventory_value, client_demand)
        shortfall = max(client_demand - inventory_value, 0)

        total_pending_order_value += client_demand
        total_inventory_coverage += covered_demand
        total_uncovered_demand += shortfall

        if shortfall == 0:
            expected_loss_usd += at_risk_by_cat.get(category, 0) * 0.15
        else:
            inventory_covers = False
            expected_loss_usd += (shortfall * 1.50) + (covered_demand * 0.15)
            shortfall_details.append(
                f"{category}: client demand ${client_demand:,.0f}, "
                f"inventory ${inventory_value:,.0f}, shortfall ${shortfall:,.0f}"
            )

    severity_adjustment = 0.5 if inventory_covers else 1.5
    expected_loss_usd += tariff_cost_impact_usd

    reasoning = (
        "Inventory covers all pending client orders for affected categories despite disruption."
        if inventory_covers
        else (
            "Inventory insufficient. "
            f"{'; '.join(shortfall_details)}. "
            "High risk of client order failures."
        )
    )

    return json.dumps({
        "exposure_usd": round(total_exposure, 2),
        "affected_shipments": len(shipments_at_risk),
        "pending_order_value_usd": round(total_pending_order_value, 2),
        "inventory_coverage_usd": round(total_inventory_coverage, 2),
        "uncovered_demand_usd": round(total_uncovered_demand, 2),
        "inventory_covers": inventory_covers,
        "severity_adjustment": severity_adjustment,
        "expected_loss_usd": round(expected_loss_usd, 2),
        "tariff_cost_included_usd": round(tariff_cost_impact_usd, 2),
        "predictive_loss_reasoning": reasoning,
    }, default=str)
