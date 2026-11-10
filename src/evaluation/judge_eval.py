"""Offline evaluation of the judge: is its recommendation SUPPORTED by the evidence it cites?

Step 1  generate_cases():  real alerts -> the real judge model -> eval/judge_cases.jsonl (evidence texts, the model's raw answer,
                           whether the code's own checks accepted it) + a few deliberately corrupted answers as negative controls.
Step 2  (by hand)          eval/judge_grades.jsonl: supported yes / partly / no for every case.
Step 3  grade_with_llm():  a DIFFERENT, stronger model grades the same cases; compare() reports how often it agrees with the hand
                           grades. Only if it agrees well may it be trusted to grade more cases.

    python -m src.evaluation.judge_eval generate | grade | compare
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

from src.judge.schema import JudgeDecision
from src.reader.limiter import RateLimiter, call_with_retry

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "eval" / "judge_cases.jsonl"
GRADES = ROOT / "eval" / "judge_grades.jsonl"
LLM_GRADES = ROOT / "eval" / "results" / "judge_llm_grades.jsonl"
REPORT = ROOT / "eval" / "results" / "judge_eval.json"
GRADER_MODEL = "gemini-3.5-flash-lite"  # must differ from the judged model (the answers were produced by gemini-3.6-flash)
SEED = 20261110

GRADER_PROMPT = """You check whether a recommendation is supported by the evidence it cites. Use ONLY the FACTS and EVIDENCE below.

For each claim decide: "yes" (the cited evidence or facts clearly say it), "partly" (partly, or it adds detail that is not there), \
"no" (not supported, contradicted, or the cited evidence is about something else). Then give an overall verdict for the whole answer: \
"supported" (all claims yes), "partly" (some claims partly/no but the recommendation still follows from the supported ones), \
"unsupported" (the recommendation relies on unsupported claims).

FACTS:
{facts}

EVIDENCE (id: text):
{evidence}

RECOMMENDATION: {action}
CLAIMS:
{claims}

Answer JSON only: {{"claims": [{{"n": 1, "verdict": "yes|partly|no", "reason": "short"}}], "overall": "supported|partly|unsupported"}}
"""


def _case(case_id: str, kind: str, bundle, decision: JudgeDecision | None, result_source: str, issues: list[str]) -> dict:
    return {"case_id": case_id, "kind": kind, "facts": bundle.facts,
            "evidence": [{"id": i.id, "kind": i.kind, "text": i.text} for i in bundle.items],
            "decision": decision.model_dump(mode="json") if decision else None,
            "judge_source": result_source, "code_check_issues": issues}


def generate_cases(n_news: int = 6, n_notice: int = 8) -> list[dict]:
    from src.agent.model_config import JUDGE_MODEL
    from src.judge.evidence import build_bundle, fetch_source_texts
    from src.judge.judge import Judge
    from src.reader.cache import MemoryCache
    from src.reader.client import GeminiClient
    from src.risk.pipeline import run_risk

    run = run_risk(persist_alerts=False)
    rows, company, today = run["rows"], run["company"], run["today_date"]
    rnd = random.Random(SEED)
    news = [r for r in rows if r.signal.source == "gdelt"]
    notices = [r for r in rows if r.signal.source == "federal_register"]
    chosen = rnd.sample(news, min(n_news, len(news))) + rnd.sample(notices, min(n_notice, len(notices)))
    texts = fetch_source_texts(chosen)
    judge = Judge(GeminiClient(), MemoryCache(), RateLimiter(6), model=JUDGE_MODEL)
    cases = []
    for n, r in enumerate(chosen, 1):
        bundle = build_bundle(r, company, today, texts)
        res = judge.judge(r, bundle)
        cases.append(_case(f"real-{n:02d}", "real", bundle, res.model_decision, res.source, res.issues))
    # negative controls: answers that are NOT supported by construction
    ctrl = [c for c in cases if c["decision"]][:6]
    for k, c in enumerate(ctrl):
        bad = json.loads(json.dumps(c))
        bad["case_id"], bad["kind"] = f"control-{k + 1:02d}", "control"
        claims = bad["decision"]["claims"]
        if k % 2 == 0:   # an invented claim attached to real evidence
            claims[0]["statement"] = "A flood closed the port for three weeks and the supplier has declared bankruptcy."
        else:            # the claims now point at another alert's evidence, which says something else
            other = cases[(cases.index(c) + 3) % len(cases)]
            bad["evidence"] = other["evidence"] + [e for e in bad["evidence"] if e["id"] == "facts"]
        bad["judge_source"], bad["code_check_issues"] = "control", []
        cases.append(bad)
    CASES.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
    return cases


def _load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def grade_with_llm() -> list[dict]:
    from src.reader.client import GeminiClient
    from src.reader.reader import extract_json

    client, limiter = GeminiClient(), RateLimiter(10)
    out = []
    for c in _load(CASES):
        if not c["decision"]:
            continue
        ev = "\n".join(f"{e['id']}: {e['text']}" for e in c["evidence"])
        claims = "\n".join(f"{i}. {cl['statement']}  [cites: {', '.join(cl['evidence_ids'])}]"
                           for i, cl in enumerate(c["decision"]["claims"], 1))
        prompt = GRADER_PROMPT.format(facts=json.dumps(c["facts"], default=str, indent=1), evidence=ev,
                                      action=c["decision"]["recommended_action"], claims=claims)
        resp = call_with_retry(lambda: client.generate(prompt, GRADER_MODEL, temperature=0.0, max_output_tokens=4096), limiter=limiter)
        try:
            g = extract_json(resp.text)
            overall = g.get("overall")
        except ValueError:
            g, overall = {}, None
        out.append({"case_id": c["case_id"], "overall": overall, "claims": g.get("claims", [])})
    LLM_GRADES.parent.mkdir(exist_ok=True)
    LLM_GRADES.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n", encoding="utf-8")
    return out


MAP = {"supported": "yes", "partly": "partly", "unsupported": "no"}


def compare(hand: dict[str, str], llm: dict[str, str | None]) -> dict:
    """Agreement between hand grades (yes/partly/no) and the LLM grader ('supported'/'partly'/'unsupported')."""
    ids = [i for i in hand if i in llm and llm[i]]
    exact = sum(1 for i in ids if MAP.get(llm[i]) == hand[i])
    binary = sum(1 for i in ids if (MAP.get(llm[i]) == "yes") == (hand[i] == "yes"))
    bad = [i for i in ids if hand[i] == "no"]
    caught = sum(1 for i in bad if MAP.get(llm[i]) != "yes")
    confusion: dict[str, int] = {}
    for i in ids:
        k = f"hand={hand[i]} llm={MAP.get(llm[i])}"
        confusion[k] = confusion.get(k, 0) + 1
    return {"cases": len(ids), "exact_agreement": round(exact / len(ids), 3) if ids else None,
            "agreement_fully_supported_vs_not": round(binary / len(ids), 3) if ids else None,
            "hand_graded_unsupported": len(bad), "llm_flagged_those_as_not_fully_supported": caught, "confusion": confusion}


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "compare"
    if cmd == "generate":
        cs = generate_cases()
        print(len(cs), "cases;", sum(1 for c in cs if c["judge_source"] == "model"), "real answers accepted by the code checks,",
              sum(1 for c in cs if c["judge_source"] == "fallback"), "rejected (fallback)")
    elif cmd == "grade":
        print(len(grade_with_llm()), "cases graded by", GRADER_MODEL)
    else:
        hand = {g["case_id"]: g["supported"] for g in _load(GRADES)}
        llm = {g["case_id"]: g["overall"] for g in _load(LLM_GRADES)}
        rep = compare(hand, llm)
        REPORT.write_text(json.dumps(rep, indent=1), encoding="utf-8")
        print(json.dumps(rep, indent=1))
