"""Fetcher unit tests: every source is parsed from a saved real response (tests/fixtures), and the
HTTP helper's retry/timeout rules are checked with a fake session. No network, no sleeping."""

import json
from datetime import date
from pathlib import Path

import pytest
import requests

from src.fetchers import ecb, federal_register, gdacs, gdelt, http, open_meteo, portwatch

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# -- http helper ---------------------------------------------------------------

class Resp:
    def __init__(self, status=200, body=None, text=None, headers=None):
        self.status_code, self._body, self.headers = status, body, headers or {}
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


class FakeSession:
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout, "headers": headers})
        out = self.outcomes.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


def test_http_retries_5xx_and_timeouts_then_succeeds():
    sleeps = []
    s = FakeSession(requests.Timeout("slow"), Resp(503), Resp(200, {"ok": 1}))
    assert http.get_json("https://x.test/a", session=s, sleep=sleeps.append) == {"ok": 1}
    assert len(s.calls) == 3 and sleeps == [1.5, 3.0]  # exponential backoff


def test_http_gives_up_after_retries():
    s = FakeSession(*[Resp(500)] * 4)
    with pytest.raises(http.FetchError, match="failed after 4 attempts"):
        http.get_json("https://x.test/a", session=s, sleep=lambda _: None)


def test_http_does_not_retry_client_errors_and_sends_timeout_and_agent():
    s = FakeSession(Resp(404, text="nope"))
    with pytest.raises(http.FetchError, match="HTTP 404"):
        http.get_json("https://x.test/a", session=s, sleep=lambda _: None)
    assert len(s.calls) == 1
    assert s.calls[0]["timeout"] == http.DEFAULT_TIMEOUT and "chainguard" in s.calls[0]["headers"]["User-Agent"]


def test_http_honours_retry_after_and_rejects_non_json():
    sleeps = []
    s = FakeSession(Resp(429, headers={"Retry-After": "7"}), Resp(200, {"a": 1}))
    http.get_json("https://x.test/a", session=s, sleep=sleeps.append)
    assert sleeps == [7.0]
    bad = FakeSession(Resp(200, text="Please limit requests"))
    with pytest.raises(http.FetchError, match="did not return JSON"):
        http.get_json("https://x.test/b", session=bad, sleep=lambda _: None)


def test_http_min_interval_spaces_calls_to_same_host():
    http._last_call.clear()
    sleeps = []
    s = FakeSession(Resp(200, {}), Resp(200, {}))
    http.get_json("https://slow.test/a", session=s, min_interval=5.0, sleep=sleeps.append)
    http.get_json("https://slow.test/b", session=s, min_interval=5.0, sleep=sleeps.append)
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 5.0


# -- GDELT ---------------------------------------------------------------------

def test_gdelt_parse_articles():
    rows = gdelt.parse_articles(load("gdelt_artlist.json"), "ports")
    assert rows and all(r["article_id"] and r["url"].startswith("http") and r["query_name"] == "ports" for r in rows)
    assert len({r["article_id"] for r in rows}) == len(rows)
    assert rows[0]["seen_at"].endswith("+00:00")
    assert gdelt.parse_articles({}) == []


def test_gdelt_title_cleanup_and_stable_id():
    payload = {"articles": [{"url": "https://a.test/1", "title": "30 , 000 TONNE deal ; done",
                             "seendate": "20261110T060000Z", "domain": "a.test",
                             "language": "English", "sourcecountry": "X"}]}
    r1 = gdelt.parse_articles(payload)[0]
    assert r1["title"] == "30, 000 TONNE deal; done"
    assert r1["article_id"] == gdelt.parse_articles(payload)[0]["article_id"]


def test_gdelt_fetch_all_dedupes_across_queries(monkeypatch):
    art = {"articles": [{"url": "https://same.test/x", "title": "t", "seendate": "20261110T060000Z"}]}
    monkeypatch.setattr(gdelt, "get_json", lambda *a, **k: art)
    rows = gdelt.fetch_all(queries={"a": "q1", "b": "q2"})
    assert len(rows) == 1 and rows[0]["query_name"] == "a"


# -- GDACS ---------------------------------------------------------------------

def test_gdacs_parse_events():
    rows = gdacs.parse_events(load("gdacs_events.json"))
    assert rows
    r = rows[0]
    assert r["event_id"].startswith(r["event_type"] + "-") and r["alert_level"] in ("Green", "Orange", "Red")
    assert isinstance(r["lat"], float) and isinstance(r["is_current"], bool)
    assert "eventlist" in gdacs.event_params(date(2026, 11, 1), date(2026, 11, 10))


# -- PortWatch -----------------------------------------------------------------

def test_portwatch_parse_ports_chokepoints_disruptions():
    ports = portwatch.parse_locations([f["attributes"] for f in load("portwatch_ports.json")["features"]], "port")
    assert ports[0]["kind"] == "port" and ports[0]["location_id"] and ports[0]["lat"] is not None
    chokes = portwatch.parse_locations(
        [f["attributes"] for f in load("portwatch_chokepoints.json")["features"]], "chokepoint")
    assert chokes[0]["kind"] == "chokepoint"
    dis = portwatch.parse_disruptions([f["attributes"] for f in load("portwatch_disruptions.json")["features"]])
    assert dis[0]["from_date"].endswith("+00:00") and dis[0]["event_id"] is not None


def test_portwatch_daily_requires_token(monkeypatch):
    monkeypatch.delenv("PORTWATCH_ARCGIS_TOKEN", raising=False)
    with pytest.raises(portwatch.PortWatchTokenRequired):
        portwatch.fetch_daily_ports()


def test_portwatch_arcgis_error_inside_http_200(monkeypatch):
    monkeypatch.setattr(portwatch, "get_json", lambda *a, **k: {"error": {"code": 499, "message": "Token Required"}})
    with pytest.raises(portwatch.PortWatchTokenRequired):
        portwatch.query_layer("Daily_Ports_Data")
    monkeypatch.setattr(portwatch, "get_json", lambda *a, **k: {"error": {"code": 400, "message": "bad"}})
    with pytest.raises(http.FetchError):
        portwatch.query_layer("x")


def test_portwatch_pages_until_transfer_limit_clears(monkeypatch):
    pages = [{"features": [{"attributes": {"a": 1}}], "exceededTransferLimit": True},
             {"features": [{"attributes": {"a": 2}}]}]
    seen = []

    def fake(url, params, **k):
        seen.append(params["resultOffset"])
        return pages.pop(0)

    monkeypatch.setattr(portwatch, "get_json", fake)
    assert portwatch.query_layer("S") == [{"a": 1}, {"a": 2}]
    assert seen == [0, portwatch.PAGE_SIZE]


def test_portwatch_parse_daily_converts_dates_and_keeps_numbers():
    rows = portwatch.parse_daily([{"ObjectId": 1, "date": 1746144000000, "portid": "p1", "portcalls": 7, "import": 100.5}])
    assert rows == [{"portcalls": 7, "import": 100.5, "location_id": "p1", "day": "2025-05-02"}]


# -- Federal Register ----------------------------------------------------------

def test_federal_register_parse_and_params():
    rows = federal_register.parse_documents(load("federal_register.json"))
    assert rows and rows[0]["document_number"] and rows[0]["doc_type"] in ("Rule", "Proposed Rule", "Notice")
    assert rows[0]["agencies"]
    p = federal_register.document_params(since=date(2026, 11, 1))
    assert p["conditions[publication_date][gte]"] == "2026-11-01" and p["order"] == "oldest"
    assert "international-trade-commission" in p["conditions[agencies][]"]


def test_federal_register_paginates_when_incremental(monkeypatch):
    calls = []

    def fake(url, params, **k):
        calls.append(params["page"])
        return {"results": [{"document_number": f"d{params['page']}"}], "total_pages": 3}

    monkeypatch.setattr(federal_register, "get_json", fake)
    rows = federal_register.fetch_documents(since=date(2026, 11, 1))
    assert [r["document_number"] for r in rows] == ["d1", "d2", "d3"] and calls == [1, 2, 3]
    calls.clear()
    federal_register.fetch_documents(None)
    assert calls == [1]  # no cursor -> just the newest page


# -- Open-Meteo ----------------------------------------------------------------

def test_open_meteo_parse_joins_weather_and_marine():
    loc = [{"id": "SEA", "lat": 39.0, "lon": -75.0}]
    rows = open_meteo.parse_forecasts(loc, load("openmeteo_forecast.json"), load("openmeteo_marine.json"))
    assert len(rows) == 5 and rows[0]["location_id"] == "SEA"
    assert rows[0]["wind_gust_max_kmh"] is not None and rows[0]["wave_height_max_m"] is not None
    assert len({r["forecast_date"] for r in rows}) == 5


def test_open_meteo_no_marine_data_keeps_weather_rows():
    loc = [{"id": "SEA", "lat": 39.0, "lon": -75.0}]
    rows = open_meteo.parse_forecasts(loc, load("openmeteo_forecast.json"), None)
    assert rows and all(r["wave_height_max_m"] is None for r in rows)


def test_open_meteo_batches_and_survives_marine_failure(monkeypatch):
    locs = [{"id": f"L{i}", "lat": 1.0 + i, "lon": 2.0} for i in range(open_meteo.BATCH + 1)]
    forecast = load("openmeteo_forecast.json")

    def fake(url, params, **k):
        if "marine" in url:
            raise http.FetchError("no marine data")
        n = len(params["latitude"].split(","))
        return forecast if n == 1 else [forecast] * n

    monkeypatch.setattr(open_meteo, "get_json", fake)
    rows = open_meteo.fetch_daily_forecast(locs, days=5)
    assert len({r["location_id"] for r in rows}) == open_meteo.BATCH + 1
    assert "Open-Meteo" in open_meteo.ATTRIBUTION


# -- ECB -----------------------------------------------------------------------

def test_ecb_parse_rates():
    rows = ecb.parse_rates(load("ecb_exr.json"))
    assert {r["currency"] for r in rows} == {"USD", "CNY", "KRW"}
    assert len(rows) == 9 and all(r["eur_rate"] > 0 for r in rows)
    assert rows == sorted(rows, key=lambda r: (r["currency"], r["rate_date"]))
    usd = [r for r in rows if r["currency"] == "USD"]
    assert 0.5 < usd[0]["eur_rate"] < 2.0  # USD per EUR


def test_ecb_params_incremental_vs_last_n():
    assert ecb.rate_params(since=date(2026, 11, 1)) == {"format": "jsondata", "startPeriod": "2026-11-01"}
    assert ecb.rate_params(last_n=5)["lastNObservations"] == 5


def test_ecb_bad_shape_raises():
    with pytest.raises(http.FetchError):
        ecb.parse_rates({"nope": 1})
