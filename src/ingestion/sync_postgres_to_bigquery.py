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

from dotenv import load_dotenv
from google.cloud import bigquery

from src.ingestion.bq_client import DATASET, PROJECT_ID, client
from src.ingestion.init_postgres import TABLE_IDS, load_bigquery_table_definitions

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SOURCE_SCHEMA = "google_sheets"


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


def postgres_table_ref(table_id: str) -> str:
    return f"{SOURCE_SCHEMA}.{table_id}"


def bq_table_ref(table_id: str) -> str:
    return f"`{PROJECT_ID}.{DATASET}.{table_id}`"


def bq_table_id(table_id: str) -> str:
    return f"{PROJECT_ID}.{DATASET}.{table_id}"


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


def filter_rows_to_bq_schema(
    table_id: str,
    rows: list[dict[str, Any]],
    schema: list[bigquery.SchemaField],
) -> list[dict[str, Any]]:
    schema_fields = {field.name for field in schema}
    filtered_rows = [{
        key: value
        for key, value in row.items()
        if key in schema_fields
    } for row in rows]

    original_column_count = len(rows[0]) if rows else 0
    filtered_column_count = len(filtered_rows[0]) if filtered_rows else 0
    logger.info(
        "%s: original column count=%s, filtered column count=%s",
        table_id,
        original_column_count,
        filtered_column_count,
    )
    return filtered_rows


def fetch_postgres_rows(table_id: str) -> list[dict[str, Any]]:
    with neon_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {postgres_table_ref(table_id)}")
            return [normalize_row(dict(row)) for row in cur.fetchall()]


def replace_bigquery_table(table_id: str, rows: list[dict[str, Any]]) -> int:
    schema = bq_schema_for(table_id)
    filtered_rows = filter_rows_to_bq_schema(table_id, rows, schema)
    job_config = bigquery.LoadJobConfig(
        schema=schema,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    job = client.load_table_from_json(filtered_rows, bq_table_id(table_id), job_config=job_config)
    job.result()
    logger.info("%s: loaded %s rows into BigQuery", table_id, len(filtered_rows))
    logger.info("%s: table replaced successfully", table_id)
    return len(filtered_rows)


def sync_table(table_id: str) -> bool:
    if table_id not in TABLE_IDS:
        raise ValueError(f"Unsupported table {table_id!r}. Expected one of: {', '.join(TABLE_IDS)}")

    try:
        rows = fetch_postgres_rows(table_id)
        logger.info("%s: read %s rows from PostgreSQL", table_id, len(rows))

        replace_bigquery_table(table_id, rows)
        logger.info("%s: sync complete", table_id)
        return True
    except Exception:
        logger.exception("%s: sync failed", table_id)
        return False


def postgres_count(table_id: str) -> int:
    with neon_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) AS count FROM {postgres_table_ref(table_id)}")
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
