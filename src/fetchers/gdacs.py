"""GDACS - Global Disaster Alert and Coordination System (free, no key).

Docs: https://www.gdacs.org/gdacsapi/swagger/index.html  (GeoJSON event list)
Event types: EQ earthquake, TC tropical cyclone, FL flood, VO volcano, DR drought, WF wildfire.
An event changes over time (new "episodes"); we key on event type + id and keep the latest values.
"""

from __future__ import annotations

from datetime import date

from src.fetchers.http import get_json

GDACS_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
DEFAULT_TYPES = ("TC", "FL", "EQ", "VO")  # the ones that close ports / delay ships
DEFAULT_LEVELS = ("Green", "Orange", "Red")


def event_params(from_date: date, to_date: date, event_types=DEFAULT_TYPES, alert_levels=DEFAULT_LEVELS) -> dict:
    return {
        "eventlist": ";".join(event_types),
        "fromdate": from_date.isoformat(),
        "todate": to_date.isoformat(),
        "alertlevel": ";".join(alert_levels),
    }


def parse_events(payload: dict) -> list[dict]:
    rows = []
    for f in payload.get("features") or []:
        p = f.get("properties") or {}
        geom = (f.get("geometry") or {}).get("coordinates") or [None, None]
        sev = p.get("severitydata") or {}
        if p.get("eventid") is None or not p.get("eventtype"):
            continue
        countries = [c.get("iso3") for c in (p.get("affectedcountries") or []) if c.get("iso3")]
        rows.append({
            "event_id": f"{p['eventtype']}-{p['eventid']}",
            "event_type": p["eventtype"],
            "name": p.get("name") or p.get("eventname"),
            "alert_level": p.get("alertlevel"),
            "alert_score": p.get("alertscore"),
            "from_date": p.get("fromdate"),
            "to_date": p.get("todate"),
            "date_modified": p.get("datemodified"),
            "is_current": str(p.get("iscurrent")).lower() == "true",
            "lon": geom[0],
            "lat": geom[1],
            "country": p.get("country") or None,
            "affected_countries_iso3": ";".join(countries) or None,
            "severity_value": sev.get("severity"),
            "severity_unit": sev.get("severityunit"),
            "severity_text": sev.get("severitytext"),
            "report_url": (p.get("url") or {}).get("report"),
        })
    return rows


def fetch_events(from_date: date, to_date: date, **http_kwargs) -> list[dict]:
    payload = get_json(GDACS_URL, event_params(from_date, to_date), **http_kwargs)
    return parse_events(payload)
