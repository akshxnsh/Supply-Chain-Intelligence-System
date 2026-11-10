"""Run the risk pipeline, then ask the judge for an action + act-by date on every Notify-level alert and store it.

    python -m src.judge.run [business_id]

Works without a Gemini key: every alert then gets the rule-based recommendation (judge_source = fallback).
Set JUDGE_RPM to the requests-per-minute limit of the judge model in the AI Studio console (default 5).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections import Counter

from psycopg.types.json import Jsonb

from src.agent.model_config import JUDGE_MODEL
from src.ingestion.db import get_pool
from src.judge.evidence import build_bundle, fetch_source_texts
from src.judge.judge import Judge, JudgeResult
from src.reader.cache import make_cache
from src.reader.client import GeminiClient
from src.reader.limiter import LLMError, RateLimiter
from src.reader.store import DbCallLogger
from src.reader.tracing import setup_tracing, span
from src.risk.pipeline import run_risk

JUDGED_LEVELS = ("notify",)
DEFAULT_RPM = 5

UPDATE_JUDGEMENT = """
UPDATE alerts SET action = %(action)s, act_by = %(act_by)s, judge_source = %(source)s, judge_model = %(model)s,
    judge_action_type = %(action_type)s, judge_reasoning = %(reasoning)s, judge_claims = %(claims)s,
    judge_issues = %(issues)s, judged_at = now(), updated_at = now()
WHERE alert_id = %(alert_id)s
"""


def save_judgement(alert_id: str, result: JudgeResult) -> None:
    d = result.decision
    with get_pool().connection() as conn:
        conn.execute(UPDATE_JUDGEMENT, {
            "alert_id": alert_id, "action": d.recommended_action, "act_by": d.act_by, "source": result.source,
            "model": result.model if result.source != "fallback" else None, "action_type": d.action_type,
            "reasoning": d.reasoning, "claims": Jsonb([c.model_dump() for c in d.claims]), "issues": Jsonb(result.issues)})


def make_client():
    try:
        return GeminiClient()
    except LLMError as exc:
        logging.getLogger(__name__).warning("%s -> rule-based answers only", exc)
        return None


def judge_rows(rows, company, today, judge: Judge) -> list[tuple[object, JudgeResult]]:
    todo = [r for r in rows if r.level in JUDGED_LEVELS]
    texts = fetch_source_texts(todo)
    out = []
    for r in todo:
        result = judge.judge(r, build_bundle(r, company, today, texts))
        save_judgement(r.alert_id, result)
        out.append((r, result))
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    business = sys.argv[1] if len(sys.argv) > 1 else "demo-business-001"
    run = run_risk(business)
    setup_tracing()
    judge = Judge(make_client(), make_cache(prefix="chainguard:judge:"), RateLimiter(float(os.getenv("JUDGE_RPM", DEFAULT_RPM))),
                  model=JUDGE_MODEL, call_logger=DbCallLogger())
    with span("judge.run", alerts=run["alerts"], model=JUDGE_MODEL):
        judged = judge_rows(run["rows"], run["company"], run["today_date"], judge)
    print(json.dumps({"alerts": run["alerts"], "judged": len(judged),
                      "by_source": dict(Counter(res.source for _, res in judged))}, indent=2))
    for row, res in judged:
        print(f"- {row.signal.title[:60]} -> [{res.source}] {res.decision.action_type}, act by {res.decision.act_by}: {res.decision.recommended_action[:90]}")
        for issue in res.issues[:3]:
            print(f"    rejected because: {issue}")


if __name__ == "__main__":
    main()
