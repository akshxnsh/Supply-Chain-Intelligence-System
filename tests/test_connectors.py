"""Connector logic tests (state/cursor handling, tables, primary keys) with a stub of the Fivetran SDK,
so they run in the normal Python env. The real SDK is exercised with `fivetran debug` (see docs/fivetran.md).
Also checks that the copies of the fetchers inside each connector folder are in sync with src/fetchers.
"""

import importlib.util
import sys
import types
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONNECTORS = ROOT / "connectors"
NAMES = ["gdelt", "gdacs", "portwatch", "federal_register", "open_meteo", "ecb"]


class Recorder:
    def __init__(self):
        self.upserts, self.checkpoints = [], []


@pytest.fixture()
def sdk(monkeypatch):
    """Install a stub `fivetran_connector_sdk` and return its recorder."""
    rec = Recorder()
    mod = types.ModuleType("fivetran_connector_sdk")

    class Connector:
        def __init__(self, update, schema=None):
            self.update, self.schema = update, schema

        def debug(self, *a, **k):
            pass

    class Operations:
        @staticmethod
        def upsert(table, data):
            rec.upserts.append((table, data))

        @staticmethod
        def checkpoint(state):
            rec.checkpoints.append(dict(state))

    class Logging:
        info = staticmethod(lambda *a, **k: None)
        warning = staticmethod(lambda *a, **k: None)
        severe = staticmethod(lambda *a, **k: None)

    mod.Connector, mod.Operations, mod.Logging = Connector, Operations, Logging
    monkeypatch.setitem(sys.modules, "fivetran_connector_sdk", mod)
    return rec


def load_connector(name, monkeypatch):
    """Import connectors/<name>/connector.py with its own chainguard_fetchers package on the path."""
    for key in [k for k in sys.modules if k == "chainguard_fetchers" or k.startswith("chainguard_fetchers.")]:
        monkeypatch.delitem(sys.modules, key)
    monkeypatch.syspath_prepend(str(CONNECTORS / name))
    spec = importlib.util.spec_from_file_location(f"conn_{name}", CONNECTORS / name / "connector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_connector_fetcher_copies_are_in_sync():
    from scripts.sync_connector_fetchers import CONNECTORS as MAP
    from scripts.sync_connector_fetchers import render

    for folder, module in MAP.items():
        for fname, content in render(module).items():
            on_disk = (CONNECTORS / folder / "chainguard_fetchers" / fname).read_text(encoding="utf-8")
            assert on_disk == content, f"{folder}/{fname} is stale: run python -m scripts.sync_connector_fetchers"


@pytest.mark.parametrize("name", NAMES)
def test_every_connector_declares_tables_with_primary_keys(name, sdk, monkeypatch):
    mod = load_connector(name, monkeypatch)
    cfg = {"locations": '[{"id": "A", "lat": 1, "lon": 2}]'} if name == "open_meteo" else {}
    tables = mod.schema(cfg)
    assert tables and all(t["table"] and t["primary_key"] for t in tables)
    assert (CONNECTORS / name / "configuration.json").exists()
    assert mod.connector.update is mod.update and mod.connector.schema is mod.schema


# -- GDELT ---------------------------------------------------------------------

def test_gdelt_window_and_upsert(sdk, monkeypatch):
    mod = load_connector("gdelt", monkeypatch)
    now = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    assert mod.hours_to_fetch({}, now) == 24
    assert mod.hours_to_fetch({"last_run": "2026-11-10T10:30:00+00:00"}, now) == 3   # ceil(1.5) + 1 overlap
    assert mod.hours_to_fetch({"last_run": "2026-11-01T00:00:00+00:00"}, now) == 24  # capped
    assert mod.hours_to_fetch({"last_run": "2026-11-10T11:59:00+00:00"}, now) == 2

    seen = {}
    monkeypatch.setattr(mod.gdelt, "fetch_all", lambda timespan: seen.setdefault("t", timespan) and [{"article_id": "a1"}, {"article_id": "a2"}])
    mod.update({}, {})
    assert seen["t"] == "24h"
    assert [t for t, _ in sdk.upserts] == ["articles", "articles"]
    assert "last_run" in sdk.checkpoints[-1]


# -- GDACS ---------------------------------------------------------------------

def test_gdacs_window_overlaps_and_upserts(sdk, monkeypatch):
    mod = load_connector("gdacs", monkeypatch)
    assert mod.window({}, date(2026, 11, 10)) == (date(2026, 10, 27), date(2026, 11, 10))
    assert mod.window({"last_run": "2026-11-08"}, date(2026, 11, 10)) == (date(2026, 11, 5), date(2026, 11, 10))
    monkeypatch.setattr(mod.gdacs, "fetch_events", lambda s, e: [{"event_id": "TC-1"}])
    mod.update({}, {})
    assert sdk.upserts == [("events", {"event_id": "TC-1"})] and sdk.checkpoints[-1]["last_run"]


# -- PortWatch -----------------------------------------------------------------

def test_portwatch_catalogue_monthly_and_disruption_cursor(sdk, monkeypatch):
    mod = load_connector("portwatch", monkeypatch)
    calls = {"ports": 0, "since": []}

    def fake_ports():
        calls["ports"] += 1
        return [{"location_id": "p1"}]

    monkeypatch.setattr(mod.portwatch, "fetch_ports", fake_ports)
    monkeypatch.setattr(mod.portwatch, "fetch_chokepoints", lambda: [{"location_id": "c1"}])
    monkeypatch.setattr(mod.portwatch, "fetch_disruptions",
                        lambda since: (calls["since"].append(since), [{"event_id": 1, "edit_date": "2026-11-05T10:00:00+00:00"}])[1])

    mod.update({}, {})
    assert calls["ports"] == 1 and calls["since"] == [None]
    state = sdk.checkpoints[-1]
    assert state["last_edit_date"] == "2026-11-05" and state["catalogue_month"]
    assert {t for t, _ in sdk.upserts} == {"ports", "chokepoints", "disruptions"}

    sdk.upserts.clear()
    mod.update({}, state)  # same month -> catalogue not re-read, disruptions asked since edit date - 1 day
    assert calls["ports"] == 1 and calls["since"][-1] == date(2026, 11, 4)
    assert {t for t, _ in sdk.upserts} == {"disruptions"}


def test_portwatch_daily_tables_only_with_token(sdk, monkeypatch):
    mod = load_connector("portwatch", monkeypatch)
    assert len(mod.schema({})) == 3
    assert len(mod.schema({"enable_daily": "true", "arcgis_token": ""})) == 3
    full = mod.schema({"enable_daily": "true", "arcgis_token": "tok"})
    assert len(full) == 5 and {"daily_ports", "daily_chokepoints"} <= {t["table"] for t in full}


# -- Federal Register ----------------------------------------------------------

def test_federal_register_cursor(sdk, monkeypatch):
    mod = load_connector("federal_register", monkeypatch)
    today = date(2026, 11, 10)
    assert mod.start_date({}, {}, today) == date(2026, 9, 11)
    assert mod.start_date({"initial_days": "7"}, {}, today) == date(2026, 11, 3)
    assert mod.start_date({}, {"last_publication_date": "2026-11-02"}, today) == date(2026, 11, 2)

    got = {}
    monkeypatch.setattr(mod.federal_register, "fetch_documents",
                        lambda since: (got.setdefault("since", since), [{"document_number": "d1", "publication_date": "2026-11-09"}])[1])
    mod.update({}, {"last_publication_date": "2026-11-02"})
    assert got["since"] == date(2026, 11, 2)
    assert sdk.checkpoints[-1] == {"last_publication_date": "2026-11-09"}


def test_federal_register_checkpoint_never_moves_backwards(sdk, monkeypatch):
    mod = load_connector("federal_register", monkeypatch)
    monkeypatch.setattr(mod.federal_register, "fetch_documents", lambda since: [])
    mod.update({}, {"last_publication_date": "2026-11-02"})
    assert sdk.checkpoints[-1] == {"last_publication_date": "2026-11-02"}


# -- Open-Meteo ----------------------------------------------------------------

def test_open_meteo_locations_validation_and_update(sdk, monkeypatch):
    mod = load_connector("open_meteo", monkeypatch)
    with pytest.raises(ValueError, match="locations"):
        mod.parse_locations({})
    with pytest.raises(ValueError, match="id, lat, lon"):
        mod.parse_locations({"locations": '[{"id": "A"}]'})

    got = {}
    monkeypatch.setattr(mod.open_meteo, "fetch_daily_forecast",
                        lambda locs, days: (got.update(n=len(locs), days=days), [{"location_id": "A", "forecast_date": "2026-11-10"}])[1])
    mod.update({"locations": '[{"id": "A", "lat": 1, "lon": 2}]', "days": "5"}, {})
    assert got == {"n": 1, "days": 5} and sdk.upserts[0][0] == "daily_forecast"


def test_committed_open_meteo_config_has_valid_locations(sdk, monkeypatch):
    import json

    mod = load_connector("open_meteo", monkeypatch)
    cfg = json.loads((CONNECTORS / "open_meteo" / "configuration.json").read_text(encoding="utf-8"))
    assert len(mod.parse_locations(cfg)) >= 5


# -- ECB -----------------------------------------------------------------------

def test_ecb_cursor_and_currencies(sdk, monkeypatch):
    mod = load_connector("ecb", monkeypatch)
    today = date(2026, 11, 10)
    assert mod.start_date({}, {}, today) == date(2026, 8, 12)
    assert mod.start_date({}, {"last_rate_date": "2026-11-09"}, today) == date(2026, 11, 9)
    assert mod.currencies({"currencies": "usd, cny"}) == ("USD", "CNY")
    assert "USD" in mod.currencies({})

    monkeypatch.setattr(mod.ecb, "fetch_rates", lambda ccys, since: [{"currency": "USD", "rate_date": "2026-11-09", "eur_rate": 1.1}])
    mod.update({}, {"last_rate_date": "2026-11-08"})
    assert sdk.upserts[0][0] == "exchange_rates" and sdk.checkpoints[-1] == {"last_rate_date": "2026-11-09"}
