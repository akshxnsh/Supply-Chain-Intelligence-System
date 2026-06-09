import json

import pytest

from src.agent import tools


@pytest.mark.asyncio
async def test_get_recent_disruptions_preserves_query_result(monkeypatch):
    rows = [{"id": "event-1", "headline": "Port delay"}]
    monkeypatch.setattr(tools, "query_recent_events", lambda hours: rows)

    assert json.loads(await tools.get_recent_disruptions(12)) == rows


@pytest.mark.asyncio
async def test_generate_purchase_order_preserves_document_contract():
    result = json.loads(
        await tools.generate_purchase_order(
            supplier_name="Alternative Co",
            supplier_country="USA",
            product="fasteners",
            quantity=200,
            unit_price=1.25,
            required_by="2026-07-01",
        )
    )

    assert result["total_value"] == 250
    assert "PURCHASE ORDER" in result["purchase_order"]
    assert "Alternative Co" in result["purchase_order"]


@pytest.mark.asyncio
async def test_save_alert_record_uses_existing_bigquery_layer(monkeypatch):
    captured = {}
    monkeypatch.setattr(tools, "save_alert", lambda alert: captured.update(alert))

    result = json.loads(
        await tools.save_alert_record(
            alert_id="alert-1",
            business_id="demo-business-001",
            created_at="2026-06-09T00:00:00+00:00",
            disruption_id="event-1",
            severity_score=8.5,
            exposure_usd=1000,
        )
    )

    assert result == {"saved": True, "alert_id": "alert-1"}
    assert captured["disruption_id"] == "event-1"
    assert captured["severity_score"] == 8.5
