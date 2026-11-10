"""Fivetran custom connector: GDELT news articles -> table `articles` (primary key article_id).

Incremental: each sync asks GDELT only for the hours since the last successful sync (state.last_run),
capped at 24 h. An article seen twice has the same article_id, so the upsert is idempotent.
The fetch code is the plain fetcher in chainguard_fetchers/gdelt.py (copy of src/fetchers/gdelt.py).
"""

import math
from datetime import datetime, timezone

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from chainguard_fetchers import gdelt

MAX_HOURS = 24


def schema(configuration: dict):
    return [
        {
            "table": "articles",
            "primary_key": ["article_id"],
            "columns": {"article_id": "STRING", "seen_at": "UTC_DATETIME"},
        }
    ]


def hours_to_fetch(state: dict, now: datetime) -> int:
    """Whole hours since the last successful sync (+1 overlap), between 1 and MAX_HOURS."""
    last = state.get("last_run")
    if not last:
        return MAX_HOURS
    delta_h = (now - datetime.fromisoformat(last)).total_seconds() / 3600
    return max(1, min(MAX_HOURS, math.ceil(delta_h) + 1))


def update(configuration: dict, state: dict):
    now = datetime.now(timezone.utc)
    hours = hours_to_fetch(state, now)
    log.info(f"GDELT: fetching the last {hours} h")
    rows = gdelt.fetch_all(timespan=f"{hours}h")
    for row in rows:
        # upsert: insert the article, or update it if article_id already exists
        op.upsert(table="articles", data=row)
    # checkpoint: save progress; the next sync only asks for what is newer than `now`
    op.checkpoint({"last_run": now.isoformat()})
    log.info(f"GDELT: {len(rows)} articles")


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
