"""Fivetran custom connector: GDACS disasters -> table `events` (primary key event_id).

Incremental: events are asked for from (state.last_run date - OVERLAP_DAYS) because GDACS updates an event
(new episode, alert level, end date) after it first appears; the upsert replaces the old values.
"""

from datetime import date, datetime, timedelta, timezone

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from chainguard_fetchers import gdacs

FIRST_SYNC_DAYS = 14
OVERLAP_DAYS = 3


def schema(configuration: dict):
    return [
        {
            "table": "events",
            "primary_key": ["event_id"],
            "columns": {
                "event_id": "STRING",
                "alert_score": "DOUBLE",
                "from_date": "NAIVE_DATETIME",
                "to_date": "NAIVE_DATETIME",
                "date_modified": "NAIVE_DATETIME",
                "is_current": "BOOLEAN",
                "lat": "DOUBLE",
                "lon": "DOUBLE",
                "severity_value": "DOUBLE",
            },
        }
    ]


def window(state: dict, today: date) -> tuple[date, date]:
    last = state.get("last_run")
    start = date.fromisoformat(last) - timedelta(days=OVERLAP_DAYS) if last else today - timedelta(days=FIRST_SYNC_DAYS)
    return start, today


def update(configuration: dict, state: dict):
    today = datetime.now(timezone.utc).date()
    start, end = window(state, today)
    log.info(f"GDACS: events {start} .. {end}")
    rows = gdacs.fetch_events(start, end)
    for row in rows:
        op.upsert(table="events", data=row)
    op.checkpoint({"last_run": today.isoformat()})
    log.info(f"GDACS: {len(rows)} events")


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
