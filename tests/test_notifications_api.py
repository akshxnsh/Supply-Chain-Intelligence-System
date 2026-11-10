"""Notification history: newest first, scoped to one business, says that nothing is delivered yet."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.dashboard import api


@pytest.fixture()
def notes(pg_url):
    from src.ingestion.db import execute, insert_rows

    for t in ("alert_notifications", "alerts"):
        execute(f"TRUNCATE TABLE {t}")
    base = {"level": "notify", "title": "T", "source": "gdelt", "expected_loss_usd": 100.0, "confidence_band": "high", "stockout_risk": False}
    insert_rows("alert_notifications", [
        {**base, "alert_id": "a1", "business_id": "biz-a", "reason": "first notification", "notified_at": datetime(2026, 11, 1, tzinfo=timezone.utc), "title": "Older"},
        {**base, "alert_id": "a1", "business_id": "biz-a", "reason": "expected loss rose", "notified_at": datetime(2026, 11, 3, tzinfo=timezone.utc), "title": "Newer"},
        {**base, "alert_id": "b1", "business_id": "biz-b", "reason": "first notification", "notified_at": datetime(2026, 11, 2, tzinfo=timezone.utc), "title": "Other business"},
    ])


def test_history_is_newest_first_and_scoped_to_the_business(notes):
    r = TestClient(api.app).get("/api/notifications?business_id=biz-a").json()
    assert [n["title"] for n in r["notifications"]] == ["Newer", "Older"] and r["count"] == 2
    assert r["delivery"] == "not_configured"
    assert TestClient(api.app).get("/api/notifications?business_id=nobody").json()["notifications"] == []


def test_paging(notes):
    r = TestClient(api.app).get("/api/notifications?business_id=biz-a&limit=1&offset=1").json()
    assert [n["title"] for n in r["notifications"]] == ["Older"]
    assert TestClient(api.app).get("/api/notifications?limit=0").status_code == 422
