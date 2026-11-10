# ChainGuard progress log

Source of truth for rules and steps: `Claude outputs/plan.md`. Only real, measured results go here.

## Needs Akshansh
- [ ] **Neon project + `DATABASE_URL`** - create project `chainguard` in your own browser (Zen), put the connection string in `.env` as `DATABASE_URL` (not in chat). Claude could not drive Zen. Until then everything runs on local Docker Postgres (`localhost:55432`, container `chainguard-pg`).
- [ ] **Redis URL** (`REDIS_URL`) - local Docker vs free hosted. Needed from step 6 on; code is written against the interface and tested with a fake.
- [ ] **Gemini key** (`GEMINI_API_KEY`) - needed for live reader/judge calls; tests use mocks.
- [ ] **PortWatch daily data decision** - see step 3.

## Small choices made (no pause needed)
- Commit trailer: only `Co-Authored-By` is added. The plan also mentions a `Claude-Session` line, but no session id is available to me.
- Local dev DB: Docker `postgres:16` on port 55432 (Docker Desktop was started by Claude).
- psycopg 3 + `psycopg_pool` (lazy pool, so importing code never needs a database).
- `bq_client.py` was renamed (git mv) to `src/ingestion/queries.py`; function names kept, so callers only changed their import path.
- Every table got an `updated_at` column; freshness = newest `updated_at` (Postgres has no "table modified" metadata like BigQuery).
- Freshness agent: the Postgres->BigQuery sync tool was removed; "refresh" now = trigger Fivetran connector, wait, re-check freshness. Tool `check_bigquery_table_freshness` renamed `check_table_freshness` (two label edits in the React `TraceScreen.jsx` / `FreshnessScreen.jsx`).
- Old Google-Sheets -> Postgres -> BigQuery demo scripts deleted (`init_google_sheets`, `load_incident_source`, `sync_postgres_to_bigquery`, `init_tables`, `init_postgres`, `seed_postgres`, `verify_tables`). They are in git history.
- `.gitignore` ignored `.env.example` too; added `!.env.example`.
- Fixed `query_recent_cycle_performance`: it compared JSON booleans to the string `"True"` (always false); now case-insensitive.

## Baseline before step 2 (branch step-1-cleanup)
`pytest` could not even collect: 8 of 9 test files crashed at import with Google `DefaultCredentialsError` (BigQuery client created at import). So "tests passing" was not verifiable without BigQuery credentials.

## Step 2 - step-2-postgres
- BigQuery removed (code, `google-cloud-bigquery` in requirements). New: `src/ingestion/db.py`, `queries.py`, `migrate.py`, `db/migrations/001_core_tables.sql` (PKs), `002_indexes.sql`, `scripts/benchmark_db.py`.
- requirements: added `psycopg[binary]`, `psycopg-pool`, `redis`, `google-genai` (pinned to installed versions).
- Tests after step: `pytest` = **33 passed** (24 existing incl. 2 stale tests fixed + 9 new Postgres query tests that run against a throw-away schema). `compileall` OK.
- Two stale tests fixed (they never ran before): detection test lambdas had wrong kwarg names; runtime test must set `OPTIMIZED_PIPELINE=0` (live path is the one-model-call "optimized pipeline", the ADK Runner path is legacy).
- **Index benchmark** (`python -m scripts.benchmark_db`, details in `docs/benchmarks/db_indexes.md`): local Docker Postgres 16.15, SYNTHETIC data (~1.95M rows: 300k events, 300k shipments, 500k completed orders ...), median of 7 `EXPLAIN ANALYZE` runs, 15 real app queries. Sum of query times **1079.5 ms -> 21.4 ms (98.0% lower)**; best single: suppliers_overview 497 ms -> 1.1 ms, alerts_all 41 ms -> 0.1 ms. Honest exceptions: `tariffs` 7.3 -> 8.6 ms (no index, both seq scan - a tariff index was tried and measured slower, so it was removed); `timetable_join` still uses a seq scan on the small suppliers table. These numbers are for this machine/local DB, not Neon (Neon run pending the connection string).
- Not done yet in step 2: create Neon project, migrate + seed on Neon, Neon timings.
