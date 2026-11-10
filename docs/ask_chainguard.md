# Ask ChainGuard (the one real agent)

A chat assistant that answers plain-English questions about a business's alerts, shipments, stock and data freshness.
Built with Google ADK (`LlmAgent`) on `gemini-3.5-flash-lite` (override with `CHAT_MODEL`). It is the only part of the project where the
MODEL decides which lookup to make next; everything else (reader, judge) is a fixed pipeline.

    python -m src.chat.ask "Which alerts matter most right now?"
    POST /api/ask   {"question": "...", "business_id": "demo-business-001", "session_id": "<send back to continue a chat>"}

**What it can do:** five lookups (`src/chat/tools.py`): `list_open_alerts`, `get_alert_details`, `list_shipments`, `get_stock_and_orders`, `data_freshness`.
**What it cannot do:** change anything. Every query runs in a READ ONLY database transaction (`run_query_readonly`), the business is fixed when the tools
are made (a question cannot reach another business), and asked to place orders or delete data it says it cannot.

**Limits:** at most 6 lookups (a callback refuses the rest) and 8 model calls per question (ADK `RunConfig(max_llm_calls)`), a 60 s timeout, questions
3-500 characters, 10 questions a minute per API process. A hit on any limit is reported (`capped`).

**Checked by code:** after the model answers, `src/chat/grounding.py` verifies that every number, date and alert id in the answer appears in what the
lookups returned. If not, `grounded` is false, the problems are listed in `issues` and a visible note is added to the answer.
