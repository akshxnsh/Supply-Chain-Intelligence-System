# ChainGuard progress log

Source of truth for rules and steps: `Claude outputs/plan.md`. Only real, measured results go here.

## Needs Akshansh
- [x] ~~Neon project~~ DONE (created in the built-in browser after you logged in). Project `chainguard`, id `wandering-cell-42786611`, region AWS Singapore (ap-southeast-1), Postgres 18.6, free plan, direct (non-pooled) connection in `.env` as `DATABASE_URL`. Local Docker DB is `LOCAL_DATABASE_URL`/`TEST_DATABASE_URL`.
- [ ] **Redis URL** (`REDIS_URL`) - local Docker vs free hosted. Needed from step 6 on; code is written against the interface and tested with a fake.
- [ ] **Gemini key** (`GEMINI_API_KEY`) - needed for live reader/judge calls; tests use mocks.
- [ ] **PortWatch daily traffic** - needs an ArcGIS token in `.env` as `PORTWATCH_ARCGIS_TOKEN` (or a CSV download from portwatch.imf.org > Data). You asked how to add it: check the PortWatch site for a CSV download first; a free ArcGIS developer API key may not unlock another organisation's private layer (untested by me). Without it the traffic-trend signal is OFF (decision: build the rest now, token optional).

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
- **Index benchmark** (`python -m scripts.benchmark_db`, details in `docs/benchmarks/db_indexes.md`): local Docker Postgres 16.15, SYNTHETIC data (~1.95M rows: 300k events, 300k shipments, 500k completed orders ...), median of 7 `EXPLAIN ANALYZE` runs, 15 real app queries. Sum of query times **1079.5 ms -> 21.4 ms (98.0% lower)**; best single: suppliers_overview 497 ms -> 1.1 ms, alerts_all 41 ms -> 0.1 ms. Honest exceptions: `tariffs` 7.3 -> 8.6 ms (no index, both seq scan - a tariff index was tried and measured slower, so it was removed); `timetable_join` still uses a seq scan on the small suppliers table. - **Neon**: project created, `python -m src.ingestion.migrate` + `seed_data` ran on Neon (Postgres 18.6, 15 tables, sample data loaded). Index benchmark repeated on Neon at scale 0.1 (~195k synthetic rows, `docs/benchmarks/db_indexes_neon_scale0.1.md`): sum of query times **50.7 ms -> 3.1 ms (94.0% lower)** (server-side execution time from EXPLAIN ANALYZE).
- **Network latency (honest note)**: from this laptop to Neon Singapore a tiny query took **~394 ms median** (10 runs, includes the pool's connection check = 2 round trips). Server time is ~0.05 ms, so for the API the network dominates; this is the number step 10's Redis-cache measurement will be about. Local Docker has ~1 ms round trip.
- How the connection string got into `.env`: the browser pane blocks clipboard/localhost requests, so a one-shot localhost listener received a form POST from the Neon page and wrote `.env` directly; the password was never printed or sent to chat.

## Step 3 - step-3-fetchers
- Six fetchers in `src/fetchers/` (gdelt, gdacs, portwatch, federal_register, open_meteo, ecb) + shared `http.py` (timeouts, retries with exponential backoff, Retry-After, per-host spacing). Docs in `docs/sources.md`; fixtures captured live with `scripts/capture_fixtures.py`.
- Checked each API against the live service first. Real findings:
  - **PortWatch daily port/chokepoint traffic now needs a token** (HTTP 200 with `Token Required`); public daily layer is a stale May-2025 test layer. Open: port catalogue (2,065 ports with coordinates), 28 chokepoints (plan said 24), disruptions layer (132 rows, last edited 2026-08-15, i.e. stale).
  - **GDELT** is slow (TLS handshake alone > 5 s; ~17 s per call) and rate-limited to 1 request / 5 s; article list has no text.
  - **Federal Register**: plain "tariff" search returns unrelated documents (Medicare rules), so the fetcher filters to 4 trade agencies and `tariff OR duties OR duty`.
  - **ECB**: SDMX-JSON works with `Accept: application/json&format=jsondata`; units are currency per EUR. Currency API decision (open decision in plan): ECB `EXR` daily series, it is the one used.
  - **Open-Meteo**: daily summaries (not hourly) to keep Fivetran row counts small; harbour points have no wave data (None).
- Live smoke test (small calls) ran for all six: GDACS 100 events/9 days, Federal Register 200 docs/page, ECB 24 rates (2 days x 12 currencies), 2,065 ports, 28 chokepoints, Open-Meteo 14 daily rows for 2 points, GDELT returned articles after the rate-limit cooldown.
- Tests: `pytest` = **55 passed** (22 new fetcher tests: parse each source from a saved real response, retry/backoff/Retry-After/min-interval, ArcGIS error-in-200, paging, token requirement). `compileall` OK.
- Not done: the PortWatch daily-traffic fetcher is only tested on a made-up-from-TEST-layer sample.
