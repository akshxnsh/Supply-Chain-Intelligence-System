"""Fivetran custom connector: IMF PortWatch.

Tables:
  ports (location_id)           port catalogue with coordinates   - refreshed once a month (it barely changes)
  chokepoints (location_id)     the chokepoint catalogue          - refreshed once a month
  disruptions (event_id)        PortWatch disruption events       - incremental on edit date
  daily_ports / daily_chokepoints (location_id, day)  ONLY when configuration enable_daily = "true"
      and a token is configured: those layers are token-gated (see docs/sources.md).
"""

from datetime import date, datetime, timedelta, timezone

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from chainguard_fetchers import portwatch

LOCATION_COLUMNS = {"location_id": "STRING", "lat": "DOUBLE", "lon": "DOUBLE", "vessel_count_total": "INT"}


def daily_enabled(configuration: dict) -> bool:
    return str(configuration.get("enable_daily", "false")).lower() == "true" and bool(configuration.get("arcgis_token"))


def schema(configuration: dict):
    tables = [
        {"table": "ports", "primary_key": ["location_id"], "columns": LOCATION_COLUMNS},
        {"table": "chokepoints", "primary_key": ["location_id"], "columns": LOCATION_COLUMNS},
        {
            "table": "disruptions",
            "primary_key": ["event_id"],
            "columns": {
                "event_id": "LONG",
                "from_date": "UTC_DATETIME",
                "to_date": "UTC_DATETIME",
                "edit_date": "UTC_DATETIME",
                "lat": "DOUBLE",
                "lon": "DOUBLE",
                "n_affected_ports": "INT",
            },
        },
    ]
    if daily_enabled(configuration):
        for name in ("daily_ports", "daily_chokepoints"):
            tables.append({"table": name, "primary_key": ["location_id", "day"],
                           "columns": {"location_id": "STRING", "day": "NAIVE_DATE"}})
    return tables


def catalogue_due(state: dict, today: date) -> bool:
    """Catalogues are re-read once per calendar month."""
    return state.get("catalogue_month") != today.strftime("%Y-%m")


def update(configuration: dict, state: dict):
    now = datetime.now(timezone.utc)
    today = now.date()
    new_state = dict(state)

    if catalogue_due(state, today):
        ports = portwatch.fetch_ports()
        chokes = portwatch.fetch_chokepoints()
        for row in ports:
            op.upsert(table="ports", data=row)
        for row in chokes:
            op.upsert(table="chokepoints", data=row)
        new_state["catalogue_month"] = today.strftime("%Y-%m")
        log.info(f"PortWatch: {len(ports)} ports, {len(chokes)} chokepoints")
        op.checkpoint(new_state)

    last_edit = state.get("last_edit_date")
    since = date.fromisoformat(last_edit) - timedelta(days=1) if last_edit else None
    disruptions = portwatch.fetch_disruptions(since)
    for row in disruptions:
        op.upsert(table="disruptions", data=row)
    edits = [r["edit_date"] for r in disruptions if r.get("edit_date")]
    if edits:
        new_state["last_edit_date"] = max(edits)[:10]
    log.info(f"PortWatch: {len(disruptions)} disruptions")

    if daily_enabled(configuration):
        token = configuration["arcgis_token"]
        last_day = state.get("last_daily_day")
        since_day = date.fromisoformat(last_day) - timedelta(days=2) if last_day else today - timedelta(days=30)
        for table, fetch in (("daily_ports", portwatch.fetch_daily_ports),
                             ("daily_chokepoints", portwatch.fetch_daily_chokepoints)):
            rows = fetch(since=since_day, token=token)
            for row in rows:
                op.upsert(table=table, data=row)
            if rows:
                new_state["last_daily_day"] = max(max(r["day"] for r in rows), new_state.get("last_daily_day", ""))
            log.info(f"PortWatch: {len(rows)} rows in {table}")

    op.checkpoint(new_state)


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
