"""
PostgreSQL table initialization for the demo ingestion pipeline.

This script derives PostgreSQL DDL from the BigQuery schema definitions in
src/ingestion/init_tables.py, but it does not connect to BigQuery.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TABLE_IDS = [
    "alternative_suppliers",
    "business_suppliers",
    "completed_orders",
    "disruption_events",
    "inventory",
    "pending_orders",
    "port_activity",
    "shipment_timetable",
    "supplier_reviews",
    "tariff_updates",
    "weather_alerts",
]

TYPE_MAP = {
    "STRING": "TEXT",
    "INTEGER": "BIGINT",
    "FLOAT": "DOUBLE PRECISION",
    "TIMESTAMP": "TIMESTAMPTZ",
    "DATE": "DATE",
    "BOOLEAN": "BOOLEAN",
}


class SchemaField:
    def __init__(self, name: str, field_type: str, mode: str = "NULLABLE"):
        self.name = name
        self.field_type = field_type
        self.mode = mode


class BigQueryStub:
    SchemaField = SchemaField

    class Client:
        def __init__(self, *args, **kwargs):
            pass

    class Table:
        def __init__(self, *args, **kwargs):
            pass


class ServiceAccountStub:
    class Credentials:
        @staticmethod
        def from_service_account_file(*args, **kwargs):
            return None


class ImportStripper(ast.NodeTransformer):
    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and (
            node.module.startswith("google")
            or node.module == "dotenv"
        ):
            return None
        return node


def load_bigquery_table_definitions() -> dict:
    """Load TABLES from init_tables.py with BigQuery imports stubbed out."""
    source_path = Path(__file__).with_name("init_tables.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    tree = ImportStripper().visit(tree)
    ast.fix_missing_locations(tree)

    namespace = {
        "__name__": "src.ingestion.init_tables",
        "__file__": str(source_path),
        "bigquery": BigQueryStub,
        "service_account": ServiceAccountStub,
        "os": os,
        "load_dotenv": lambda *args, **kwargs: None,
    }
    exec(compile(tree, str(source_path), "exec"), namespace)
    return namespace["TABLES"]


def postgres_connection():
    dsn = os.getenv("NEON_DATABASE_URL")
    if not dsn:
        raise RuntimeError("NEON_DATABASE_URL is missing. Add it to .env before running this script.")

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("psycopg is required to connect to Neon. Install it with: pip install psycopg[binary]") from exc

    return psycopg.connect(dsn)


def quote_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def column_ddl(field: SchemaField) -> str:
    pg_type = TYPE_MAP.get(field.field_type.upper())
    if not pg_type:
        raise ValueError(f"Unsupported BigQuery type {field.field_type!r} for {field.name}")

    nullable = "" if field.mode == "REQUIRED" else " NULL"
    not_null = " NOT NULL" if field.mode == "REQUIRED" else nullable
    return f"{quote_ident(field.name)} {pg_type}{not_null}"


def create_table_sql(table_id: str, schema: list[SchemaField]) -> str:
    columns = ",\n    ".join(column_ddl(field) for field in schema)
    return f"CREATE TABLE IF NOT EXISTS {quote_ident(table_id)} (\n    {columns}\n);"


def init_postgres_tables() -> None:
    logger.info("Initializing PostgreSQL tables in Neon.")
    try:
        tables = load_bigquery_table_definitions()

        with postgres_connection() as conn:
            with conn.cursor() as cur:
                for table_id in TABLE_IDS:
                    schema = tables[table_id]["schema"]
                    cur.execute(create_table_sql(table_id, schema))
                    logger.info("Created or verified table: %s", table_id)
            conn.commit()

        logger.info("PostgreSQL tables initialized successfully in Neon.")
    except Exception:
        logger.exception("PostgreSQL table initialization failed.")
        raise


def verify_postgres_tables() -> bool:
    logger.info("Verifying PostgreSQL tables in Neon.")
    try:
        with postgres_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(%s::text[])
                    ORDER BY table_name
                    """,
                    (TABLE_IDS,),
                )
                existing = {row[0] for row in cur.fetchall()}

        missing = sorted(set(TABLE_IDS) - existing)
        if missing:
            logger.error("Missing PostgreSQL tables: %s", ", ".join(missing))
            return False

        logger.info("All expected PostgreSQL tables exist: %s", ", ".join(sorted(existing)))
        return True
    except Exception:
        logger.exception("PostgreSQL table verification failed.")
        raise


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        raise SystemExit(0 if verify_postgres_tables() else 1)

    init_postgres_tables()
