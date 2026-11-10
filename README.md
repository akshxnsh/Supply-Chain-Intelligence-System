# ChainGuard: early warning for a small importer

ChainGuard watches public news, trade notices, disaster alerts, weather forecasts and exchange rates, matches them to a
business's inbound shipments, stock and customer orders, and tells the owner **what could go wrong, how much it could cost,
how sure we are, and the latest date to act**.

It is built for a small trader who runs purchasing. An alert after the loss has happened is useless, so the point is a
**heads-up with lead time**: for example, "a strike may close the port; stock lasts 10.8 days, a 14-day delay plus a 3-day
replacement lead time would run it out; order a replacement by 2026-11-17".

This is a portfolio project on **sample company data** and **real public data feeds**. Section 4 says plainly what is measured, what is
an estimate, and what is not built.

## 1. What it produces

For every risk it finds, an alert with:

- **Level**: Notify (act now), Watch (dashboard only) or Log (for the record), always with the reason it did or did not notify.
- **Money**: possible loss, and expected loss = likelihood x possible loss (the risk score).
- **Confidence**: High / Medium / Low plus the listed reasons (never a bare percentage).
- **Action and act-by date**, a stockout flag, the affected shipments and suppliers, and the evidence it came from.

## 2. How it works

```
 6 free public sources                 Fivetran custom connectors            PostgreSQL (Neon)
 GDELT news, GDACS disasters,   --->   one Connector SDK connector    --->   fivetran_raw_* schemas
 IMF PortWatch, Federal Register,      per source, incremental                (loaded on a schedule)
 Open-Meteo, ECB rates                 (state cursors)
                                                                                   |
   python -m src.run_all   (one command, every 30 min or on demand)                v
   1 dedupe   many articles about one event -> one event, counts independent outlets
   2 reader   cheap LLM turns messy text into structured events (batched, cached, validated)
   3 risk     code matches events to shipments, prices the loss, scores confidence, applies the alert rules
   4 judge    one LLM call writes the action; code verifies every claim before it is shown
                                                                                   |
                                          FastAPI + Redis cache  --->  React dashboard
                                                  |
                                          "Ask ChainGuard": one tool-using agent (read-only)
```

Design rules that run through the whole project:

- **Code does the maths and the dates.** The models never calculate a loss, a confidence band or a date.
- **Models see only the evidence** they are given, may answer "unknown", run at low temperature and return structured output.
- **Every claim is checked by code.** The judge's numbers, dates and citations must exist in the evidence it was given, otherwise the
  answer is rejected and a rule-based recommendation is used instead (a deterministic fallback that is tested to pass the same checks).
- **No guessing.** A tariff notice that states no duty rate is never priced: it is a Watch ("check the rate"), never a Notify.
- **Tunable and explainable.** Every threshold lives in `config/risk.yaml` (our own estimates, stated as such); every alert explains itself.

### The AI parts (plain model calls, no agent framework)

| Part | Model | Job |
|---|---|---|
| Reader (`src/reader/`) | `gemini-3.5-flash-lite` | Text to a structured event: relevant or not, type, status (happened / ongoing / expected), expected dates, how clear they are, imposing country, duty rate. Batches of 10, Redis cache by content hash, rate limiter with retry, Pydantic validation. |
| Judge (`src/judge/`) | `openai/gpt-oss-120b` on Groq | The recommended action and act-by date, with cited evidence ids, verified by code. |
| Ask ChainGuard (`src/chat/`) | `gemini-3.5-flash-lite` via Google ADK | The only real agent: it chooses which of five **read-only** lookups to make. Hard caps: 6 lookups and 8 model calls per question. Queries run in a READ ONLY database transaction, so even a misbehaving model cannot write. A code check flags any number, date or alert id in the answer that no lookup returned. |

## 3. The dashboard

React + Vite (`src/dashboard/frontend`), FastAPI backend (`src/dashboard/api.py`, 26 routes). Screens that read the real pipeline:
**Dashboard**, **Risk Alerts** (with a "Run analysis now" button), **Notifications** (history of notify decisions), **Shipments & Stock**,
**Ask ChainGuard**, **Freshness**, **AI Quality** (the evaluation numbers below), **How Alerts Work** (read-only settings).
Three older screens (Active Risks, Alerts, Agent Console) belong to the original scripted simulation and are labelled "Simulation demo".

## 4. Results, measured and honest

All numbers come from this repository's own scripts; the logs are in `PROGRESS.md`, the raw results in `docs/benchmarks/` and `eval/results/`.

**Database indexes** (`python -m scripts.benchmark_db`): 15 real app queries on **synthetic** data (about 1.95 M rows, local Postgres 16), median of 7
`EXPLAIN ANALYZE` runs: summed time **1,079.5 ms to 21.4 ms (98.0% lower)**. Repeated on Neon at 0.1 scale (about 195 k rows): **50.7 ms to 3.1 ms (94.0%)**.
A tariff index that measured slower was removed.

**Redis response cache** (`python -m scripts.benchmark_api`, real HTTP, Neon Singapore from a laptop, 60 requests per endpoint): p50 about **320-440 ms uncached
to about 5 ms on a hit**; 8 concurrent clients **18 requests/s uncached (24 after a connection-pool tweak) to 384 with the cache**. Large because the database is far away; with a local database the gain would be small.
Cost: data can be stale for up to the TTL (30-300 s) for changes made outside the API.

**Reader** (334 real items, live): **82.9% fewer model calls** than one-per-item (57 vs 334, including retries); a second pass **98.8% cache hits**.

**Reader accuracy** (50 real items, vs hand labels, `python -m src.evaluation.reader_eval`): expected start date exact **22/22**, event type **27/27**, imposing country 25/27,
relevance accuracy 80% (precision 73%, recall 100%; 89% on the 28 clear-cut items), happened/ongoing/expected only 59%. It over-flags relevance, and it often calls a
preliminary trade ruling "expected" where the labels say "happened".

**Judge check** (offline LLM-as-judge, graded by a different model): 9 of 9 real answers passed the code checks with the Groq judge; the grader agrees with hand grades
on "supported or not" **14/15 (93.3%)**, and flagged all 4 deliberately bad answers.

**Alerts on the sample data** (7 shipments, 60 days of notices): the same events produced 21 Notify alerts at first, because tariffs were priced with an assumed rate.
Removing that guess and matching on who imposes the duty brought it to **0 Notify and 37 Watch** (1 priced). A quiet result mostly means "no notice states a rate that
hits these sample shipments", **not** proof that the system catches real risk.

**Tests**: `python -m pytest -q` runs **263 tests in about 25 s**. Most need no network (fake models); the Postgres ones need `TEST_DATABASE_URL` and skip without it.

### Limits you should know about

- **The "correct answers" behind the accuracy numbers were drafted by an AI assistant and have not been reviewed by a person**, and the samples are small (50 and 15).
  Read them as a first measurement. The same caveat is shown in the dashboard.
- **Nothing is sent to anyone.** Notify decisions are logged, but no email or chat channel is built.
- Company data (suppliers, shipments, orders, inventory) is **sample data**; only one business is analysed (`PIPELINE_BUSINESSES`).
- Likelihood per band, confidence weights, delay lengths and loss rates in `config/risk.yaml` are **our own judgment**, not fitted to outcomes.
- Free-tier realities: Gemini limits (about 15 requests/min for the reader), Groq 8,000 tokens/min, Neon free compute, and a **30-day Fivetran trial**.
- GDELT answers HTTP 429 often, so its `shipping` and `ports` searches can be late (the connector keeps its place and retries). The PortWatch daily traffic
  signal is **off** without an ArcGIS token. The "black swan" check says "not enough history" until a week of news is stored.
- The judge's act-by date is only checked to be inside the allowed window, not that it is the best date; grounding checks do not read number words ("two") or month names.
- No login: do not expose the API publicly as it is. No automated frontend tests.

## 5. Run it

Needs Python (developed on 3.13), Node.js, Docker (local Postgres and Redis), and free accounts for Neon, Fivetran, Gemini and Groq for the live parts.

```bash
python -m venv .venv
.\.venv\Scripts\activate            # Windows (use source .venv/bin/activate elsewhere)
pip install -r requirements.txt
cp .env.example .env                # then fill in the values; .env is gitignored
```

Local Postgres and Redis for development and tests:

```bash
docker run -d --name chainguard-pg -e POSTGRES_PASSWORD=PASSWORD -e POSTGRES_DB=chainguard -p 55432:5432 postgres:16
docker run -d --name chainguard-redis -p 6379:6379 redis:7
```

Create the tables, load the sample company data, run the pipeline once, start the API and the dashboard:

```bash
python -m src.ingestion.migrate
python -m src.ingestion.seed_data
python -m src.run_all                       # dedupe -> reader -> risk -> judge (needs the Fivetran tables to exist)
python -m uvicorn src.dashboard.api:app --port 8000
```

```bash
cd src/dashboard/frontend
npm install
echo VITE_API_URL=http://localhost:8000 > .env.local     # the frontend defaults to a hosted API otherwise
npm run dev
```

Other commands:

```bash
python -m src.chat.ask "Which alerts matter most right now?"   # Ask ChainGuard from the terminal
python -m src.evaluation.reader_eval                           # re-score the reader (calls the live model)
python -m scripts.fivetran_api status                          # state of the six Fivetran connections
powershell -ExecutionPolicy Bypass -File scripts\schedule_pipeline.ps1   # run the pipeline every 30 min (Windows; -Remove to undo)
python -m pytest -q
```

The six data connectors live in `connectors/` and are deployed with the Fivetran Connector SDK (see `docs/fivetran.md`).

## 6. Repository map

```text
src/fetchers/      plain Python fetchers for the six sources (the connectors wrap these)
connectors/        Fivetran Connector SDK connectors, one per source
src/events/        dedupe: many articles -> one event
src/reader/        the LLM reader (+ cache, rate limiter, Gemini and Groq clients, Phoenix tracing hook)
src/risk/          matching, exposure, confidence, alert rules, pipeline, shipments/stock views
src/judge/         evidence, prompt, verification, fallback
src/chat/          Ask ChainGuard: read-only tools, grounding check, ADK agent
src/evaluation/    reader and judge evaluation, saved-results summary
src/run_all.py     the one-command pipeline (lock, run log, manual trigger)
src/dashboard/     FastAPI (api.py), Redis cache (cache.py), React frontend
src/ingestion/     Postgres access, migrations runner, sample data
db/migrations/     numbered SQL migrations
config/risk.yaml   every alert threshold and assumption
eval/              hand labels and saved evaluation results
docs/              sources, fivetran, risk rules, pipeline, Ask ChainGuard, benchmarks, legacy notes
scripts/           benchmarks, Fivetran helper, scheduler installer
```

`src/agent/`, `src/detection/`, `src/exposure/`, `src/suppliers/` and `run.py` are the original multi-agent simulation (it used BigQuery). They still power the
"Simulation demo" screens and the freshness helpers; the live pipeline above does not use them. Notes from that version are in `docs/legacy/`.

## 7. Documentation

- `docs/risk.md`: the risk score, confidence parts and alert rules.
- `docs/sources.md`, `docs/fivetran.md`: the six sources, their limits, and how they are loaded.
- `docs/pipeline.md`: the one-command pipeline, locking and scheduling.
- `docs/ask_chainguard.md`: what the agent can and cannot do.
- `docs/benchmarks/`: raw benchmark results. `PROGRESS.md`: the dated log of every step, including what went wrong.

## 8. Credits

The React dashboard shell and its original screens were built by **amiyasingh**. The backend, data pipeline, AI parts, database, caching, evaluation
and the later screens (Risk Alerts, Notifications, Shipments & Stock, Ask ChainGuard, AI Quality, How Alerts Work, and the rewritten dashboard home) are by Akshansh Singh,
working with Claude Code. Open data: GDELT, GDACS, IMF PortWatch, US Federal Register / USITC, Open-Meteo (CC BY 4.0, non-commercial), ECB reference rates.

## License

MIT. See `LICENSE`.
