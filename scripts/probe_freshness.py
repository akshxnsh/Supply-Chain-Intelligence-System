"""CLI probe: send a freshness query through the root agent and verify delegation.

Usage:
    python scripts/probe_freshness.py [table_name] [business_id]

Defaults: disruption_events, demo-business-001
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from src.agent.runtime import FRESHNESS_AGENT_TOOLS, run_probe_async


async def main() -> int:
    table_name = sys.argv[1] if len(sys.argv) > 1 else "disruption_events"
    business_id = sys.argv[2] if len(sys.argv) > 2 else "demo-business-001"

    if not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
        print("[PROBE] ERROR: GOOGLE_API_KEY or GEMINI_API_KEY must be set.")
        return 1

    prompt = f"Check freshness of {table_name} and refresh if stale"
    print(f"[PROBE] Prompt  : {prompt}")
    print(f"[PROBE] Business: {business_id}")
    print()

    try:
        result = await run_probe_async(prompt=prompt, business_id=business_id)
    except KeyError as exc:
        print(f"[PROBE] ERROR: Unknown business_id {business_id!r}: {exc}")
        return 1

    if result.get("error"):
        attempts = result.get("attempts", 1)
        print(f"[PROBE] WARNING: Gemini error after {attempts} attempt(s): {result['error']}")
        print("[PROBE] Partial trace preserved — continuing with what was collected.")
        print()

    print(f"[PROBE] Session : {result['session_id']}")
    print()

    if not result["tool_calls"]:
        print("[PROBE] No tool calls recorded.")
    else:
        print(f"[PROBE] Tool call trace ({len(result['tool_calls'])} total):")
        for i, tc in enumerate(result["tool_calls"], 1):
            tag = " *** FRESHNESS ***" if tc["tool"] in FRESHNESS_AGENT_TOOLS else ""
            args_str = json.dumps(tc["args"], default=str) if tc["args"] else "(no args)"
            resp = tc.get("response")
            resp_line = ""
            if resp is not None:
                resp_line = f"\n       response: {json.dumps(resp, default=str)[:120]}"
            print(f"  {i:>3}. {tc['tool']}{tag}")
            print(f"       args: {args_str}{resp_line}")

    print()
    freshness_hits = result.get("freshness_tool_calls", [])
    if freshness_hits:
        print(f"[PROBE] FreshnessAgent tools invoked ({len(freshness_hits)}):")
        for tc in freshness_hits:
            print(f"  ✓ {tc['tool']}")
    else:
        print("[PROBE] No FreshnessAgent tools were invoked.")

    if result["response"]:
        print()
        print("[PROBE] Agent response (first 500 chars):")
        print(f"  {result['response'][:500]}")

    print()
    if result["passed"]:
        print("[PROBE] PASS — delegation to FreshnessAgent confirmed.")
        return 0
    else:
        print("[PROBE] FAIL — no FreshnessAgent tool was called.")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
