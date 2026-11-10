"""Pick ~50 real items for the reader evaluation and freeze the text the reader saw (eval/reader_items.jsonl).

Stratified so every kind of case is present: news the reader called relevant / not relevant, notices with and without
future dates. Selection uses the stored reader output ONLY to make the mix balanced; the labels (eval/reader_labels.jsonl)
are written separately, from the text alone.

    python -m scripts.eval_pick_sample
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from src.ingestion.db import run_query
from src.reader import store

OUT = Path(__file__).resolve().parents[1] / "eval" / "reader_items.jsonl"
SEED = 20261110


def main() -> None:
    items = {i.item_id: i for i in store.build_items()}
    pred = {r["event_id"]: r for r in run_query("SELECT event_id, relevant, status, start_date FROM events")}
    rnd = random.Random(SEED)
    news = sorted(i for i in items if i.startswith("news:") and i in pred)
    notices = sorted(i for i in items if i.startswith("notice:") and i in pred)
    pick = []
    rel_news = [i for i in news if pred[i]["relevant"]]
    other_news = [i for i in news if not pred[i]["relevant"]]
    pick += rnd.sample(rel_news, min(12, len(rel_news))) + rnd.sample(other_news, 13)
    expected = [i for i in notices if pred[i]["status"] == "expected"]
    rest = [i for i in notices if i not in expected]
    pick += rnd.sample(expected, 10) + rnd.sample(rest, 15)
    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for iid in sorted(pick):
            it = items[iid]
            f.write(json.dumps({"item_id": iid, "source_type": it.source_type, "reference_date": it.reference_date.isoformat(),
                                "lines": it.lines}, ensure_ascii=False) + "\n")
    print(f"wrote {len(pick)} items to {OUT}")


if __name__ == "__main__":
    main()
