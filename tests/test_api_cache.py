"""Redis response cache on the read endpoints (fakeredis, no database, no network)."""

import json

import fakeredis
import pytest
from fastapi.testclient import TestClient

from src.dashboard import api, cache


@pytest.fixture()
def redis_client():
    r = fakeredis.FakeRedis(decode_responses=True)
    cache.configure(r)
    yield r
    cache.reset()


@pytest.fixture()
def calls(monkeypatch):
    """Count real database calls behind the endpoints."""
    n = {"suppliers": 0, "alerts": 0, "risk": 0}

    def suppliers(business_id):
        n["suppliers"] += 1
        return [{"supplier_name": f"S of {business_id}", "annual_spend_usd": 1.0}]

    def alerts(business_id, limit, offset):
        n["alerts"] += 1
        return [{"id": "a1", "limit": limit, "offset": offset}]

    def risk(business_id, level, status, limit, offset):
        n["risk"] += 1
        return [{"alert_id": "r1", "level": level or "watch"}]

    monkeypatch.setattr(api, "query_suppliers_overview", suppliers)
    monkeypatch.setattr(api, "query_alerts_page", alerts)
    monkeypatch.setattr(api, "query_risk_alerts", risk)
    return n


def test_second_identical_request_is_a_cache_hit_without_touching_the_database(redis_client, calls):
    c = TestClient(api.app)
    first = c.get("/api/suppliers?business_id=biz-1")
    second = c.get("/api/suppliers?business_id=biz-1")
    assert first.headers["x-cache"] == "MISS" and second.headers["x-cache"] == "HIT"
    assert first.json() == second.json() == {"suppliers": [{"supplier_name": "S of biz-1", "annual_spend_usd": 1.0}]}
    assert calls["suppliers"] == 1
    (key,) = redis_client.keys("chainguard:api:suppliers:*")
    assert 0 < redis_client.ttl(key) <= 300


def test_different_arguments_never_share_an_entry(redis_client, calls):
    c = TestClient(api.app)
    c.get("/api/suppliers?business_id=biz-1")
    other = c.get("/api/suppliers?business_id=biz-2")
    assert other.headers["x-cache"] == "MISS" and other.json()["suppliers"][0]["supplier_name"] == "S of biz-2"
    page1, page2 = c.get("/api/alerts?business_id=b&limit=5&offset=0"), c.get("/api/alerts?business_id=b&limit=5&offset=5")
    assert page1.json()["offset"] == 0 and page2.json()["offset"] == 5 and calls["alerts"] == 2


def test_errors_are_never_cached(redis_client, monkeypatch):
    n = {"calls": 0}

    def boom(business_id):
        n["calls"] += 1
        raise RuntimeError("database down")

    monkeypatch.setattr(api, "query_suppliers_overview", boom)
    c = TestClient(api.app)
    assert c.get("/api/suppliers").json()["error"] == "database down"
    assert c.get("/api/suppliers").json()["error"] == "database down"
    assert n["calls"] == 2 and redis_client.keys("chainguard:api:suppliers:*") == []


def test_writes_invalidate_only_their_own_group(redis_client, calls, monkeypatch):
    monkeypatch.setattr("src.ingestion.queries.acknowledge_alert", lambda alert_id: None)
    c = TestClient(api.app)
    c.get("/api/alerts?business_id=b")
    c.get("/api/suppliers?business_id=b")
    assert c.post("/api/alerts/a1/acknowledge").json()["success"] is True
    assert c.get("/api/alerts?business_id=b").headers["x-cache"] == "MISS"          # alerts group was cleared
    assert c.get("/api/suppliers?business_id=b").headers["x-cache"] == "HIT"        # suppliers untouched


def test_risk_alerts_cache_and_acknowledge_invalidates(redis_client, calls, monkeypatch):
    monkeypatch.setattr(api, "acknowledge_risk_alert", lambda alert_id: alert_id == "r1")
    c = TestClient(api.app)
    assert c.get("/api/risk/alerts?business_id=b&level=watch").headers["x-cache"] == "MISS"
    assert c.get("/api/risk/alerts?business_id=b&level=watch").headers["x-cache"] == "HIT"
    assert c.get("/api/risk/alerts?business_id=b&level=notify").headers["x-cache"] == "MISS"   # level is part of the key
    assert c.post("/api/risk/alerts/r1/acknowledge").json()["status"] == "acknowledged"
    assert c.post("/api/risk/alerts/nope/acknowledge").status_code == 404
    assert c.get("/api/risk/alerts?business_id=b&level=watch").headers["x-cache"] == "MISS"
    assert c.get("/api/risk/alerts?level=bogus").status_code == 422                          # query validation still works


def test_single_alert_404_is_not_cached_and_dates_serialize(redis_client, monkeypatch):
    from datetime import date, datetime, timezone

    row = {"alert_id": "r1", "act_by": date(2026, 11, 12), "last_seen": datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc),
           "explanation": ["x"]}
    monkeypatch.setattr(api, "query_risk_alert", lambda alert_id: row if alert_id == "r1" else None)
    c = TestClient(api.app)
    assert c.get("/api/risk/alerts/zzz").status_code == 404
    a, b = c.get("/api/risk/alerts/r1"), c.get("/api/risk/alerts/r1")
    assert a.headers["x-cache"] == "MISS" and b.headers["x-cache"] == "HIT" and b.json()["act_by"] == "2026-11-12"


def test_async_endpoint_is_cached_too(redis_client, monkeypatch):
    n = {"calls": 0}

    async def fake_fresh(table_names=None):
        n["calls"] += 1
        return json.dumps([{"table_name": "t", "is_stale": False}])

    monkeypatch.setattr("src.agent.freshness_agent.check_table_freshness", fake_fresh)
    c = TestClient(api.app)
    a, b = c.get("/api/freshness"), c.get("/api/freshness")
    assert a.headers["x-cache"] == "MISS" and b.headers["x-cache"] == "HIT" and n["calls"] == 1 and b.json()["fresh_count"] == 1


def test_redis_down_means_bypass_not_error(calls, monkeypatch):
    monkeypatch.setattr("src.ingestion.queries.acknowledge_alert", lambda alert_id: None)

    class Dead:
        def get(self, *a, **k):
            raise ConnectionError("down")

        def set(self, *a, **k):
            raise ConnectionError("down")

        def incr(self, *a, **k):
            raise ConnectionError("down")

        def scan_iter(self, *a, **k):
            raise ConnectionError("down")

    cache.configure(Dead())
    try:
        c = TestClient(api.app)
        r = c.get("/api/suppliers?business_id=b")
        assert r.status_code == 200 and r.json()["suppliers"] and calls["suppliers"] == 1
        assert c.post("/api/alerts/a1/acknowledge").status_code == 200       # invalidate() survives a dead Redis
    finally:
        cache.reset()


def test_disabled_cache_sets_bypass_header_and_stats_report_it(calls):
    cache.configure(None)
    try:
        c = TestClient(api.app)
        assert c.get("/api/suppliers?business_id=b").headers["x-cache"] == "BYPASS"
        assert c.get("/api/cache/stats").json() == {"enabled": False}
    finally:
        cache.reset()


def test_stats_count_hits_and_misses(redis_client, calls):
    c = TestClient(api.app)
    for _ in range(4):
        c.get("/api/suppliers?business_id=b")
    assert c.get("/api/cache/stats").json() == {"enabled": True, "available": True, "hits": 3, "misses": 1, "hit_rate": 0.75}


def test_openapi_signature_is_unchanged_for_clients():
    params = {p["name"] for p in api.app.openapi()["paths"]["/api/suppliers"]["get"]["parameters"]}
    assert params == {"business_id"}              # the injected Response parameter is invisible to API users


def test_db_pool_check_is_skipped_for_recently_verified_connections(monkeypatch):
    from src.ingestion import db

    class Conn:
        pass

    checked = []
    monkeypatch.setattr(db.ConnectionPool, "check_connection", staticmethod(lambda c: checked.append(c)))
    monkeypatch.setattr(db, "CHECK_AFTER_IDLE_S", 30.0)
    c = Conn()
    db._check(c)
    db._check(c)
    db._check(c)
    assert len(checked) == 1                                   # verified once, trusted for 30 s
    c._cg_checked -= 60
    db._check(c)
    assert len(checked) == 2                                   # idle for a minute: verified again
    monkeypatch.setattr(db, "CHECK_AFTER_IDLE_S", 0.0)
    db._check(c)
    db._check(c)
    assert len(checked) == 4                                   # 0 = the old behaviour, check every time
