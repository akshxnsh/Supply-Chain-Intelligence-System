"""Fivetran custom connector: ECB euro reference rates -> table `exchange_rates`
(primary key currency + rate_date).

Incremental: asks for rates from state.last_rate_date (inclusive) onward; first sync reads the last
`initial_days` (default 90). ECB publishes on working days only.
"""

from datetime import date, datetime, timedelta, timezone

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from chainguard_fetchers import ecb

DEFAULT_INITIAL_DAYS = 90


def schema(configuration: dict):
    return [
        {
            "table": "exchange_rates",
            "primary_key": ["currency", "rate_date"],
            "columns": {"currency": "STRING", "rate_date": "NAIVE_DATE", "eur_rate": "DOUBLE"},
        }
    ]


def start_date(configuration: dict, state: dict, today: date) -> date:
    last = state.get("last_rate_date")
    if last:
        return date.fromisoformat(last)
    return today - timedelta(days=int(configuration.get("initial_days", DEFAULT_INITIAL_DAYS)))


def currencies(configuration: dict) -> tuple[str, ...]:
    raw = configuration.get("currencies")
    return tuple(c.strip().upper() for c in raw.split(",") if c.strip()) if raw else ecb.DEFAULT_CURRENCIES


def update(configuration: dict, state: dict):
    today = datetime.now(timezone.utc).date()
    since = start_date(configuration, state, today)
    rows = ecb.fetch_rates(currencies(configuration), since=since)
    for row in rows:
        op.upsert(table="exchange_rates", data=row)
    last = max([r["rate_date"] for r in rows] + [since.isoformat()])
    op.checkpoint({"last_rate_date": last})
    log.info(f"ECB: {len(rows)} rates since {since}")


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
