"""Read the saved evaluation results (eval/results/*.json) for the dashboard. Nothing is recomputed here: these are the numbers the
evaluation scripts measured, shown as they are. Missing files give None, never invented numbers."""

from __future__ import annotations

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[2] / "eval" / "results"
# judged model (the one that wrote the answers) -> result file. The GRADER is the same for both runs (see judge_eval.GRADER_MODEL).
JUDGE_FILES = {"gemini-3.6-flash": "judge_eval.json", "openai/gpt-oss-120b (Groq)": "judge_eval_groq.json"}
GRADER_MODEL = "gemini-3.5-flash-lite"


def _read(name: str):
    try:
        return json.loads((RESULTS / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_summary() -> dict:
    reader = _read("reader_eval.json")
    judge = []
    for judged, fname in JUDGE_FILES.items():
        d = _read(fname)
        if d:
            judge.append({"judged_model": judged, **{k: d.get(k) for k in ("cases", "exact_agreement", "agreement_fully_supported_vs_not",
                                                                  "hand_graded_unsupported", "llm_flagged_those_as_not_fully_supported")}})
    return {
        "reader": None if not reader else {k: reader.get(k) for k in ("model", "items", "scores", "cold_run", "warm_run")},
        "judge": judge,
        "grader_model": GRADER_MODEL,
        "labels_reviewed_by_a_person": False,   # the hand labels are first drafts (written by an AI); see PROGRESS.md
    }
