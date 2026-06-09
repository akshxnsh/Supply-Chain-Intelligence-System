import inspect
import json

import pytest

from src.agent.agents import create_root_agent


def test_specialist_agents_have_tools_registered():
    root = create_root_agent()
    for agent in root.sub_agents:
        assert len(agent.tools) > 0, f"{agent.name} has no tools registered"


def test_all_registered_tools_are_async():
    root = create_root_agent()
    sync_tools = []
    for agent in [root] + list(root.sub_agents):
        for tool in agent.tools:
            fn = getattr(tool, "func", tool)
            if callable(fn) and not inspect.iscoroutinefunction(fn):
                sync_tools.append(f"{agent.name}.{getattr(fn, '__name__', repr(tool))}")
    assert not sync_tools, (
        f"These tools block the event loop (must be async):\n"
        + "\n".join(f"  - {t}" for t in sync_tools)
    )


@pytest.mark.asyncio
async def test_get_recent_disruptions_returns_valid_json(monkeypatch):
    from src.agent import tools

    rows = [{"id": "e1", "headline": "Port Strike"}]
    monkeypatch.setattr(tools, "query_recent_events", lambda hours: rows)
    result = await tools.get_recent_disruptions(24)
    parsed = json.loads(result)
    assert isinstance(parsed, list)
    assert parsed[0]["id"] == "e1"


@pytest.mark.asyncio
async def test_save_alert_record_returns_json_string(monkeypatch):
    from src.agent import tools

    monkeypatch.setattr(tools, "save_alert", lambda alert: None)
    result = await tools.save_alert_record(
        alert_id="a1",
        business_id="demo-business-001",
        created_at="2026-06-09T00:00:00Z",
        disruption_id="d1",
        severity_score=7.0,
        exposure_usd=5000,
    )
    assert isinstance(result, str), "save_alert_record must return str, not dict"
    parsed = json.loads(result)
    assert parsed == {"saved": True, "alert_id": "a1"}


def test_instruction_provider_falls_back_when_business_id_missing(caplog):
    import logging

    root = create_root_agent()
    # Grab the instruction callable from any specialist agent
    provider = root.sub_agents[0].instruction

    class FakeContext:
        state = {}  # no business_id key

    with caplog.at_level(logging.WARNING, logger="src.agent.agents"):
        result = provider(FakeContext())

    assert "demo-business-001" in result
    assert any("missing from session state" in r.message for r in caplog.records)
