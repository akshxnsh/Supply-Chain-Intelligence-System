"""Ask ChainGuard: grounding check, read-only tools, call caps, the agent loop with a scripted fake model, and the API endpoint.
No network and no Gemini key: a fake ADK model plays the part of the model."""

import asyncio
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from pydantic import PrivateAttr

from src.chat import agent as chat_agent
from src.chat.grounding import check_grounding
from src.chat.tools import make_tools

ALERT_ID = "a1b2c3d4e5f60718293a"


# -- grounding (pure) ---------------------------------------------------------------------------------------------------

OUT = [{"count": 2, "alerts": [{"alert_id": ALERT_ID, "expected_loss_usd": 9407.85, "act_by": "2026-11-17", "lead_time_days": 5}]}]


def test_grounded_answer_passes():
    answer = f"1. Alert {ALERT_ID} has an expected loss of $9,407.85; order by 2026-11-17 (5 days). There are 2 alerts."
    assert check_grounding(answer, OUT) == []


@pytest.mark.parametrize("answer,fragment", [
    ("The expected loss is $12,000.", "number 12000"),
    ("Order by 2026-11-20.", "date 2026-11-20"),
    ("Order by November 20, 2026.", "date 2026-11-20"),
    ("See alert ffffffffffffffffffff for details.", "alert id ffffffffffffffffffff"),
    ("You have 7 alerts.", "number 7"),
])
def test_invented_facts_are_found(answer, fragment):
    assert any(fragment in i for i in check_grounding(answer, OUT))


def test_list_markers_and_rounded_quotes_are_not_flagged():
    assert check_grounding("1. First point\n2. Second point\n- 3) third", OUT) == []
    assert check_grounding("Roughly $9,408 expected.", OUT) == []                    # within 0.5% of 9407.85
    assert check_grounding("No data was found.", []) == []
    assert check_grounding("It is 42.", []) != []                                     # a number with no lookups at all is ungrounded


# -- tools ---------------------------------------------------------------------------------------------------------------------

@pytest.fixture()
def db(pg_url):
    from src.ingestion.db import execute, insert_rows

    for t in ("alerts", "shipment_timetable", "business_suppliers", "inventory", "pending_orders"):
        execute(f'TRUNCATE TABLE "{t}"')
    row = {"alert_type": "now", "signal_kind": "tariff", "source": "federal_register", "event_type": "tariff_or_trade_rule",
           "exposure_usd": 100.0, "expected_loss_usd": 40.0, "confidence_band": "high", "confidence_score": 0.8, "level": "watch", "title": "T"}
    insert_rows("alerts", [
        {**row, "alert_id": "A-mine-1", "business_id": "biz-a", "title": "Mine one", "level": "notify", "expected_loss_usd": 500.0},
        {**row, "alert_id": "A-mine-2", "business_id": "biz-a", "title": "Mine two"},
        {**row, "alert_id": "A-mine-3", "business_id": "biz-a", "title": "Mine resolved"},
        {**row, "alert_id": "B-theirs", "business_id": "biz-b", "title": "Not yours"}])
    execute("UPDATE alerts SET status = 'resolved' WHERE alert_id = 'A-mine-3'")      # insert_rows uses the first row's columns only
    return pg_url


def test_read_only_transaction_refuses_writes(db):
    import psycopg

    from src.ingestion.db import run_query, run_query_readonly

    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        run_query_readonly("UPDATE alerts SET title = 'hacked'")
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        run_query_readonly("DELETE FROM alerts")
    assert run_query("SELECT count(*) AS n FROM alerts")[0]["n"] == 4                  # nothing changed
    run_query("UPDATE alerts SET title = title WHERE false")                           # the normal path still writes fine afterwards
    assert run_query_readonly("SELECT 1 AS x") == [{"x": 1}]


def test_tools_only_see_their_own_business(db):
    tools = {f.__name__: f for f in make_tools("biz-a")}
    assert set(tools) == {"list_open_alerts", "get_alert_details", "list_shipments", "get_stock_and_orders", "data_freshness"}
    listed = tools["list_open_alerts"]()
    assert listed["count"] == 2 and [a["alert_id"] for a in listed["alerts"]] == ["A-mine-1", "A-mine-2"]   # open only, Notify first
    assert tools["list_open_alerts"](level="notify")["count"] == 1
    assert tools["get_alert_details"]("A-mine-1")["title"] == "Mine one"
    assert "no alert" in tools["get_alert_details"]("B-theirs")["error"]               # another business's alert is invisible
    assert "level must be" in tools["list_open_alerts"](level="bogus")["error"]
    assert tools["list_open_alerts"](limit=0)["count"] == 1 and tools["list_open_alerts"](limit=999)["count"] == 2


def test_stock_and_shipment_tools_use_the_formula_and_serialise(db):
    from datetime import timedelta

    from src.ingestion.db import insert_rows

    today = datetime.now(timezone.utc)
    insert_rows("business_suppliers", [{"id": "s1", "business_id": "biz-a", "supplier_name": "Acme", "country": "Germany", "product_category": "auto_parts"}])
    insert_rows("shipment_timetable", [{"id": "shp-1", "business_id": "biz-a", "supplier_id": "s1", "product_category": "auto_parts", "quantity": 1,
                                        "shipment_value_usd": 1000.0, "expected_arrival_date": (today + timedelta(days=3)).date(), "etd": today,
                                        "eta": today + timedelta(days=3), "journey_time_hours": 72.0, "route": "A > B", "status": "in_transit",
                                        "origin_port": "A", "destination_port": "B"}])
    insert_rows("inventory", [{"id": "i1", "business_id": "biz-a", "product_category": "auto_parts", "inventory_value_usd": 5000.0}])
    insert_rows("pending_orders", [{"id": "o1", "business_id": "biz-a", "product_category": "auto_parts", "quantity": 1, "order_value_usd": 700.0,
                                    "required_by_date": (today + timedelta(days=10)).date(), "status": "pending"}])
    tools = {f.__name__: f for f in make_tools("biz-a")}
    ships = tools["list_shipments"]()
    assert ships["count"] == 1 and ships["shipments"][0]["supplier_name"] == "Acme" and isinstance(ships["shipments"][0]["arrives"], str)
    stock = tools["get_stock_and_orders"]()["categories"][0]
    assert stock["product_category"] == "auto_parts" and stock["daily_demand_usd"] == 70.0 and stock["days_of_stock"] == 71.4
    assert make_tools("biz-b")[2]()["count"] == 0                                      # list_shipments for another business is empty


def test_a_database_failure_comes_back_as_an_error_not_an_exception(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("src.chat.tools.run_query_readonly", boom)
    out = make_tools("biz-a")[0]()
    assert out == {"error": "could not look that up (RuntimeError)"}


# -- the agent loop with a scripted fake model ---------------------------------------------------------------------------------

class FakeLlm(BaseLlm):
    model: str = "fake-model"
    _steps: list = PrivateAttr(default_factory=list)
    _seen: int = PrivateAttr(default=0)

    def script(self, *steps):
        self._steps = list(steps)
        return self

    async def generate_content_async(self, llm_request, stream=False):
        self._seen += 1
        step = self._steps.pop(0) if len(self._steps) > 1 else self._steps[0]       # the last step repeats forever
        if isinstance(step, tuple):                                                    # ("tool", args)
            parts = [types.Part(function_call=types.FunctionCall(name=step[0], args=step[1]))]
        else:
            parts = [types.Part(text=step)]
        yield LlmResponse(content=types.Content(role="model", parts=parts))


@pytest.fixture()
def fake_tools(monkeypatch):
    """Replace the database tools with canned answers so agent tests need no database."""
    calls = []

    def list_open_alerts(level: str = "", limit: int = 8) -> dict:
        """List open alerts."""
        calls.append(("list_open_alerts", level, limit))
        return OUT[0]

    def data_freshness() -> dict:
        """How fresh the data is."""
        calls.append(("data_freshness",))
        return {"count": 1, "sources": [{"source": "gdelt_articles", "minutes_since_sync": 363.16, "stale": True}]}

    monkeypatch.setattr(chat_agent, "make_tools", lambda business_id: [list_open_alerts, data_freshness])
    return calls


def run(question, model, **kw):
    return asyncio.run(chat_agent.ask(question, "biz-a", model=model, **kw))


def test_agent_looks_things_up_and_answers_with_checked_facts(fake_tools):
    llm = FakeLlm().script(("list_open_alerts", {"limit": 3}), f"The top alert is {ALERT_ID} with an expected loss of $9,407.85; act by 2026-11-17.")
    r = run("What matters most?", llm)
    assert r.grounded and r.issues == [] and not r.capped and r.error is None
    assert [c["name"] for c in r.tool_calls] == ["list_open_alerts"] and r.tool_calls[0]["args"] == {"limit": 3} and r.tool_calls[0]["ok"] is True
    assert r.llm_calls == 2 and r.cited_alert_ids == [ALERT_ID] and "9,407.85" in r.answer and fake_tools == [("list_open_alerts", "", 3)]


def test_an_invented_number_is_flagged_in_the_answer(fake_tools):
    llm = FakeLlm().script(("list_open_alerts", {}), f"Alert {ALERT_ID} will cost you $50,000.")
    r = run("How bad?", llm)
    assert r.grounded is False and any("number 50000" in i for i in r.issues) and "could not verify" in r.answer


def test_tool_budget_refuses_extra_lookups_and_marks_the_answer_capped(fake_tools):
    llm = FakeLlm().script(("list_open_alerts", {}), ("data_freshness", {}), ("list_open_alerts", {}), ("data_freshness", {}), "I could only check some things.")
    r = run("Check everything", llm, max_tool_calls=2, max_llm_calls=10)
    assert len(fake_tools) == 2                                                     # only two lookups really ran
    assert r.capped is True and len(r.tool_calls) == 4 and [c["ok"] for c in r.tool_calls].count(False) == 2
    assert r.answer.startswith("I could only check")


def test_model_call_cap_stops_a_looping_agent(fake_tools):
    llm = FakeLlm().script(("list_open_alerts", {}))                                # never answers, calls a tool forever
    r = run("Loop forever", llm, max_tool_calls=50, max_llm_calls=3)
    assert r.capped is True and "limit" in r.answer.lower() and r.error and llm._seen <= 4 and r.grounded is False


def test_model_failures_become_friendly_messages(fake_tools):
    class Broken(FakeLlm):
        async def generate_content_async(self, llm_request, stream=False):
            raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")
            yield  # pragma: no cover

    r = run("Anything", Broken())
    assert "request limit" in r.answer and r.grounded is False and r.tool_calls == []


def test_a_conversation_can_continue_in_the_same_session(fake_tools):
    sid = "chat-test-session"
    r1 = asyncio.run(chat_agent.ask("First", "biz-a", sid, model=FakeLlm().script("First answer.")))
    r2 = asyncio.run(chat_agent.ask("Second", "biz-a", sid, model=FakeLlm().script("Second answer.")))
    assert r1.session_id == r2.session_id == sid and r1.answer == "First answer." and r2.answer == "Second answer."


def test_instruction_states_the_safety_rules():
    text = chat_agent.INSTRUCTION
    assert "ONLY the lookup tools" in text and "Never calculate" in text and "You can only read" in text and "alert_id" in text
    assert chat_agent.MAX_TOOL_CALLS <= 8 and chat_agent.MAX_LLM_CALLS <= 10


# -- API ----------------------------------------------------------------------------------------------------------------------

def test_api_ask_validates_and_rate_limits(monkeypatch):
    from src.dashboard import api

    async def fake_ask(question, business_id, session_id=None, **kw):
        return chat_agent.AskResult(answer=f"echo: {question}", model="m", session_id=session_id or "s1")

    monkeypatch.setattr(chat_agent, "ask", fake_ask)
    api._ask_times.clear()
    c = TestClient(api.app)
    ok = c.post("/api/ask", json={"question": "Which alerts matter?", "business_id": "demo-business-001"})
    assert ok.status_code == 200 and ok.json()["answer"] == "echo: Which alerts matter?" and ok.json()["grounded"] is True
    assert c.post("/api/ask", json={"question": "hi"}).status_code == 422                                   # too short
    assert c.post("/api/ask", json={"question": "x" * 501}).status_code == 422                              # too long
    assert c.post("/api/ask", json={"question": "A real question", "business_id": "nope"}).status_code == 404
    for _ in range(api._ASK_LIMIT_PER_MINUTE):
        last = c.post("/api/ask", json={"question": "Another question"})
    assert last.status_code == 429
    api._ask_times.clear()
