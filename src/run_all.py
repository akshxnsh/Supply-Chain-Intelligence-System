"""Run the whole pipeline once: group news -> read new items with the model -> score risk and update alerts -> judge Notify alerts.

    python -m src.run_all                       # one run (what the scheduler calls)
    python -m src.run_all --every-minutes 30    # keep running in this process, one run every 30 minutes
    python -m src.run_all --skip reader,judge   # leave steps out
    python -m src.run_all --business demo-business-001

The same run can be started by hand: this command, or POST /api/pipeline/run (the dashboard can call it).

Properties:
  - a database advisory lock means two runs (schedule + manual, or two schedulers) never overlap: the second one exits as "skipped_locked";
  - every step is isolated: if one fails (model overloaded, no key) the error is recorded and the next steps still run on what exists;
  - each step skips work that is already done (the reader only reads new or changed items, the judge reuses cached answers),
    so a run with nothing new takes seconds and makes no model call;
  - every run is written to pipeline_runs (trigger, status, per-step result and timing).
Data COLLECTION is not part of this: Fivetran syncs the sources on its own schedule (docs/fivetran.md).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Callable

from psycopg.types.json import Jsonb

from src.ingestion.db import connect, get_pool

logger = logging.getLogger(__name__)

LOCK_KEY = 74_202_611          # arbitrary constant: one pipeline per database
STEP_ORDER = ("dedupe", "reader", "risk", "judge")


# -- the steps (each takes and fills a shared context, returns a small summary dict) ---------------------------------------

def step_dedupe(ctx: dict) -> dict:
    from src.events.cluster_store import run_dedupe

    return run_dedupe()


def step_reader(ctx: dict) -> dict:
    from src.reader.run import run_reader

    return run_reader()


def step_risk(ctx: dict) -> dict:
    from src.risk.pipeline import run_risk

    runs = [run_risk(b) for b in ctx["businesses"]]
    ctx["risk_runs"] = runs
    return {"businesses": len(runs), "alerts": sum(r["alerts"] for r in runs),
            "by_level": {lvl: sum(r["alerts_by_level"].get(lvl, 0) for r in runs) for lvl in ("notify", "watch", "log")},
            "notifications_this_run": sum(r["notifications_this_run"] for r in runs),
            "resolved_stale_alerts": sum(r.get("resolved_stale_alerts", 0) for r in runs)}


def step_judge(ctx: dict) -> dict:
    from collections import Counter

    from src.agent.model_config import JUDGE_MODEL
    from src.judge.run import DEFAULT_RPM, judge_rows, make_client
    from src.judge.judge import Judge
    from src.reader.cache import make_cache
    from src.reader.limiter import RateLimiter
    from src.reader.store import DbCallLogger

    runs = ctx.get("risk_runs")
    if not runs:
        return {"skipped": "the risk step did not run"}
    judge = Judge(make_client(), make_cache(prefix="chainguard:judge:"), RateLimiter(float(os.getenv("JUDGE_RPM", DEFAULT_RPM))),
                  model=JUDGE_MODEL, call_logger=DbCallLogger())
    judged = []
    for run in runs:
        judged += judge_rows(run["rows"], run["company"], run["today_date"], judge)
    return {"judged": len(judged), "by_source": dict(Counter(res.source for _, res in judged))}


DEFAULT_STEPS: dict[str, Callable[[dict], dict]] = {"dedupe": step_dedupe, "reader": step_reader, "risk": step_risk, "judge": step_judge}


# -- lock + log ---------------------------------------------------------------------------------------------------------------

@contextmanager
def advisory_lock(key: int = LOCK_KEY):
    """Yield True if this process got the pipeline lock (held on its own connection until the block ends), else False."""
    conn = connect(autocommit=True)
    try:
        got = conn.execute("SELECT pg_try_advisory_lock(%s) AS got", (key,)).fetchone()["got"]
        try:
            yield got
        finally:
            if got:
                conn.execute("SELECT pg_advisory_unlock(%s)", (key,))
    finally:
        conn.close()


def is_running(key: int = LOCK_KEY) -> bool:
    with advisory_lock(key) as got:
        return not got


def _log_start(trigger: str) -> int:
    with get_pool().connection() as conn:
        return conn.execute("INSERT INTO pipeline_runs (trigger) VALUES (%s) RETURNING run_id", (trigger,)).fetchone()["run_id"]


def _log_finish(run_id: int, status: str, steps: list[dict], summary: str) -> None:
    with get_pool().connection() as conn:
        conn.execute("UPDATE pipeline_runs SET finished_at = now(), status = %s, steps = %s, summary = %s WHERE run_id = %s",
                     (status, Jsonb(steps), summary, run_id))


def recent_runs(limit: int = 5) -> list[dict]:
    with get_pool().connection() as conn:
        return list(conn.execute("SELECT run_id, started_at, finished_at, trigger, status, summary, steps FROM pipeline_runs "
                                 "ORDER BY started_at DESC LIMIT %s", (limit,)).fetchall())


# -- one run -------------------------------------------------------------------------------------------------------------------

def run_all(trigger: str = "manual-cli", businesses: list[str] | None = None, skip: tuple[str, ...] = (),
            steps: dict[str, Callable[[dict], dict]] | None = None, lock_key: int = LOCK_KEY) -> dict:
    """Run the steps once. Returns {run_id, status, steps, summary}; status is ok | partial | error | skipped_locked."""
    steps = steps or DEFAULT_STEPS
    businesses = businesses or [b for b in os.getenv("PIPELINE_BUSINESSES", "demo-business-001").split(",") if b]
    with advisory_lock(lock_key) as got:
        if not got:
            logger.info("another pipeline run holds the lock: skipping")
            return {"run_id": None, "status": "skipped_locked", "steps": [], "summary": "another run is in progress"}
        run_id = _log_start(trigger)
        ctx: dict = {"businesses": businesses}
        results: list[dict] = []
        for name in [n for n in STEP_ORDER if n in steps]:
            if name in skip:
                results.append({"name": name, "status": "skipped", "seconds": 0, "summary": "left out on request"})
                continue
            started = time.perf_counter()
            try:
                summary = steps[name](ctx)
                status, detail = "ok", {"summary": summary}
            except Exception as exc:  # noqa: BLE001 - one broken step must not stop the next ones
                logger.exception("step %s failed", name)
                status, detail = "error", {"error": f"{exc.__class__.__name__}: {str(exc)[:300]}"}
            results.append({"name": name, "status": status, "seconds": round(time.perf_counter() - started, 2), **detail})
        ran = [r for r in results if r["status"] != "skipped"]
        failed = [r for r in ran if r["status"] == "error"]
        status = "ok" if not failed else ("error" if len(failed) == len(ran) else "partial")
        summary_text = "; ".join(f"{r['name']}: {r['status']}" for r in results)
        _log_finish(run_id, status, results, summary_text)
    try:  # a run launched from the API process refreshes the cached answers at once; other processes rely on the TTL
        from src.dashboard.cache import invalidate

        invalidate("alerts", "risk")
    except Exception:  # noqa: BLE001
        pass
    return {"run_id": run_id, "status": status, "steps": results, "summary": summary_text}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--business", action="append", help="business id (repeatable); default demo-business-001")
    ap.add_argument("--skip", default="", help="comma list of steps to leave out: dedupe,reader,risk,judge")
    ap.add_argument("--every-minutes", type=float, default=0, help="stay running and repeat every N minutes (0 = run once)")
    ap.add_argument("--trigger", default="manual-cli", help="recorded in pipeline_runs (the scheduler passes 'schedule')")
    args = ap.parse_args()
    skip = tuple(s for s in args.skip.split(",") if s)
    while True:
        started = datetime.now(timezone.utc)
        result = run_all(args.trigger if not args.every_minutes else "schedule", args.business, skip)
        print(json.dumps({"at": started.isoformat(timespec="seconds"), "status": result["status"], "summary": result["summary"]}), flush=True)
        if not args.every_minutes:
            raise SystemExit(0 if result["status"] in ("ok", "skipped_locked") else 1)
        time.sleep(max(1.0, args.every_minutes * 60 - (datetime.now(timezone.utc) - started).total_seconds()))


if __name__ == "__main__":
    main()
