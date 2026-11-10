"""Reader prompt. Bump PROMPT_VERSION whenever the wording or schema changes: it is part of the cache key."""

from __future__ import annotations

from src.reader.schema import ReadItem

PROMPT_VERSION = "reader-v1"

INSTRUCTIONS = """You extract structured facts from short news headlines and official trade notices for a supply-chain \
early-warning tool. Read ONLY the text given for each item. Do not use outside knowledge, do not guess.

Rules:
- If the text does not say something, answer "unknown" (or an empty list / null). Never invent a place, a date or a product.
- "relevant" is true only if the item could delay shipments (ports, canals, straits, shipping lanes, strikes, severe weather, \
disasters, accidents) or change import costs (tariffs, duties, quotas, bans, sanctions, trade rules). Otherwise false.
- "status": "happened" (already occurred), "ongoing" (in progress now), "expected" (announced or forecast for the future), "unknown".
- Dates are ISO "YYYY-MM-DD". "start_date" is when the event starts or, for a rule, when it takes effect; "end_date" when it ends. \
Resolve words like "tomorrow" or "next Monday" against the item's "published" date. If the text gives no date use null.
- "date_clarity": "explicit" if the text states the date, "implied" if you worked it out from words like "next week", else "unclear".
- "location_clarity": "explicit" if a specific port/place is named, "implied" if only a region/country is clear, else "unclear".
- "direction": "delay", "higher_cost", "both", "none" or "unknown".
- "locations" are places exactly as named in the text (port, strait, city); "countries" country names; "products" goods mentioned.
- "summary": one plain sentence (max 200 characters) using only the text.

Answer with JSON only, in this exact shape, one object per item and the same item_id:
{"items": [{"item_id": "...", "relevant": true, "event_type": "port_strike|port_closure|port_congestion|severe_weather|\
natural_disaster|canal_or_strait_closure|tariff_or_trade_rule|sanctions|accident_or_incident|other_labor_action|other|unknown", \
"status": "happened|ongoing|expected|unknown", "direction": "delay|higher_cost|both|none|unknown", "locations": [], "countries": [], \
"products": [], "start_date": null, "end_date": null, "date_clarity": "explicit|implied|unclear", \
"location_clarity": "explicit|implied|unclear", "summary": ""}]}
"""


def render_item(item: ReadItem) -> str:
    body = "\n".join(f"  {line}" for line in item.lines)
    return f'--- item_id: {item.item_id}\n  kind: {item.source_type}\n  published: {item.reference_date.isoformat()}\n{body}'


def build_prompt(items: list[ReadItem]) -> str:
    return INSTRUCTIONS + "\nItems:\n" + "\n".join(render_item(i) for i in items) + "\n"
