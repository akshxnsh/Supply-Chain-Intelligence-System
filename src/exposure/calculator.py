import json
from src.ingestion.bq_client import (
    query_business_suppliers,
    query_pending_orders_at_risk,
    query_inventory,
)

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
        "predictive_loss_reasoning": "Inventory covers orders." if inventory_covers else f"Inventory depleted. {"; ".join(shortfall_details)} High risk of lost sales."
    }, default=str)