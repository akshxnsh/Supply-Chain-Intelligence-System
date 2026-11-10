"""GDELT freshness is measured from Fivetran's last successful sync, not from the newest row (a quiet news day writes no rows)."""

from datetime import datetime, timedelta, timezone

from src.agent import freshness_agent as fa
from src.agent.freshness_config import FRESHNESS_TABLES


def _ago(minutes: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


def test_only_gdelt_uses_fivetran_sync_time():
    assert [n for n, c in FRESHNESS_TABLES.items() if c.use_fivetran_sync_time] == ["gdelt_articles"]


def test_quiet_gdelt_with_recent_successful_sync_is_fresh(monkeypatch):
    monkeypatch.setattr(fa, "fivetran_last_success", lambda connector_id: _ago(10))
    monkeypatch.setattr(fa, "query_table_last_updated", lambda *a, **k: _ago(400))  # newest row is old: no news
    r = fa._table_freshness("gdelt_articles")
    assert r["is_stale"] is False and r["measured_from"] == "fivetran_last_successful_sync" and 9 < r["age_minutes"] < 11


def test_gdelt_really_stale_when_sync_stopped_succeeding(monkeypatch):
    monkeypatch.setattr(fa, "fivetran_last_success", lambda connector_id: _ago(300))
    monkeypatch.setattr(fa, "query_table_last_updated", lambda *a, **k: _ago(5))
    r = fa._table_freshness("gdelt_articles")
    assert r["is_stale"] is True and r["measured_from"] == "fivetran_last_successful_sync"


def test_falls_back_to_newest_row_when_fivetran_unreachable(monkeypatch):
    monkeypatch.setattr(fa, "fivetran_last_success", lambda connector_id: None)
    monkeypatch.setattr(fa, "query_table_last_updated", lambda *a, **k: _ago(400))
    r = fa._table_freshness("gdelt_articles")
    assert r["is_stale"] is True and r["measured_from"] == "newest_row"


def test_other_sources_still_use_newest_row(monkeypatch):
    monkeypatch.setattr(fa, "fivetran_last_success", lambda connector_id: (_ for _ in ()).throw(AssertionError("must not be called")))
    monkeypatch.setattr(fa, "query_table_last_updated", lambda *a, **k: _ago(30))
    r = fa._table_freshness("gdacs_events")
    assert r["is_stale"] is False and r["measured_from"] == "newest_row"


def test_fivetran_lookup_never_raises(monkeypatch):
    import requests

    monkeypatch.setenv("FIVETRAN_API_KEY", "x")
    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(requests, "get", boom)
    assert fa.fivetran_last_success("diplomat_umpire") is None
