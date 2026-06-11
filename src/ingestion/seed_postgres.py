"""
Seed PostgreSQL with the same demo data used by the BigQuery seed loader.

The seed rows are loaded from src/ingestion/seed_data.py with BigQuery calls
stubbed out, so this script preserves the existing demo data without touching
the BigQuery seeding code.
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from src.ingestion.init_postgres import TABLE_IDS, postgres_connection, quote_ident

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


class WriteDisposition:
    WRITE_APPEND = "WRITE_APPEND"
    WRITE_TRUNCATE = "WRITE_TRUNCATE"


class BigQueryStub:
    WriteDisposition = WriteDisposition


class SeedSourceStripper(ast.NodeTransformer):
    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module and (
            node.module.startswith("google")
            or node.module == "dotenv"
            or node.module == "src.ingestion.bq_client"
        ):
            return None
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if node.name == "load_rows":
            return None
        return node

    def visit_Expr(self, node: ast.Expr):
        if (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "load_dotenv"
        ):
            return None
        return node


def load_seed_namespace(load_rows) -> dict[str, Any]:
    source_path = Path(__file__).with_name("seed_data.py")
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    tree = SeedSourceStripper().visit(tree)
    ast.fix_missing_locations(tree)

    namespace = {
        "__name__": "src.ingestion.seed_data",
        "__file__": str(source_path),
        "bigquery": BigQueryStub,
        "load_rows": load_rows,
        "os": os,
    }
    exec(compile(tree, str(source_path), "exec"), namespace)
    return namespace


def insert_rows(cur, table_id: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return

    columns = list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    column_sql = ", ".join(quote_ident(column) for column in columns)
    sql = f"INSERT INTO {quote_ident(table_id)} ({column_sql}) VALUES ({placeholders})"

    values = [tuple(row.get(column) for column in columns) for row in rows]
    cur.executemany(sql, values)


def seed_postgres_tables() -> None:
    logger.info("Seeding PostgreSQL tables in Neon.")
    try:
        with postgres_connection() as conn:
            with conn.cursor() as cur:

                def load_rows(table_id: str, rows: list[dict[str, Any]], write_disposition=WriteDisposition.WRITE_TRUNCATE):
                    if table_id not in TABLE_IDS:
                        return

                    if write_disposition == WriteDisposition.WRITE_TRUNCATE:
                        cur.execute(f"TRUNCATE TABLE {quote_ident(table_id)}")
                        logger.info("Truncated table: %s", table_id)

                    insert_rows(cur, table_id, rows)
                    logger.info("Loaded %s rows into %s", len(rows), table_id)

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

            conn.commit()

        logger.info("PostgreSQL seed data loaded successfully into Neon.")
    except Exception:
        logger.exception("PostgreSQL seeding failed.")
        raise


if __name__ == "__main__":
    seed_postgres_tables()
