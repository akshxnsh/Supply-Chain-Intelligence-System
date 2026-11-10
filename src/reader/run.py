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

DEFAULT_RPM = 8


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch-size", type=int, default=10)
    args = ap.parse_args()

    items = store.build_items(days=args.days)
    pending = store.pending_items(items, READER_MODEL)
    print(f"{len(items)} items in window, {len(pending)} pending (new or changed)")
    if args.dry_run or not pending:
        return

    setup_tracing()
    reader = Reader(GeminiClient(), make_cache(), RateLimiter(float(os.getenv("READER_RPM", DEFAULT_RPM))),
                    model=READER_MODEL, batch_size=args.batch_size, call_logger=store.DbCallLogger())
    with span("reader.run", items=len(pending), model=READER_MODEL):
        results, stats = reader.read(pending)
    saved = store.save_results(results, READER_MODEL)
    print(json.dumps({"saved_events": saved, **stats.to_dict()}, indent=2))


if __name__ == "__main__":
    main()
