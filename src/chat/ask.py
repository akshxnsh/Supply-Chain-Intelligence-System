"""Command line for Ask ChainGuard.

    python -m src.chat.ask "Which shipments are at risk this week and what should I do first?"
    python -m src.chat.ask "How fresh is the data?" --business demo-business-001
"""

from __future__ import annotations

import argparse
import json
import logging

from src.chat.agent import ask_sync


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--business", default="demo-business-001")
    args = ap.parse_args()
    r = ask_sync(args.question, args.business)
    print(r.answer)
    print("\n--- lookups:", json.dumps([{"tool": c["name"], "args": c["args"], "ok": c["ok"]} for c in r.tool_calls]))
    print(f"--- model {r.model}: {r.llm_calls} model call(s), {len(r.tool_calls)} lookup(s), {r.seconds}s, grounded={r.grounded}, capped={r.capped}")


if __name__ == "__main__":
    main()
