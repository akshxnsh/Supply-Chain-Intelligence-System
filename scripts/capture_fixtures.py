"""Save small real responses from each source into tests/fixtures (used by the fetcher unit tests).

    python -m scripts.capture_fixtures            # all sources
    python -m scripts.capture_fixtures gdelt ecb  # only some
Re-run when a source changes its response format. Keeps 3 records per list to stay small.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from src.fetchers import ecb, federal_register, gdacs, gdelt, open_meteo, portwatch
from src.fetchers.http import get_json

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
KEEP = 3


def save(name: str, payload) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print("saved", name)


def cap_gdelt():
    p = get_json(gdelt.GDELT_URL, gdelt.article_params(gdelt.DEFAULT_QUERIES["ports"], "1d", 10),
                 timeout=gdelt.TIMEOUT, retries=5, backoff=15.0)
    p["articles"] = p.get("articles", [])[:KEEP]
    save("gdelt_artlist.json", p)


def cap_gdacs():
    p = get_json(gdacs.GDACS_URL, gdacs.event_params(date.today() - timedelta(days=9), date.today()))
    p["features"] = p["features"][:KEEP]
    save("gdacs_events.json", p)


def cap_portwatch():
    for name, svc in [("portwatch_ports.json", portwatch.PORTS), ("portwatch_chokepoints.json", portwatch.CHOKEPOINTS),
                      ("portwatch_disruptions.json", portwatch.DISRUPTIONS)]:
        p = get_json(f"{portwatch.BASE}/{svc}/FeatureServer/0/query", portwatch.query_params())
        p["features"] = p["features"][:KEEP]
        p.pop("fields", None)
        save(name, p)


def cap_federal_register():
    p = get_json(federal_register.URL, federal_register.document_params(per_page=KEEP))
    save("federal_register.json", p)


def cap_open_meteo():
    loc = [{"id": "SEA", "lat": 39.0, "lon": -75.0}]
    save("openmeteo_forecast.json", get_json(open_meteo.WEATHER_URL, open_meteo.forecast_params(loc, 5, open_meteo.WEATHER_DAILY)))
    save("openmeteo_marine.json", get_json(open_meteo.MARINE_URL, open_meteo.forecast_params(loc, 5, open_meteo.MARINE_DAILY)))


def cap_ecb():
    save("ecb_exr.json", get_json(ecb.URL.format(ccys="USD+CNY+KRW"), ecb.rate_params(last_n=3)))


SOURCES = {"gdelt": cap_gdelt, "gdacs": cap_gdacs, "portwatch": cap_portwatch,
           "federal_register": cap_federal_register, "open_meteo": cap_open_meteo, "ecb": cap_ecb}

if __name__ == "__main__":
    for name in (sys.argv[1:] or list(SOURCES)):
        SOURCES[name]()
