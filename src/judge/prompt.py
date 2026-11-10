"""Judge prompt. Bump PROMPT_VERSION when it changes (it is part of the cache key)."""

from __future__ import annotations

from src.judge.evidence import facts_json
from src.judge.schema import EvidenceBundle

PROMPT_VERSION = "judge-v1"

INSTRUCTIONS = """You advise a small importer who runs purchasing. An early-warning system found a possible supply problem. \
Decide what the importer should do and by when.

Hard rules:
- Use ONLY the FACTS and EVIDENCE below. No outside knowledge. If the evidence is not enough, choose action_type "monitor" and say what is unknown.
- You do NOT calculate. Money, days, stock cover and dates are given in FACTS. Quote numbers EXACTLY as written there; never round, \
estimate or invent a number, and never write a number that is not in FACTS or EVIDENCE.
- Every claim must cite one or more evidence ids from the list (exactly as written). Use "facts" to cite the numbers in FACTS.
- "act_by" is a date YYYY-MM-DD, not earlier than today and not later than act_by_limit (if given). Use null when no deadline applies.
- action_type must be one of: {allowed}.
- Write numbers as digits and dates ONLY as YYYY-MM-DD (never "Nov 17" or "two days").
- Be specific and short. Name the supplier / category only if it appears in FACTS.

Answer with JSON only:
{{"action_type": "...", "recommended_action": "one or two sentences", "act_by": "YYYY-MM-DD or null", "reasoning": "short", \
"claims": [{{"statement": "...", "evidence_ids": ["facts", "..."]}}], "uncertainty": "what is unknown, or null"}}
"""


def build_prompt(bundle: EvidenceBundle) -> str:
    head = INSTRUCTIONS.format(allowed=", ".join(sorted(bundle.allowed_action_types)))
    limit = bundle.act_by_limit.isoformat() if bundle.act_by_limit else "none"
    ev = "\n".join(f'[{i.id}] ({i.kind}) {i.text}' for i in bundle.items)
    return (f"{head}\nact_by_limit: {limit}\ntoday: {bundle.act_by_floor.isoformat() if bundle.act_by_floor else 'unknown'}\n\n"
            f"FACTS:\n{facts_json(bundle)}\n\nEVIDENCE:\n{ev}\n")
