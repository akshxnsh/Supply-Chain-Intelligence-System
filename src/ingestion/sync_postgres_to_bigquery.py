"""
Sync mirrored PostgreSQL tables from Neon into BigQuery.

Source: Neon PostgreSQL via NEON_DATABASE_URL
Destination: BigQuery via the existing src.ingestion.bq_client configuration
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from google.cloud import bigquery

from src.ingestion.bq_client import DATASET, PROJECT_ID, client
from src.ingestion.init_postgres import TABLE_IDS, load_bigquery_table_definitions

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PRIMARY_KEYS = {
    "alternative_suppliers": "id",
    "business_suppliers": "id",
    "completed_orders": "id",
    "disruption_events": "id",
    "inventory": "id",
    "pending_orders": "id",
    "port_activity": "port_id",
    "shipment_timetable": "id",
    "supplier_reviews": "id",
    "tariff_updates": "id",
    "weather_alerts": "id",
}


def neon_connection():
    dsn = os.getenv("NEON_DATABASE_URL")
    if not dsn:
        raise RuntimeError("NEON_DATABASE_URL is missing. Add it to .env before running this script.")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError("psycopg is required. Install it with: pip install psycopg[binary]") from exc

    return psycopg.connect(dsn, row_factory=dict_row)


def quote_pg(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def bq_table_ref(table_id: str) -> str:
    return f"`{PROJECT_ID}.{DATASET}.{table_id}`"


def normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: normalize_value(value) for key, value in row.items()}


def bq_schema_for(table_id: str) -> list[bigquery.SchemaField]:
    tables = load_bigquery_table_definitions()
    return [
        bigquery.SchemaField(field.name, field.field_type, mode=field.mode)
        for field in tables[table_id]["schema"]
    ]


def fetch_postgres_rows(table_id: str) -> list[dict[str, Any]]:
    with neon_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {quote_pg(table_id)}")
            return [normalize_row(dict(row)) for row in cur.fetchall()]


def load_staging_table(table_id: str, rows: list[dict[str, Any]]) -> str:
    staging_table_id = f"_staging_{table_id}_{uuid4().hex[:12]}"
    staging_ref = f"{PROJECT_ID}.{DATASET}.{staging_table_id}"
    table = bigquery.Table(staging_ref, schema=bq_schema_for(table_id))
    client.create_table(table)

    if rows:
        job_config = bigquery.LoadJobConfig(
            schema=table.schema,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        job = client.load_table_from_json(rows, staging_ref, job_config=job_config)
        job.result()

    return staging_table_id


def merge_staging_into_target(table_id: str, staging_table_id: str, columns: list[str]) -> tuple[int, int]:
    primary_key = PRIMARY_KEYS[table_id]
    update_columns = [column for column in columns if column != primary_key]

    update_sql = ", ".join(
        f"T.`{column}` = S.`{column}`"
        for column in update_columns
    )
    insert_columns = ", ".join(f"`{column}`" for column in columns)
    insert_values = ", ".join(f"S.`{column}`" for column in columns)

    sql = f"""
        MERGE {bq_table_ref(table_id)} T
        USING {bq_table_ref(staging_table_id)} S
        ON T.`{primary_key}` = S.`{primary_key}`
        WHEN MATCHED THEN
          UPDATE SET {update_sql}
        WHEN NOT MATCHED THEN
          INSERT ({insert_columns}) VALUES ({insert_values})
    """

    job = client.query(sql)
    job.result()

    dml_stats = getattr(job, "dml_stats", None)
    inserted = int(getattr(dml_stats, "inserted_row_count", 0) or 0)
    updated = int(getattr(dml_stats, "updated_row_count", 0) or 0)
    return inserted, updated


def sync_table(table_id: str) -> bool:
    if table_id not in TABLE_IDS:
        raise ValueError(f"Unsupported table {table_id!r}. Expected one of: {', '.join(TABLE_IDS)}")

    staging_table_id = None
    try:
        rows = fetch_postgres_rows(table_id)
        logger.info("%s: read %s rows from PostgreSQL", table_id, len(rows))

        if not rows:
            logger.info("%s: no rows to sync", table_id)
            return True

        columns = [field.name for field in bq_schema_for(table_id)]
        staging_table_id = load_staging_table(table_id, rows)
        inserted, updated = merge_staging_into_target(table_id, staging_table_id, columns)

        logger.info(
            "%s: sync complete, inserted=%s, updated=%s",
            table_id,
            inserted,
            updated,
        )
        return True
    except Exception:
        logger.exception("%s: sync failed", table_id)
        return False
    finally:
        if staging_table_id:
            client.delete_table(f"{PROJECT_ID}.{DATASET}.{staging_table_id}", not_found_ok=True)


def postgres_count(table_id: str) -> int:
    with neon_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS count FROM {quote_pg(table_id)}")
            row = cur.fetchone()
            return int(row["count"])


def bigquery_count(table_id: str) -> int:
    rows = client.query(f"SELECT COUNT(*) AS count FROM {bq_table_ref(table_id)}").result()
    return int(next(rows)["count"])


def verify_counts(table_ids: list[str]) -> bool:
    ok = True
    for table_id in table_ids:
        try:
            pg_count = postgres_count(table_id)
            bq_count = bigquery_count(table_id)
            status = "OK" if pg_count == bq_count else "MISMATCH"
            if pg_count != bq_count:
                ok = False
            logger.info(
                "%s: PostgreSQL=%s BigQuery=%s %s",
                table_id,
                pg_count,
                bq_count,
                status,
            )
        except Exception:
            ok = False
            logger.exception("%s: verification failed", table_id)
    return ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Neon PostgreSQL tables to BigQuery.")
    parser.add_argument("--table", choices=TABLE_IDS, help="Sync or verify a single table.")
    parser.add_argument("--verify", action="store_true", help="Print PostgreSQL vs BigQuery row counts.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    table_ids = [args.table] if args.table else TABLE_IDS

    if args.verify:
        return 0 if verify_counts(table_ids) else 1

    successes = 0
    for table_id in table_ids:
        if sync_table(table_id):
            successes += 1

    failures = len(table_ids) - successes
    logger.info("Sync finished: succeeded=%s failed=%s", successes, failures)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
