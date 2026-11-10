"""Fivetran custom connector: Federal Register trade documents -> table `documents` (primary key document_number).

Incremental: asks only for documents published on/after state.last_publication_date (inclusive, so a
same-day document is never missed; the upsert makes the overlap harmless). First sync reads the last
`initial_days` (configuration, default 60).
"""

from datetime import date, datetime, timedelta, timezone

from fivetran_connector_sdk import Connector
from fivetran_connector_sdk import Logging as log
from fivetran_connector_sdk import Operations as op

from chainguard_fetchers import federal_register

DEFAULT_INITIAL_DAYS = 60


def schema(configuration: dict):
    return [
        {
            "table": "documents",
            "primary_key": ["document_number"],
            "columns": {
                "document_number": "STRING",
                "publication_date": "NAIVE_DATE",
                "effective_on": "NAIVE_DATE",
                "comments_close_on": "NAIVE_DATE",
            },
        }
    ]


def start_date(configuration: dict, state: dict, today: date) -> date:
    last = state.get("last_publication_date")
    if last:
        return date.fromisoformat(last)
    return today - timedelta(days=int(configuration.get("initial_days", DEFAULT_INITIAL_DAYS)))


def update(configuration: dict, state: dict):
    today = datetime.now(timezone.utc).date()
    since = start_date(configuration, state, today)
    log.info(f"Federal Register: documents published since {since}")
    rows = federal_register.fetch_documents(since=since)
    for row in rows:
        op.upsert(table="documents", data=row)
    dates = [r["publication_date"] for r in rows if r.get("publication_date")]
    new_last = max(dates + [since.isoformat()])
    op.checkpoint({"last_publication_date": new_last})
    log.info(f"Federal Register: {len(rows)} documents")


connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
