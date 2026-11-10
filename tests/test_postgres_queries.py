"""Query-layer tests against a real PostgreSQL (skipped without TEST_DATABASE_URL)."""

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.usefixtures("pg_url")


@pytest.fixture()
def q(pg_url):
    from src.ingestion import db, queries

    for t in ["disruption_events", "business_suppliers", "pending_orders", "shipment_timetable",
              "agent_alerts", "agent_calibration", "completed_orders", "supplier_reviews",
              "alternative_suppliers", "weather_alerts", "tariff_updates", "inventory", "port_activity"]:
        db.execute(f'TRUNCATE TABLE "{t}"')
    return queries


def _now():
    return datetime.now(timezone.utc)


def test_migrations_are_idempotent_and_create_indexes(pg_url):
    import psycopg
    from psycopg.rows import dict_row

    from src.ingestion.migrate import apply_migrations, status

    with psycopg.connect(pg_url, row_factory=dict_row) as conn:
        assert apply_migrations(conn) == []  # already applied by the fixture
        st = status(conn)
        assert st["pending"] == [] and len(st["applied"]) >= 2
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM pg_indexes WHERE schemaname = current_schema() "
                        "AND indexname LIKE 'idx_%'")
            assert cur.fetchone()["n"] >= 10


def test_recent_events_respects_window_and_order(q):
    from src.ingestion.db import insert_rows

    insert_rows("disruption_events", [
        {"id": "new", "source": "x", "headline": "recent", "published_at": _now() - timedelta(hours=1)},
        {"id": "old", "source": "x", "headline": "old", "published_at": _now() - timedelta(hours=100)},
        {"id": "mid", "source": "x", "headline": "mid", "published_at": _now() - timedelta(hours=5)},
    ])
    ids = [r["id"] for r in q.query_recent_events(hours=24)]
    assert ids == ["new", "mid"]


def test_shipments_at_risk_filters_supplier_status_and_window(q):
    from src.ingestion.db import insert_rows

    today = _now()

    def ship(i, sup, status, days):
        return {"id": i, "business_id": "b1", "supplier_id": sup, "product_category": "auto_parts",
                "quantity": 10, "shipment_value_usd": 100.0, "expected_arrival_date": (today + timedelta(days=days)).date(),
                "etd": today - timedelta(days=3), "eta": today + timedelta(days=days),
                "journey_time_hours": 100.0, "route": "A > B", "status": status}

    insert_rows("shipment_timetable", [ship("s1", "sup-1", "in_transit", 5), ship("s2", "sup-2", "in_transit", 5),
                                       ship("s3", "sup-1", "delivered", 5), ship("s4", "sup-1", "in_transit", 90)])
    rows = q.query_shipments_at_risk("b1", ["sup-1"], window_days=30)
    assert [r["id"] for r in rows] == ["s1"]
    assert q.query_shipments_at_risk("b1", []) == []


def test_alternative_suppliers_excludes_country_and_sorts(q):
    from src.ingestion.db import insert_rows

    def alt(i, c, rel):
        return {"id": i, "name": i, "country": c, "product_category": "fasteners", "reliability_score": rel}

    insert_rows("alternative_suppliers", [alt("a", "USA", 9.0), alt("b", "China", 9.9), alt("c", "Mexico", 8.0)])
    assert [r["id"] for r in q.query_alternative_suppliers("fasteners", "China")] == ["a", "c"]


def test_batch_orders_and_reviews_group_by_supplier(q):
    from src.ingestion.db import insert_rows

    d = _now().date()
    insert_rows("completed_orders", [
        {"id": "o1", "business_id": "b", "supplier_id": "s1", "order_value_usd": 1.0, "ordered_date": d,
         "expected_delivery_date": d, "status": "delivered", "delay_days": 2},
        {"id": "o2", "business_id": "b", "supplier_id": "s1", "order_value_usd": 1.0, "ordered_date": d,
         "expected_delivery_date": d, "status": "cancelled"},
    ])
    out = q.query_completed_orders_by_suppliers(["s1", "s2"])
    assert len(out["s1"]) == 1 and out["s2"] == []


def test_save_alert_then_duplicate_check_then_acknowledge(q):
    from src.ingestion.db import run_query

    q.save_alert({"id": "al-1", "business_id": "b1", "created_at": _now().isoformat(),
                  "disruption_id": "d1", "severity_score": 7.5, "exposure_usd": 1000.0})
    assert q.check_duplicate_alert("b1", "d1") is True
    assert q.check_duplicate_alert("b1", "other") is False
    q.acknowledge_alert("al-1")
    assert run_query("SELECT status FROM agent_alerts WHERE id = 'al-1'")[0]["status"] == "acknowledged"
    with pytest.raises(ValueError):
        q.save_alert({"id": "x", "business_id": "b", "created_at": "t", "severity_score": 99})


def test_calibration_recency_weights_recent_records_more(q):
    from src.ingestion.db import insert_rows

    def rec(i, sev, days_ago):
        return {"id": i, "event_type": "port", "region": "r", "severity_scored": sev, "actual_delay_days": 3,
                "created_at": _now() - timedelta(days=days_ago)}

    insert_rows("agent_calibration", [rec("c1", 2.0, 170), rec("c2", 8.0, 1)])
    out = q.query_calibration_with_recency("port", "r")
    assert out["record_count"] == 2
    assert out["weighted_baseline_severity"] > 5.0  # the recent 8.0 outweighs the old 2.0
    assert q.query_calibration_with_recency("port", "nowhere")["record_count"] == 0


def test_alerts_page_has_pagination_and_confidence_column(q):
    for i in range(3):
        q.save_alert({"id": f"p{i}", "business_id": "b1",
                      "created_at": (_now() - timedelta(minutes=i)).isoformat(), "severity_score": 5.0})
    page = q.query_alerts_page("b1", limit=2, offset=0)
    assert [r["id"] for r in page] == ["p0", "p1"]
    assert "calibration_confidence" in page[0]
    assert [r["id"] for r in q.query_alerts_page("b1", limit=2, offset=2)] == ["p2"]


def test_table_last_updated_for_freshness(q):
    from src.ingestion.db import insert_rows

    assert q.query_table_last_updated("inventory") is None
    insert_rows("inventory", [{"id": "i1", "business_id": "b", "product_category": "x", "inventory_value_usd": 1.0}])
    assert q.query_table_last_updated("inventory") is not None
