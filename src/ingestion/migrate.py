"""Apply db/migrations/*.sql in filename order. Each file runs once (tracked in schema_migrations).

    python -m src.ingestion.migrate            # apply pending migrations
    python -m src.ingestion.migrate --status   # list applied / pending
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.ingestion.db import connect

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"
logger = logging.getLogger(__name__)


def migration_files(directory: Path = MIGRATIONS_DIR) -> list[Path]:
    return sorted(directory.glob("*.sql"))


def apply_migrations(conn, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations on an open connection; returns the names applied."""
    applied: list[str] = []
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        cur.execute("SELECT name FROM schema_migrations")
        done = {r["name"] for r in cur.fetchall()}
    conn.commit()

    for path in migration_files(directory):
        if path.name in done:
            continue
        with conn.cursor() as cur:
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
        conn.commit()  # one transaction per file
        applied.append(path.name)
        logger.info("applied %s", path.name)
    return applied


def status(conn, directory: Path = MIGRATIONS_DIR) -> dict[str, list[str]]:
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        cur.execute("SELECT name FROM schema_migrations ORDER BY name")
        done = [r["name"] for r in cur.fetchall()]
    conn.commit()
    pending = [p.name for p in migration_files(directory) if p.name not in done]
    return {"applied": done, "pending": pending}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()
    with connect() as conn:
        if args.status:
            print(status(conn))
        else:
            applied = apply_migrations(conn)
            print(f"applied: {applied or 'nothing (up to date)'}")


if __name__ == "__main__":
    main()
