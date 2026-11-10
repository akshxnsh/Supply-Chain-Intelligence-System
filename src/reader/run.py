"""Read all pending news clusters and trade notices with Gemini and store the events.

    python -m src.reader.run                 # read what is new/changed
    python -m src.reader.run --dry-run       # show how many items are pending, no model call

Needs GEMINI_API_KEY. Set READER_RPM to the requests-per-minute limit shown for the reader model in the AI Studio
console (limits are per project and differ per model); the default is deliberately low.
"""

from __future__ import annotations

import argparse
import json
import logging
import os

from src.agent.model_config import READER_MODEL
from src.reader import store
from src.reader.cache import make_cache
from src.reader.client import GeminiClient
from src.reader.limiter import RateLimiter
from src.reader.reader import Reader
from src.reader.tracing import setup_tracing, span

DEFAULT_RPM = 12   # gemini-3.5-flash-lite free tier: 15 requests/minute (AI Studio, Nov 2026)


def run_reader(days: int = 7, batch_size: int = 10, dry_run: bool = False) -> dict:
    """Read every new or changed item with the model and store the events. Returns the numbers (no printing)."""
    items = store.build_items(days=days)
    pending = store.pending_items(items, READER_MODEL)
    out = {"items_in_window": len(items), "pending": len(pending)}
    if dry_run or not pending:
        return out
    setup_tracing()
    reader = Reader(GeminiClient(), make_cache(), RateLimiter(float(os.getenv("READER_RPM", DEFAULT_RPM))),
                    model=READER_MODEL, batch_size=batch_size, call_logger=store.DbCallLogger())
    with span("reader.run", items=len(pending), model=READER_MODEL):
        results, stats = reader.read(pending)
    out["saved_events"] = store.save_results(results, READER_MODEL)
    out.update(stats.to_dict())
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch-size", type=int, default=10)
    args = ap.parse_args()
    result = run_reader(args.days, args.batch_size, args.dry_run)
    print(f"{result['items_in_window']} items in window, {result['pending']} pending (new or changed)")
    if "saved_events" in result:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
