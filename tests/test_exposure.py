import json

from src.exposure import calculator


def test_calculate_impact_inventory_covers_client_demand(monkeypatch):
    monkeypatch.setattr(
        calculator,
        "query_shipments_at_risk",
        lambda business_id, supplier_ids, window_days: [
            {
                "supplier_id": "sup-1",
                "product_category": "roofing_materials",
                "shipment_value_usd": 10000,
            }
        ],
    )
    monkeypatch.setattr(
        calculator,
        "query_pending_orders",
        lambda business_id: [
            {
                "client_id": "client-1",
                "product_category": "roofing_materials",
                "order_value_usd": 8000,
            }
        ],
    )
    monkeypatch.setattr(
        calculator,
        "query_inventory",
        lambda business_id: [
            {
                "product_category": "roofing_materials",
                "inventory_value_usd": 9000,
            }
        ],
    )

    result = json.loads(
        calculator.calculate_impact("demo-business-001", ["sup-1"], "2026-06-10")
    )

    assert result["exposure_usd"] == 10000
    assert result["pending_order_value_usd"] == 8000
    assert result["inventory_coverage_usd"] == 8000
    assert result["uncovered_demand_usd"] == 0
    assert result["inventory_covers"] is True
    assert result["expected_loss_usd"] == 1500
    assert result["severity_adjustment"] == 0.5


def test_calculate_impact_uncovered_demand_increases_loss(monkeypatch):
    monkeypatch.setattr(
        calculator,
        "query_shipments_at_risk",
        lambda business_id, supplier_ids, window_days: [
            {
                "supplier_id": "sup-1",
                "product_category": "roofing_materials",
                "shipment_value_usd": 10000,
            }
        ],
    )
    monkeypatch.setattr(
        calculator,
        "query_pending_orders",
        lambda business_id: [
            {
                "client_id": "client-1",
                "product_category": "roofing_materials",
                "order_value_usd": 8000,
            }
        ],
    )
    monkeypatch.setattr(
        calculator,
        "query_inventory",
        lambda business_id: [
            {
                "product_category": "roofing_materials",
                "inventory_value_usd": 3000,
            }
        ],
    )

    result = json.loads(
        calculator.calculate_impact("demo-business-001", ["sup-1"], "2026-06-10")
    )

    assert result["inventory_covers"] is False
    assert result["inventory_coverage_usd"] == 3000
    assert result["uncovered_demand_usd"] == 5000
    assert result["expected_loss_usd"] == 7950
    assert result["severity_adjustment"] == 1.5


def test_calculate_impact_no_affected_suppliers_returns_zero():
    result = json.loads(
        calculator.calculate_impact("demo-business-001", [], "2026-06-10")
    )

    assert result["exposure_usd"] == 0
    assert result["affected_shipments"] == 0
    assert result["pending_order_value_usd"] == 0
    assert result["inventory_covers"] is True
    assert result["expected_loss_usd"] == 0


def test_calculate_impact_shipment_without_matching_demand_is_limited(monkeypatch):
    monkeypatch.setattr(
        calculator,
        "query_shipments_at_risk",
        lambda business_id, supplier_ids, window_days: [
            {
                "supplier_id": "sup-1",
                "product_category": "roofing_materials",
                "shipment_value_usd": 10000,
            }
        ],
    )
    monkeypatch.setattr(
        calculator,
        "query_pending_orders",
        lambda business_id: [
            {
                "client_id": "client-1",
                "product_category": "fasteners",
                "order_value_usd": 8000,
            }
        ],
    )
    monkeypatch.setattr(calculator, "query_inventory", lambda business_id: [])

    result = json.loads(
        calculator.calculate_impact("demo-business-001", ["sup-1"], "2026-06-10")
    )

    assert result["exposure_usd"] == 10000
    assert result["pending_order_value_usd"] == 0
    assert result["uncovered_demand_usd"] == 0
    assert result["inventory_covers"] is True
    assert result["expected_loss_usd"] == 1500
