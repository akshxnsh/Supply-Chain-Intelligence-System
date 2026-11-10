# Fivetran: how the data gets into Postgres

```
free public APIs --> src/fetchers/*.py (plain Python, unit tested)
                      \--> connectors/<source>/connector.py  (thin Fivetran Connector SDK wrapper)
                              \--> Fivetran (schedule, state, table/column creation, loading)
                                      \--> Neon Postgres, one schema per connection
```

## What we write vs what Fivetran does
- **We write**: the API calls (`src/fetchers`), and per connector `schema()` (table names, primary keys, column types)
  and `update(configuration, state)` (which rows are new, what cursor to save).
- **Fivetran does**: runs `update()` on a schedule, stores the `state` we checkpoint, creates/alters tables and columns in
  the destination, de-duplicates by primary key (upsert) and adds `_fivetran_synced` / `_fivetran_deleted`.

## Built-in connector check
Checked the public Fivetran connector catalogue page (2026-11-10): there is **no built-in connector** for GDELT, GDACS,
IMF PortWatch, the Federal Register, Open-Meteo or the ECB (only an unrelated "Open Exchange Rates" connector that needs a
paid API key). So all six are custom connectors.

## Connectors
| connector folder | tables (primary key) | cursor in state | suggested schedule |
|---|---|---|---|
| `gdelt` | `articles` (article_id) | `last_run` (asks only for the hours since) | every 30 min |
| `gdacs` | `events` (event_id) | `last_run` date, 3-day overlap (events get updated) | every 3 h |
| `portwatch` | `ports`, `chokepoints` (location_id), `disruptions` (event_id); `daily_*` only with a token | `catalogue_month`, `last_edit_date` | daily |
| `federal_register` | `documents` (document_number) | `last_publication_date` | every 6 h |
| `open_meteo` | `daily_forecast` (location_id, forecast_date) | none (forecast replaced each run) | every 6 h |
| `ecb` | `exchange_rates` (currency, rate_date) | `last_rate_date` | daily |

Monthly active rows (MAR) stay far below the free 500k: rows are upserted by primary key and Fivetran counts a key once per
month. Rough monthly distinct keys: GDELT ~ a few thousand articles/day, the others a few thousand in total.

## The fetcher copies
`fivetran deploy` uploads only the connector folder, so each folder has `chainguard_fetchers/` = a copy of
`src/fetchers/http.py` + its module with the import rewritten. Regenerate with `python -m scripts.sync_connector_fetchers`
(a test fails if a copy is stale).

## Run a connector locally (no Fivetran account needed)
The SDK needs its own env (it pins grpc/protobuf). One-time:
```bash
py -3.12 -m venv .venv-fivetran && .venv-fivetran/Scripts/python -m pip install fivetran-connector-sdk==3.1.0
```
Then (Git Bash; the SDK shells out to `pipreqs`, so its Scripts folder must be on PATH, and Windows needs UTF-8):
```bash
export PATH="$PWD/.venv-fivetran/Scripts:$PATH" PYTHONUTF8=1 PYTHONIOENCODING=utf-8 DO_NOT_TRACK=1
fivetran debug connectors/ecb --configuration configuration.json --yes   # path is relative to the connector folder
```
Output lands in `connectors/<name>/files/warehouse.db` (DuckDB, git-ignored). Run it twice to see the incremental cursor.

## Notes that differ from the plan
- The plan says "Python 3.9-3.12". SDK 3.1.0 (Nov 2026) deploys Python 3.10 - 3.14. The local debug env uses 3.12.
- One Fivetran connection per source means one Postgres **schema per source**: `fivetran_raw_<source>` (e.g. `fivetran_raw_ecb`),
  not one shared `fivetran_raw`. Independent schedules were worth more than a single schema name.
- `PORTWATCH_ARCGIS_TOKEN`-gated daily traffic is optional; see `docs/sources.md`.
