"""The read-only evaluation summary and settings views."""

import json

from fastapi.testclient import TestClient

from src.dashboard import api
from src.evaluation import summary
from src.risk import company_view


def test_summary_reads_saved_results_and_never_invents(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, "RESULTS", tmp_path)
    assert summary.load_summary() == {"reader": None, "judge": [], "grader_model": "gemini-3.5-flash-lite", "labels_reviewed_by_a_person": False}   # nothing saved -> nothing shown
    (tmp_path / "reader_eval.json").write_text(json.dumps({"model": "m", "items": 50, "scores": {"all_items": {"items": 50}}, "cold_run": {}, "warm_run": {}, "mismatches": [1, 2]}))
    (tmp_path / "judge_eval_groq.json").write_text(json.dumps({"cases": 15, "exact_agreement": 0.7, "agreement_fully_supported_vs_not": 0.9, "confusion": {"x": 1}}))
    got = summary.load_summary()
    assert got["reader"]["model"] == "m" and "mismatches" not in got["reader"]
    assert [j["judged_model"] for j in got["judge"]] == ["openai/gpt-oss-120b (Groq)"] and got["judge"][0]["cases"] == 15


def test_summary_survives_a_corrupt_file(tmp_path, monkeypatch):
    monkeypatch.setattr(summary, "RESULTS", tmp_path)
    (tmp_path / "reader_eval.json").write_text("{not json")
    assert summary.load_summary()["reader"] is None


def test_repo_ships_its_evaluation_results():
    got = summary.load_summary()                     # the real files in eval/results must be committed with the code
    assert got["reader"] and got["reader"]["items"] == 50 and len(got["judge"]) == 2


def test_settings_use_the_business_row_or_the_defaults(monkeypatch):
    monkeypatch.setattr(company_view, "run_query_readonly", lambda sql, params=None: [{"importing_country": "Canada", "notify_threshold_usd": 5000.0}])
    mine = company_view.trader_settings("b")
    assert mine["has_own_settings"] and mine["importing_country"] == "Canada" and mine["notify_threshold_usd"] == 5000.0 and mine["watch_floor_usd"] == 1250.0
    monkeypatch.setattr(company_view, "run_query_readonly", lambda sql, params=None: [])
    default = company_view.trader_settings("b")
    assert not default["has_own_settings"] and default["importing_country"] == "United States" and default["notify_threshold_usd"] == 2000.0
    assert default["likelihood_by_band"]["high"] > default["likelihood_by_band"]["low"] and default["rare_event_guard_usd"] == 250000.0


def test_endpoints(monkeypatch):
    monkeypatch.setattr(company_view, "run_query_readonly", lambda sql, params=None: [])
    c = TestClient(api.app)
    assert c.get("/api/settings?business_id=b").json()["notify_threshold_usd"] == 2000.0
    assert c.get("/api/quality").json()["reader"]["items"] == 50
