"""The shipments / stock endpoint and the `monitored` flag on businesses."""

from fastapi.testclient import TestClient

from src.dashboard import api
from src.risk import company_view


def test_company_endpoint_returns_shipments_and_stock(monkeypatch):
    monkeypatch.setattr(company_view, "shipments", lambda b, limit=50: [{"shipment_id": "s1", "business": b}])
    monkeypatch.setattr(company_view, "stock_cover", lambda b: [{"product_category": "auto_parts", "days_of_stock": 10.8}])
    r = TestClient(api.app).get("/api/company?business_id=biz-x")
    assert r.status_code == 200
    assert r.json() == {"business_id": "biz-x", "shipments": [{"shipment_id": "s1", "business": "biz-x"}],
                        "stock": [{"product_category": "auto_parts", "days_of_stock": 10.8}]}


def test_company_endpoint_reports_a_database_problem_instead_of_crashing(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(company_view, "shipments", boom)
    r = TestClient(api.app).get("/api/company?business_id=biz-x").json()
    assert r["shipments"] == [] and r["stock"] == [] and "db down" in r["error"]


def test_businesses_say_which_ones_the_pipeline_analyses(monkeypatch):
    monkeypatch.setenv("PIPELINE_BUSINESSES", "biz-1")
    monkeypatch.setattr(api, "list_businesses", lambda: [{"id": "biz-1", "name": "One"}, {"id": "biz-2", "name": "Two"}])
    got = {b["id"]: b["monitored"] for b in TestClient(api.app).get("/api/businesses").json()["businesses"]}
    assert got == {"biz-1": True, "biz-2": False}


def test_monitored_defaults_to_the_demo_business(monkeypatch):
    monkeypatch.delenv("PIPELINE_BUSINESSES", raising=False)
    assert company_view.monitored_business_ids() == ["demo-business-001"]
