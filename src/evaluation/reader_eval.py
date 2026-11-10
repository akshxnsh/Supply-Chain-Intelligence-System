"""Score the reader against hand labels (eval/reader_labels.jsonl) on frozen items (eval/reader_items.jsonl).

    python -m src.evaluation.reader_eval            # runs the live model (cold cache, then warm), writes eval/results/

Metrics: relevance (accuracy / precision / recall / F1), event type, status, expected-date extraction (exact start date),
imposing country, stated duty rate. Each is reported on ALL labelled items and on the UNAMBIGUOUS ones only (items where
reasonable people could label differently are flagged in the label file). Also reports the cache and call numbers.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from src.reader.schema import ReadEvent, ReadItem

ROOT = Path(__file__).resolve().parents[2]
ITEMS = ROOT / "eval" / "reader_items.jsonl"
LABELS = ROOT / "eval" / "reader_labels.jsonl"
RESULTS = ROOT / "eval" / "results"

COUNTRY_ALIASES = {"us": "united states", "usa": "united states", "u.s.": "united states", "united states of america": "united states",
                   "prc": "china", "people's republic of china": "china", "republic of korea": "south korea"}


def norm_country(c: str | None) -> str | None:
    if not c:
        return None
    c = c.strip().lower()
    return COUNTRY_ALIASES.get(c, c)


def load_items() -> list[ReadItem]:
    out = []
    for line in ITEMS.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        out.append(ReadItem(d["item_id"], d["source_type"], date.fromisoformat(d["reference_date"]), d["lines"], {}))
    return out


def load_labels() -> dict[str, dict]:
    return {d["item_id"]: d for d in (json.loads(l) for l in LABELS.read_text(encoding="utf-8").splitlines())}


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 3) if den else None


def _block(pairs: list[tuple[dict, ReadEvent | None]], ambiguous_only_excluded: bool) -> dict:
    """Metrics on a list of (gold, predicted-or-None) pairs."""
    if ambiguous_only_excluded:
        pairs = [(g, p) for g, p in pairs if not g.get("ambiguous")]
    out: dict = {"items": len(pairs)}

    # relevance (a failed read counts as 'not relevant')
    tp = sum(1 for g, p in pairs if g["relevant"] and p and p.relevant)
    fp = sum(1 for g, p in pairs if not g["relevant"] and p and p.relevant)
    fn = sum(1 for g, p in pairs if g["relevant"] and not (p and p.relevant))
    tn = sum(1 for g, p in pairs if not g["relevant"] and not (p and p.relevant))
    prec, rec = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
    out["relevance"] = {"accuracy": _ratio(tp + tn, len(pairs)), "precision": prec, "recall": rec,
                        "f1": round(2 * prec * rec / (prec + rec), 3) if prec and rec else None, "tp": tp, "fp": fp, "fn": fn, "tn": tn}

    gold_rel = [(g, p) for g, p in pairs if g["relevant"]]
    out["event_type"] = _acc([(g["event_type"], p.event_type if p else None) for g, p in gold_rel])
    out["status"] = _acc([(g["status"], p.status if p else None) for g, p in gold_rel])

    dated = [(g, p) for g, p in gold_rel if g.get("start_date")]
    exact = sum(1 for g, p in dated if p and p.start_date and p.start_date.isoformat() == g["start_date"])
    within1 = sum(1 for g, p in dated if p and p.start_date and abs((p.start_date - date.fromisoformat(g["start_date"])).days) <= 1)
    undated = [(g, p) for g, p in gold_rel if not g.get("start_date")]
    invented = sum(1 for g, p in undated if p and p.start_date)
    out["start_date"] = {"gold_with_date": len(dated), "exact": exact, "exact_rate": _ratio(exact, len(dated)),
                         "within_1_day": within1, "predicted_a_date_where_gold_has_none": invented, "gold_without_date": len(undated)}

    with_country = [(g, p) for g, p in gold_rel if g.get("imposing_country")]
    out["imposing_country"] = _acc([(norm_country(g["imposing_country"]), norm_country(p.imposing_country) if p else None) for g, p in with_country])

    gold_rate = [(g, p) for g, p in gold_rel if g.get("rate_percent") is not None]
    got = sum(1 for g, p in gold_rate if p and p.rate_percent is not None and abs(p.rate_percent - g["rate_percent"]) < 0.01)
    false_rate = sum(1 for g, p in gold_rel if g.get("rate_percent") is None and p and p.rate_percent is not None)
    out["rate_percent"] = {"gold_with_rate": len(gold_rate), "correct": got, "rate_invented_where_gold_has_none": false_rate}
    return out


def _acc(pairs: list[tuple]) -> dict:
    ok = sum(1 for g, p in pairs if g == p)
    return {"items": len(pairs), "correct": ok, "accuracy": _ratio(ok, len(pairs))}


def score(labels: dict[str, dict], predictions: dict[str, ReadEvent | None]) -> dict:
    pairs = [(g, predictions.get(iid)) for iid, g in labels.items()]
    return {"all_items": _block(pairs, False), "unambiguous_items": _block(pairs, True)}


def mismatches(labels: dict[str, dict], predictions: dict[str, ReadEvent | None]) -> list[dict]:
    """Per-item disagreements, for review."""
    out = []
    for iid, g in labels.items():
        p = predictions.get(iid)
        diffs = {}
        if bool(p and p.relevant) != g["relevant"]:
            diffs["relevant"] = (g["relevant"], bool(p and p.relevant))
        if g["relevant"] and p:
            for f in ("event_type", "status"):
                if getattr(p, f) != g[f]:
                    diffs[f] = (g[f], getattr(p, f))
            if (p.start_date.isoformat() if p.start_date else None) != g.get("start_date"):
                diffs["start_date"] = (g.get("start_date"), p.start_date.isoformat() if p.start_date else None)
            if g.get("imposing_country") and norm_country(p.imposing_country) != norm_country(g["imposing_country"]):
                diffs["imposing_country"] = (g["imposing_country"], p.imposing_country)
        if diffs:
            out.append({"item_id": iid, "ambiguous": g.get("ambiguous", []), "note": g.get("note", ""), "diffs": diffs})
    return out


def run_live() -> dict:
    """Cold run (fresh cache -> model calls) then warm run (same cache -> hits), on the 50 frozen items."""
    from src.agent.model_config import READER_MODEL
    from src.reader.cache import MemoryCache
    from src.reader.client import GeminiClient
    from src.reader.limiter import RateLimiter
    from src.reader.reader import Reader

    items, labels = load_items(), load_labels()
    cache = MemoryCache()
    reader = Reader(GeminiClient(), cache, RateLimiter(8), model=READER_MODEL)
    cold_results, cold = reader.read(items)
    warm_results, warm = reader.read(items)
    preds = {r.item.item_id: r.event for r in cold_results}
    report = {"model": READER_MODEL, "items": len(items), "scores": score(labels, preds),
              "cold_run": cold.to_dict(), "warm_run": warm.to_dict(), "mismatches": mismatches(labels, preds)}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "reader_eval.json").write_text(json.dumps(report, indent=1, default=str), encoding="utf-8")
    return report


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.WARNING)
    r = run_live()
    print(json.dumps({k: r[k] for k in ("model", "items", "scores", "cold_run", "warm_run")}, indent=1, default=str))
    print(f"{len(r['mismatches'])} items disagree with the labels (see eval/results/reader_eval.json)")
