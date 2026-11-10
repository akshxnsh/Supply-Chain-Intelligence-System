"""Open-Meteo - weather and marine FORECASTS (free, no key).

Docs: https://open-meteo.com/en/docs and https://open-meteo.com/en/docs/marine-weather-api
Terms: free for NON-COMMERCIAL use only, data licensed CC BY 4.0 -> keep the attribution below
anywhere the data is shown. Fair-use limits: ~10,000 calls/day. One deterministic forecast, no
ensemble, so there is no uncertainty range (confidence therefore falls with days ahead, in code).

We keep DAILY summaries per location (max gust, max wind, rain total, max wave height), keyed by
(location_id, forecast_date): ~7 rows per port instead of 168 hourly rows, which keeps the
Fivetran monthly-active-row count small.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from src.fetchers.http import FetchError, get_json

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0), https://open-meteo.com/"
WEATHER_DAILY = ("wind_gusts_10m_max", "wind_speed_10m_max", "precipitation_sum", "weather_code")
MARINE_DAILY = ("wave_height_max", "wave_period_max")
BATCH = 50  # locations per request


def forecast_params(locations: Sequence[dict], days: int, daily: Sequence[str]) -> dict:
    return {
        "latitude": ",".join(str(l["lat"]) for l in locations),
        "longitude": ",".join(str(l["lon"]) for l in locations),
        "daily": ",".join(daily),
        "forecast_days": days,
        "timezone": "UTC",
    }


def _as_list(payload) -> list[dict]:
    return payload if isinstance(payload, list) else [payload]


def parse_forecasts(locations: Sequence[dict], weather_payload, marine_payload=None,
                    fetched_at: datetime | None = None) -> list[dict]:
    """One row per (location, day). Marine values are None where the point has no sea cell."""
    fetched = (fetched_at or datetime.now(timezone.utc)).isoformat()
    weather = _as_list(weather_payload)
    marine = _as_list(marine_payload) if marine_payload is not None else [None] * len(locations)
    rows = []
    for loc, w, m in zip(locations, weather, marine):
        wd = (w or {}).get("daily") or {}
        md = (m or {}).get("daily") or {}
        for i, day in enumerate(wd.get("time") or []):
            def pick(d, key):
                vals = d.get(key) or []
                return vals[i] if i < len(vals) else None
            wave_days = md.get("time") or []
            j = wave_days.index(day) if day in wave_days else None
            rows.append({
                "location_id": loc["id"],
                "forecast_date": day,
                "wind_gust_max_kmh": pick(wd, "wind_gusts_10m_max"),
                "wind_speed_max_kmh": pick(wd, "wind_speed_10m_max"),
                "precipitation_sum_mm": pick(wd, "precipitation_sum"),
                "weather_code": pick(wd, "weather_code"),
                "wave_height_max_m": (md.get("wave_height_max") or [None] * (j + 1))[j] if j is not None else None,
                "wave_period_max_s": (md.get("wave_period_max") or [None] * (j + 1))[j] if j is not None else None,
                "fetched_at": fetched,
            })
    return rows


def fetch_daily_forecast(locations: Sequence[dict], days: int = 7, **http_kwargs) -> list[dict]:
    """locations: [{'id': 'USBAL', 'lat': 39.27, 'lon': -76.58}, ...]"""
    rows: list[dict] = []
    for start in range(0, len(locations), BATCH):
        batch = list(locations[start:start + BATCH])
        weather = get_json(WEATHER_URL, forecast_params(batch, days, WEATHER_DAILY), **http_kwargs)
        try:
            marine = get_json(MARINE_URL, forecast_params(batch, days, MARINE_DAILY), **http_kwargs)
        except FetchError:
            marine = None  # e.g. every point in the batch is inland: weather rows still valid
        rows.extend(parse_forecasts(batch, weather, marine))
    return rows
