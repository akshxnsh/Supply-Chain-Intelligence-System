import os
import uuid

import pytest

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("PHOENIX_API_KEY", "")


@pytest.fixture(scope="session")
def pg_url():
    """A real PostgreSQL scoped to a throwaway schema with all migrations applied.

    Skipped when TEST_DATABASE_URL is not set. Sets DATABASE_URL for the session so the
    app's own db layer talks to the scratch schema.
    """
    from dotenv import load_dotenv

    load_dotenv()
    base = os.getenv("TEST_DATABASE_URL")
    if not base:
        pytest.skip("TEST_DATABASE_URL not set")
    import psycopg
    from psycopg.rows import dict_row

    from src.ingestion import db
    from src.ingestion.migrate import apply_migrations

    schema = f"t_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(base, autocommit=True) as c:
        c.execute(f'CREATE SCHEMA "{schema}"')
    sep = "&" if "?" in base else "?"
    scoped = f"{base}{sep}options=-csearch_path%3D{schema}"
    old = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = scoped
    db.close_pool()
    with psycopg.connect(scoped, row_factory=dict_row) as conn:
        apply_migrations(conn)
    yield scoped
    db.close_pool()
    if old is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = old
    with psycopg.connect(base, autocommit=True) as c:
        c.execute(f'DROP SCHEMA "{schema}" CASCADE')
