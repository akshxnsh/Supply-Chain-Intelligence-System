from fastapi.testclient import TestClient

from src.dashboard import api


def test_simulate_endpoint_preserves_dashboard_contract(monkeypatch):
    async def fake_cycle(business_id, log_callback):
        log_callback("ADK cycle complete")
        return {
            "alert_fired": True,
            "disruption": {"id": "event-1", "headline": "Delay"},
            "exposure_usd": 5000,
            "severity_score": 7.5,
            "top_supplier": "Alternative Co",
            "purchase_order": "PO draft",
            "owner_email": "Email draft",
            "tool_calls": [],
        }

    monkeypatch.setattr(api, "run_agent_cycle_async", fake_cycle)
    client = TestClient(api.app)

    response = client.post(
        "/api/simulate?business_id=demo-business-001"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["business_id"] == "demo-business-001"
    assert body["disruption"]["id"] == "event-1"
    assert body["severity_score"] == 7.5
    assert body["raw"]["tool_calls"] == []
