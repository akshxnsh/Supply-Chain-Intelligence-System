# Baltimore Bridge — Data Freshness Lifecycle Demo

This demo shows the system transitioning from a **healthy baseline** to a
**detected disruption** purely because the **FreshnessAgent** ingests new data.
There is **no hardcoded Baltimore logic** anywhere in the agents — the alert
appears only because incident data lands in BigQuery.

## Architecture

```
                    BASELINE (healthy)                      INCIDENT (Baltimore)
BigQuery       seed_baseline_data.py  ───────────────▶  FreshnessAgent sync ▶ BigQuery
                                                              ▲
Source (Postgres google_sheets schema) ◀── load_incident_source.py / Fivetran ◀── seed_data.py
```

- **BigQuery** is what the agents query. It starts on the healthy baseline.
- **Source** = Neon Postgres `google_sheets` schema (production: filled by Fivetran
  from the "Supply Chain Data" Google Sheet). It holds the **Baltimore incident**.
- **`sync_postgres_to_bigquery.sync_table()`** WRITE_TRUNCATE-replaces each BigQuery
  table from the source. The FreshnessAgent calls this after a connector refresh.

## Files

| File | Role |
|------|------|
| `src/ingestion/seed_baseline_data.py` | **NEW** — seeds BigQuery with the healthy pre-incident state. |
| `src/ingestion/seed_data.py` | The **incident** dataset (Baltimore). Unchanged in substance. |
| `src/ingestion/load_incident_source.py` | **NEW** — stages the incident dataset into Postgres `google_sheets` (what `sync_table` reads). |
| `src/ingestion/init_google_sheets.py --seed` | Production path: writes the incident dataset into the Google Sheet (then Fivetran → Postgres). |
| `src/agent/freshness_agent.py` | FreshnessAgent tools (unchanged). |
| `src/agent/freshness_config.py` | Table → connector + staleness map (unchanged; no connector changes required). |

## Why the baseline produces no alert (traced, not assumed)

`detect_disruptions()` flags a supplier only via: a port with congestion > 5.0 or a
strike, a weather alert on a current/upcoming route checkpoint, a news headline
naming a current/upcoming route checkpoint, a disruption event whose **country**
matches a supplier, or a tariff whose **(country, product)** matches a supplier.
The baseline satisfies none:

- **Ports** all < 5.0, no strikes (Baltimore 2.5, Virginia 2.8).
- **Disruption events**: one inert event in *Netherlands* (no supplier country match;
  headline names *Port of Rotterdam*, which is on no active route).
- **Weather**: one low advisory on *Singapore/Hong Kong* ports (on no active route;
  `"Port of Singapore"` does not substring-match the route token `"Singapore Strait"`).
- **Tariffs**: *Mexico/auto_parts*, *Vietnam/fasteners*, *Brazil/auto_parts* — none of
  which match an active supplier's (country, product).

→ `affected_suppliers == []` → `calculate_impact([])` returns exposure 0 → no alert.

## Why a single `disruption_events` refresh flips it

Every baseline auto_parts shipment is destined for **Port of Baltimore** (the
business's primary port). When the incident `disruption_events` lands, the headline
*"…Port of Baltimore closed indefinitely"* substring-matches the upcoming
`Port of Baltimore` checkpoint on those in-transit shipments
(`match_news_to_shipment`, first branch — no port congestion required). That alone
yields affected suppliers and fires the alert. Refreshing
`port_activity` + `shipment_timetable` + `tariff_updates` completes the full picture
(congestion 10.0, 1848h delay, the Virginia reroutes, exposure ≈ $392.6K). For a
deterministic demo, force the transition with the direct sync tool (below); the
staleness-gated path instead waits out each signal table's window (30–60 min).

---

## Runbook

### Stage A — Seed the healthy baseline into BigQuery
```bash
python -m src.ingestion.seed_baseline_data
```
Dashboard: normal operations, no Baltimore alert, low risk.

### Stage B — Stage the Baltimore incident in the SOURCE (not BigQuery yet)
Self-contained path (writes directly to Postgres `google_sheets`):
```bash
python -m src.ingestion.load_incident_source
python -m src.ingestion.load_incident_source --verify   # optional: row counts
```
Production path instead (Sheets → Fivetran → Postgres): `python -m src.ingestion.init_google_sheets --seed`
then let the Fivetran connectors sync. BigQuery is still on the baseline — dashboard stays healthy.

### Stage C/D/E — Trigger the FreshnessAgent transition
Run the agent and have it use the FreshnessAgent, **or** drive the tools directly.
The fast, deterministic path (bypasses the staleness gate via the direct sync tool):
```python
import asyncio
from src.agent.freshness_agent import sync_postgres_table_to_bigquery
INCIDENT = ["disruption_events","port_activity","shipment_timetable","tariff_updates",
            "inventory","pending_orders","business_suppliers","alternative_suppliers",
            "weather_alerts","completed_orders","supplier_reviews"]
for t in INCIDENT:
    print(asyncio.run(sync_postgres_table_to_bigquery(t)))
```
Staleness-gated path (matches the live demo narrative): wait for the windows, then
`refresh_all_stale_tables()` — `disruption_events` (1 min) flips first and is enough
to fire the alert; the rest follow as their windows (30–60 min) elapse.

### Stage F/G — Run the pipeline and confirm the alert
```bash
python run.py once demo-business-001
```

---

## Verification checklist

| Check | Expected (baseline, Stage A) | Expected (post-refresh, Stage F) |
|-------|------------------------------|----------------------------------|
| `detect_disruptions` affected count | 0 | ≥ 5 (Baltimore-bound suppliers) |
| `alert_fired` | **false** | **true** |
| `black_swan_detected` | false | false |
| `exposure_usd` | 0 | ≈ 392,600 |
| `severity_score` | low / n/a | high (≈ 9, on the 0–10 scale) |
| Dashboard | normal operations | Baltimore alert + PO + owner email |
| Mechanism | — | the FreshnessAgent sync is the only thing that changed BigQuery |

Prerequisites: `NEON_DATABASE_URL` (source staging/sync), BigQuery credentials,
and — for the agent-driven refresh — `FIVETRAN_MCP_COMMAND`. No connector
configuration changes are required: the incident reuses the existing per-table
connector mapping in `freshness_config.py`.
