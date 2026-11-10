"""Fivetran custom connector: Open-Meteo daily weather + marine forecast -> table `daily_forecast`
(primary key location_id + forecast_date).

Locations come from configuration `locations`: a JSON string like [{"id": "SGSIN", "lat": 1.26, "lon": 103.8}].
Each sync replaces the next `days` days of forecast (a forecast changes as the date gets closer).
Data: Open-Meteo.com, CC BY 4.0, non-commercial use only (see docs/sources.md).
"""

import json
from datetime import datetime, timezone

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from chainguard_fetchers import open_meteo

DEFAULT_DAYS = 7


def parse_locations(configuration: dict) -> list[dict]:
    raw = configuration.get("locations")
    if not raw:
        raise ValueError("configuration 'locations' is required (JSON list of {id, lat, lon})")
    locations = json.loads(raw) if isinstance(raw, str) else raw
    for loc in locations:
        if not {"id", "lat", "lon"} <= set(loc):
            raise ValueError(f"location needs id, lat, lon: {loc}")
    return locations


def schema(configuration: dict):
    return [
        {
            "table": "daily_forecast",
            "primary_key": ["location_id", "forecast_date"],
            "columns": {
                "location_id": "STRING",
                "forecast_date": "NAIVE_DATE",
                "wind_gust_max_kmh": "DOUBLE",
                "wind_speed_max_kmh": "DOUBLE",
                "precipitation_sum_mm": "DOUBLE",
                "weather_code": "INT",
                "wave_height_max_m": "DOUBLE",
                "wave_period_max_s": "DOUBLE",
                "fetched_at": "UTC_DATETIME",
            },
        }
    ]


def update(configuration: dict, state: dict):
    locations = parse_locations(configuration)
    days = int(configuration.get("days", DEFAULT_DAYS))
    rows = open_meteo.fetch_daily_forecast(locations, days=days)
    for row in rows:
        op.upsert(table="daily_forecast", data=row)
    op.checkpoint({"last_run": datetime.now(timezone.utc).isoformat()})
    log.info(f"Open-Meteo: {len(rows)} forecast rows for {len(locations)} locations")


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
