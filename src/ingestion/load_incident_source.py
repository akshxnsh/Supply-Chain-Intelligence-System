"""
Load the Baltimore INCIDENT dataset into the Neon Postgres `google_sheets`
schema — the source that FreshnessAgent's sync_postgres_to_bigquery reads from.

Background
----------
Production data path:

    Google Sheets ──Fivetran connector──▶ Neon Postgres (schema: google_sheets)
                  ──sync_postgres_to_bigquery (WRITE_TRUNCATE)──▶ BigQuery

`sync_postgres_to_bigquery.sync_table()` reads from `google_sheets.<table>`
(see SOURCE_SCHEMA there). In production Fivetran fills that schema from the
"Supply Chain Data" workbook (init_google_sheets.py --seed writes the incident
rows to the workbook). This helper does the equivalent directly against Postgres
so the FreshnessAgent transition is demonstrable WITHOUT a live Fivetran/Sheets
round-trip: it stages the exact Baltimore incident dataset from seed_data.py into
`google_sheets.<table>`.

Demo role
---------
Run this ONCE to stage the incident in the source. BigQuery still holds the
healthy baseline (seed_baseline_data.py) and is untouched. When FreshnessAgent
later runs refresh_stale_table / refresh_all_stale_tables, sync_table() pulls
these rows into BigQuery (WRITE_TRUNCATE), flipping the scenario to the incident.

Usage
-----
    python -m src.ingestion.load_incident_source            # stage all tables
    python -m src.ingestion.load_incident_source --verify   # print row counts
"""

from __future__ import annotations

import argparse
import logging
from typing import Any

from dotenv import load_dotenv

from src.ingestion.init_postgres import (
    TABLE_IDS,
    TYPE_MAP,
    load_bigquery_table_definitions,
    postgres_connection,
    quote_ident,
)
from src.ingestion.seed_postgres import WriteDisposition, load_seed_namespace

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Must match sync_postgres_to_bigquery.SOURCE_SCHEMA.
SOURCE_SCHEMA = "google_sheets"


def qualified(table_id: str) -> str:
    return f"{quote_ident(SOURCE_SCHEMA)}.{quote_ident(table_id)}"


def column_ddl(field) -> str:
    pg_type = TYPE_MAP.get(field.field_type.upper())
    if not pg_type:
        raise ValueError(f"Unsupported BigQuery type {field.field_type!r} for {field.name}")
    not_null = " NOT NULL" if field.mode == "REQUIRED" else " NULL"
    return f"{quote_ident(field.name)} {pg_type}{not_null}"


def create_schema_and_tables(cur, tables: dict[str, Any]) -> None:
    cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quote_ident(SOURCE_SCHEMA)}")
    for table_id in TABLE_IDS:
        columns = ",\n    ".join(column_ddl(f) for f in tables[table_id]["schema"])
        cur.execute(f"CREATE TABLE IF NOT EXISTS {qualified(table_id)} (\n    {columns}\n);")
        logger.info("Created or verified source table: %s.%s", SOURCE_SCHEMA, table_id)


def collect_incident_rows() -> dict[str, list[dict[str, Any]]]:
    """Collect the Baltimore incident rows from seed_data.py (BigQuery stubbed out)."""
    incident_rows: dict[str, list[dict[str, Any]]] = {table_id: [] for table_id in TABLE_IDS}

    def load_rows(table_id: str, rows: list[dict[str, Any]], write_disposition=WriteDisposition.WRITE_TRUNCATE):
        if table_id not in incident_rows:
            return
        if write_disposition == WriteDisposition.WRITE_TRUNCATE:
            incident_rows[table_id] = []
        incident_rows[table_id].extend(rows)

    seed = load_seed_namespace(load_rows)
    seed["seed_business_suppliers"]()
    seed["seed_pending_orders"]()
    seed["seed_shipment_timetable"]()
    seed["seed_alternative_suppliers"]()
    seed["seed_port_activity"]()
    seed["seed_disruption_events"]()
    seed["seed_weather_alerts"]()
    seed["seed_tariff_updates"]()
    seed["seed_inventory"]()
    seed["seed_completed_orders"]()
    seed["seed_supplier_reviews"]()
    return incident_rows


def insert_rows(cur, table_id: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(quote_ident(c) for c in columns)
    sql = f"INSERT INTO {qualified(table_id)} ({column_sql}) VALUES ({placeholders})"
    values = [tuple(row.get(c) for c in columns) for row in rows]
    cur.executemany(sql, values)


def stage_incident_source() -> None:
    logger.info("Staging Baltimore incident dataset into Neon schema %r.", SOURCE_SCHEMA)
    tables = load_bigquery_table_definitions()
    incident_rows = collect_incident_rows()

    with postgres_connection() as conn:
        with conn.cursor() as cur:
            create_schema_and_tables(cur, tables)
            for table_id in TABLE_IDS:
                rows = incident_rows[table_id]
                cur.execute(f"TRUNCATE TABLE {qualified(table_id)}")
                insert_rows(cur, table_id, rows)
                logger.info("Staged %s rows into %s.%s", len(rows), SOURCE_SCHEMA, table_id)
        conn.commit()

    logger.info("Incident dataset staged. FreshnessAgent sync will now deliver it to BigQuery.")


def verify_counts() -> None:
    with postgres_connection() as conn:
        with conn.cursor() as cur:
            for table_id in TABLE_IDS:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {qualified(table_id)}")
                    count = cur.fetchone()[0]
                    logger.info("%s.%s: %s rows", SOURCE_SCHEMA, table_id, count)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s.%s: not staged (%s)", SOURCE_SCHEMA, table_id, exc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage the Baltimore incident dataset into the Postgres source schema.")
    parser.add_argument("--verify", action="store_true", help="Print staged row counts instead of writing.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.verify:
        verify_counts()
    else:
        stage_incident_source()
