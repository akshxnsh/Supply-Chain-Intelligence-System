"""The one-command pipeline: order, isolation of failing steps, lock, run log, manual trigger endpoints (fake steps, fast)."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from src import run_all as pipeline
from src.dashboard import api

pytestmark = pytest.mark.usefixtures("pg_url")


def make_steps(order, fail=(), ctx_log=None):
    def step(name):
        def fn(ctx):
            order.append(name)
            if ctx_log is not None:
                ctx_log.append((name, dict(ctx)))
            if name in fail:
                raise RuntimeError(f"{name} exploded")
            ctx[name] = True
            return {"did": name}
        return fn

    return {n: step(n) for n in pipeline.STEP_ORDER}


@pytest.fixture()
def key():
    return int(time.time() * 1000) % 2_000_000_000          # unique advisory-lock key per test


def test_steps_run_in_order_and_the_run_is_logged(key):
    order = []
    res = pipeline.run_all("manual-cli", ["biz"], steps=make_steps(order), lock_key=key)
    assert order == ["dedupe", "reader", "risk", "judge"] and res["status"] == "ok" and res["run_id"]
    row = pipeline.recent_runs(1)[0]
    assert row["run_id"] == res["run_id"] and row["trigger"] == "manual-cli" and row["status"] == "ok" and row["finished_at"] is not None
    assert [s["name"] for s in row["steps"]] == order and all(s["status"] == "ok" and "seconds" in s for s in row["steps"])
    assert row["steps"][0]["summary"] == {"did": "dedupe"} and "judge: ok" in row["summary"]


def test_a_failing_step_does_not_stop_the_next_ones(key):
    order = []
    res = pipeline.run_all("schedule", ["biz"], steps=make_steps(order, fail={"reader"}), lock_key=key)
    assert order == ["dedupe", "reader", "risk", "judge"]                   # risk and judge still ran
    assert res["status"] == "partial"
    reader = next(s for s in res["steps"] if s["name"] == "reader")
    assert reader["status"] == "error" and "RuntimeError: reader exploded" in reader["error"]
    assert pipeline.recent_runs(1)[0]["status"] == "partial"


def test_everything_failing_is_an_error_and_skipped_steps_are_marked(key):
    order = []
    res = pipeline.run_all("manual-cli", ["biz"], skip=("judge",), steps=make_steps(order, fail={"dedupe", "reader", "risk"}), lock_key=key)
    assert res["status"] == "error" and order == ["dedupe", "reader", "risk"]
    assert next(s for s in res["steps"] if s["name"] == "judge") == {"name": "judge", "status": "skipped", "seconds": 0, "summary": "left out on request"}


def test_steps_share_a_context_and_get_the_business_list(key):
    seen = []
    pipeline.run_all("manual-cli", ["b1", "b2"], steps=make_steps([], ctx_log=seen), lock_key=key)
    assert seen[0][1]["businesses"] == ["b1", "b2"]
    assert seen[-1][0] == "judge" and seen[-1][1]["risk"] is True            # the judge step sees what earlier steps stored


def test_a_second_run_while_one_is_in_progress_is_skipped_not_overlapped(key):
    before = len(pipeline.recent_runs(50))
    with pipeline.advisory_lock(key) as got:
        assert got is True and pipeline.is_running(key) is True
        order = []
        res = pipeline.run_all("schedule", ["biz"], steps=make_steps(order), lock_key=key)
        assert res["status"] == "skipped_locked" and res["run_id"] is None and order == []
    assert pipeline.is_running(key) is False                                  # released when the first one finished
    assert len(pipeline.recent_runs(50)) == before                            # a skipped run writes no log row


def test_lock_is_released_even_if_a_step_blows_up_badly(key):
    def bad(ctx):
        raise SystemError("boom")

    steps = {**make_steps([]), "dedupe": bad}
    pipeline.run_all("manual-cli", ["biz"], steps=steps, lock_key=key)
    assert pipeline.is_running(key) is False


def test_default_steps_cover_the_whole_pipeline():
    assert tuple(pipeline.DEFAULT_STEPS) == pipeline.STEP_ORDER == ("dedupe", "reader", "risk", "judge")


# -- manual trigger over the API ----------------------------------------------------------------------------------------------

def test_api_trigger_starts_a_background_run_and_returns_at_once(monkeypatch):
    started = threading.Event()
    got = {}

    def fake_run_all(trigger, businesses, skip):
        got.update(trigger=trigger, businesses=businesses, skip=skip)
        started.set()

    monkeypatch.setattr(pipeline, "run_all", fake_run_all)
    monkeypatch.setattr(pipeline, "is_running", lambda key=pipeline.LOCK_KEY: False)
    r = TestClient(api.app).post("/api/pipeline/run?business_id=biz-1&skip=judge")
    assert r.status_code == 202 and r.json() == {"started": True, "skip": ["judge"]}
    assert started.wait(5) and got == {"trigger": "manual-api", "businesses": ["biz-1"], "skip": ("judge",)}


def test_api_trigger_refuses_when_running_and_rejects_unknown_steps(monkeypatch):
    called = []
    monkeypatch.setattr(pipeline, "run_all", lambda **kw: called.append(kw))
    monkeypatch.setattr(pipeline, "is_running", lambda key=pipeline.LOCK_KEY: True)
    c = TestClient(api.app)
    assert c.post("/api/pipeline/run").status_code == 409
    assert c.post("/api/pipeline/run?skip=bogus").status_code == 422
    assert called == []


def test_api_status_reports_running_and_recent_runs(key, monkeypatch):
    pipeline.run_all("manual-api", ["biz"], steps=make_steps([]), lock_key=key)
    body = TestClient(api.app).get("/api/pipeline/status?limit=3").json()
    assert body["running"] is False and body["recent_runs"][0]["trigger"] == "manual-api" and body["recent_runs"][0]["status"] == "ok"
    assert len(body["recent_runs"]) <= 3
