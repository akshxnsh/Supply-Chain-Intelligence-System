import json
from types import SimpleNamespace

import pytest
from opentelemetry import trace

from src.agent import runtime


class FakeSessionService:
    def __init__(self):
        self.created = None
        self.state = {}

    async def create_session(self, **kwargs):
        self.created = kwargs
        self.state = dict(kwargs["state"])
        return SimpleNamespace(state=self.state)

    async def get_session(self, **kwargs):
        return SimpleNamespace(state=self.state)


class FakeEvent:
    author = "SupplyChainIntelligenceAgent"

    def __init__(self, text):
        self.content = SimpleNamespace(
            parts=[SimpleNamespace(text=json.dumps(text))]
        )

    def get_function_calls(self):
        return []

    def is_final_response(self):
        return True


class FakeRunner:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False

    async def run_async(self, **kwargs):
        yield FakeEvent(
            {
                "alert_fired": False,
                "disruption": {"id": "event-1"},
                "severity_score": 0,
            }
        )

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_runtime_uses_adk_session_and_runner(monkeypatch):
    sessions = FakeSessionService()
    monkeypatch.setattr(runtime, "_get_session_service", lambda: sessions)
    monkeypatch.setattr(runtime, "Runner", FakeRunner)
    monkeypatch.setattr(runtime, "create_root_agent", lambda: object())
    monkeypatch.setattr(
        runtime,
        "get_tracer",
        lambda: trace.get_tracer("test"),
    )

    result = await runtime.run_agent_cycle_async(
        business_id="demo-business-001",
        session_id="session-1",
    )

    assert sessions.created["session_id"] == "session-1"
    assert sessions.created["state"]["business_id"] == "demo-business-001"
    assert result["disruption"]["id"] == "event-1"
    assert result["session_id"] == "session-1"
    assert result["tool_calls"] == []
