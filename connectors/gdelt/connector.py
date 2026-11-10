"""Fivetran custom connector: GDELT news articles -> table `articles` (primary key article_id).

GDELT's DOC API rate-limits hard (HTTP 429), so this connector is built to survive that:
  - each of our searches has its OWN cursor (state.last_run_by_query), asking only for the hours since that
    search last succeeded, capped at MAX_HOURS;
  - a search that is still rate-limited after patient retries is skipped for this run and keeps its old cursor, so
    its time window is retried next run (nothing is lost, the upsert makes overlap harmless);
  - only when EVERY search fails does the sync fail (so Fivetran shows it as failed, not as a quiet empty sync).
The fetch code is the plain fetcher in chainguard_fetchers/gdelt.py (copy of src/fetchers/gdelt.py).
"""

import math
from datetime import datetime, timezone

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from chainguard_fetchers import gdelt
from chainguard_fetchers.http import FetchError

MAX_HOURS = 72
RETRIES = 3          # per search; waits 20 s, 40 s, 80 s between tries
BACKOFF_SECONDS = 20.0


def schema(configuration: dict):
    return [
        {
            "table": "articles",
            "primary_key": ["article_id"],
            "columns": {"article_id": "STRING", "seen_at": "UTC_DATETIME"},
        }
    ]


def hours_to_fetch(last_run: str | None, now: datetime) -> int:
    """Whole hours since a search last succeeded (+1 overlap), between 1 and MAX_HOURS; MAX_HOURS if never."""
    if not last_run:
        return MAX_HOURS
    delta_h = (now - datetime.fromisoformat(last_run)).total_seconds() / 3600
    return max(1, min(MAX_HOURS, math.ceil(delta_h) + 1))


def update(configuration: dict, state: dict):
    now = datetime.now(timezone.utc)
    cursors = dict(state.get("last_run_by_query") or {})
    failures: dict[str, str] = {}
    total = 0

    for name, query in gdelt.DEFAULT_QUERIES.items():
        hours = hours_to_fetch(cursors.get(name), now)
        log.info(f"GDELT '{name}': fetching the last {hours} h")
        try:
            rows = gdelt.fetch_articles(query, query_name=name, timespan=f"{hours}h",
                                        retries=RETRIES, backoff=BACKOFF_SECONDS)
        except FetchError as exc:
            failures[name] = str(exc)
            log.warning(f"GDELT '{name}' skipped this run (cursor kept): {exc}")
            continue
        for row in rows:
            # upsert: insert the article, or update it if article_id already exists
            op.upsert(table="articles", data=row)
        total += len(rows)
        cursors[name] = now.isoformat()
        # checkpoint after every search: progress is saved even if a later search fails
        op.checkpoint({"last_run_by_query": cursors})

    if len(failures) == len(gdelt.DEFAULT_QUERIES):
        raise RuntimeError(f"GDELT: every search failed: {failures}")
    log.info(f"GDELT: {total} articles; skipped searches: {sorted(failures)}")


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
