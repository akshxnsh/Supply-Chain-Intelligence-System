"""PostgreSQL access layer (psycopg 3 + connection pool).

The pool is created lazily on first use so importing this module never needs a
database. The connection string comes from DATABASE_URL (never printed or logged).
"""

from __future__ import annotations

import atexit
import os
import threading
from typing import Any, Iterable, Sequence

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set. Put it in .env (see .env.example).")
    return url


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    database_url(),
                    min_size=int(os.getenv("DB_POOL_MIN", "1")),
                    max_size=int(os.getenv("DB_POOL_MAX", "10")),
                    kwargs={"row_factory": dict_row},
                    check=ConnectionPool.check_connection,  # drops connections Neon closed while idle
                    open=True,
                )
    return _pool


def close_pool() -> None:
    global _pool
    with _pool_lock:
        if _pool is not None:
            _pool.close()
            _pool = None


atexit.register(close_pool)


def run_query(sql: str, params: dict | Sequence | None = None) -> list[dict]:
    """Run a SELECT (or INSERT/UPDATE ... RETURNING) and return rows as dicts."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall()) if cur.description else []


def execute(sql: str, params: dict | Sequence | None = None) -> int:
    """Run a statement that returns no rows. Returns the affected row count."""
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def insert_rows(table: str, rows: Iterable[dict[str, Any]], truncate: bool = False) -> int:
    """Insert dict rows (all rows must share the first row's keys). Table/column names are ours, values are bound."""
    rows = list(rows)
    if not rows:
        return 0
    columns = list(rows[0].keys())
    col_sql = ", ".join(quote_ident(c) for c in columns)
    ph = ", ".join(["%s"] * len(columns))
    sql = f"INSERT INTO {quote_ident(table)} ({col_sql}) VALUES ({ph})"
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            if truncate:
                cur.execute(f"TRUNCATE TABLE {quote_ident(table)}")
            cur.executemany(sql, [tuple(r.get(c) for c in columns) for r in rows])
    return len(rows)


def connect(**kwargs) -> psycopg.Connection:
    """One-off (non-pooled) connection, for scripts such as migrations and benchmarks."""
    return psycopg.connect(database_url(), row_factory=dict_row, **kwargs)
