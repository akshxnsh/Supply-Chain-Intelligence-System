"""Step 8 tests: evidence bundle, verification of the model's answer, the judge flow with a fake model, fallback, storage."""

import json
from datetime import timedelta

import pytest

from src.judge.evidence import build_bundle
from src.judge.judge import Judge, fallback_decision
from src.judge.prompt import build_prompt
from src.judge.schema import EvidenceBundle, EvidenceItem, JudgeDecision
from src.judge.verify import verify
from src.reader import cache as cache_mod
from src.reader.client import LLMResponse
from src.reader.limiter import LLMError, RateLimiter
from src.risk.pipeline import evaluate
from test_risk import CFG, PORTS, TODAY, company, delay_signal, shipment, tariff_signal


def closure_alert(**sig_kw):
    """A heads-up Baltimore closure that would run the stock out (numbers worked by hand in test_risk)."""
    sig = delay_signal(event_type="port_closure", expected_delay_days=10.0, end=TODAY + timedelta(days=9), independent_sources=4,
                       evidence=[{"type": "news_cluster", "id": "c1"}], **sig_kw)
    (row,) = evaluate([sig], [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    texts = {"s1": [EvidenceItem("article:a1", "news_article", "Baltimore dockworkers vote to strike from Friday (cnn.com)"),
                    EvidenceItem("article:a2", "news_article", "Port of Baltimore braces for 10-day closure (reuters.com)")]}
    return row, build_bundle(row, company(), TODAY, texts)


def decision(**over):
    d = {"action_type": "order_replacement", "recommended_action": "Order replacement auto_parts from Harrisburg Auto Parts now.",
         "act_by": TODAY.isoformat(), "reasoning": "Stock runs out before the delayed shipment can arrive.",
         "claims": [{"statement": "Stock covers less than the delay plus the replacement lead time.", "evidence_ids": ["facts"]},
                    {"statement": "Dockworkers announced a strike.", "evidence_ids": ["article:a1", "article:a2"]}],
         "uncertainty": None}
    d.update(over)
    return d


class FakeLLM:
    def __init__(self, *answers):
        self.answers, self.calls, self.prompts = list(answers), 0, []

    def generate(self, prompt, model, **kw):
        self.calls += 1
        self.prompts.append(prompt)
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return LLMResponse(a if isinstance(a, str) else json.dumps(a), 900, 120, 40.0)


class Log:
    def __init__(self):
        self.rows = []

    def log(self, e):
        self.rows.append(e)


def make_judge(llm, cache=None, log=None):
    return Judge(llm, cache if cache is not None else cache_mod.MemoryCache(), RateLimiter(600, sleep=lambda s: None),
                 model="judge-test", call_logger=log, sleep=lambda s: None)


# -- evidence ---------------------------------------------------------------------------------------------------

def test_bundle_has_code_computed_facts_and_citable_evidence():
    row, bundle = closure_alert()
    f = bundle.facts
    assert f["possible_loss_usd"] == 20620 and f["alert_type"] == "heads_up" and f["lead_time_days"] == 5
    assert f["stock"][0]["stockout_risk"] is True and f["stock"][0]["replacement_lead_time_days"] == 3.0
    assert f["best_alternative_suppliers"][0]["name"] == "Harrisburg Auto Parts" and f["affected_suppliers"] == ["Bavarian Parts GmbH (Germany)"]
    assert bundle.ids() == {"facts", "article:a1", "article:a2"} and bundle.act_by_limit == TODAY and bundle.act_by_floor == TODAY
    assert bundle.allowed_action_types == {"order_replacement", "notify_customers", "monitor"} and TODAY in bundle.allowed_dates


def test_tariff_and_no_stockout_bundles_allow_the_right_actions():
    sig = tariff_signal(evidence=[{"type": "federal_register", "id": "2026-1"}])
    (row,) = evaluate([sig], [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    b = build_bundle(row, company(), TODAY, {"t1": [EvidenceItem("notice:2026-1", "notice", "Proposed Rule: 25 percent duty on auto parts")]})
    assert b.allowed_action_types == {"review_landed_cost", "monitor"} and b.facts["tariff"]["rate_percent"] == 25.0
    assert b.act_by_limit == TODAY + timedelta(days=4)
    calm = delay_signal(status="ongoing", start=TODAY - timedelta(days=1), end=TODAY + timedelta(days=2))
    (calm_row,) = evaluate([calm], [shipment()], company(inventory=900000.0), PORTS, CFG, TODAY, 2000.0, "biz")
    assert build_bundle(calm_row, company(inventory=900000.0), TODAY).allowed_action_types == {"notify_customers", "monitor", "none"}


def test_prompt_shows_facts_evidence_ids_limit_and_rules():
    _, bundle = closure_alert()
    p = build_prompt(bundle)
    assert "FACTS:" in p and '"possible_loss_usd": 20620' in p and "[article:a1]" in p and "[facts]" in p
    assert "act_by_limit: " + TODAY.isoformat() in p and "order_replacement" in p and "YYYY-MM-DD" in p
    assert "Never" in p or "never" in p


# -- verification ---------------------------------------------------------------------------------------------------

def test_good_answer_passes_verification():
    _, bundle = closure_alert()
    assert verify(JudgeDecision.model_validate(decision()), bundle) == []
    exact = decision(reasoning="Possible loss $20,620; stock covers 2.5 days, replacement lead time 3 days, delay 10 days.",
                     recommended_action=f"Order by {TODAY.isoformat()}.")
    assert verify(JudgeDecision.model_validate(exact), bundle) == []


@pytest.mark.parametrize("over,fragment", [
    ({"claims": [{"statement": "x", "evidence_ids": ["article:made-up"]}]}, "unknown evidence id"),
    ({"action_type": "hedge_exchange_rate"}, "not allowed here"),
    ({"reasoning": "We could lose $25,000 here."}, "number 25000 in reasoning"),
    ({"reasoning": "Stock lasts 9 days."}, "number 9 in reasoning"),
    ({"recommended_action": "Order about $20k of parts."}, "number 20000"),
    ({"recommended_action": "Order by 2026-11-20."}, "date 2026-11-20"),
    ({"act_by": "2026-11-20"}, "after the latest allowed date"),
    ({"act_by": "2026-11-01"}, "before today"),
    ({"claims": [{"statement": "A claim with 7 invented days", "evidence_ids": ["facts"]}]}, "number 7 in claim 1"),
])
def test_bad_answers_are_rejected_with_a_reason(over, fragment):
    _, bundle = closure_alert()
    issues = verify(JudgeDecision.model_validate(decision(**over)), bundle)
    assert issues and any(fragment in i for i in issues)


def test_numbers_quoted_from_evidence_and_id_digits_are_allowed():
    sig = tariff_signal(evidence=[{"type": "federal_register", "id": "2026-22750"}])
    (row,) = evaluate([sig], [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    b = build_bundle(row, company(), TODAY, {"t1": [EvidenceItem("notice:2026-22750", "notice", "Duty of 25 percent on parts from Germany, comments due in 30 days")]})
    d = JudgeDecision.model_validate({"action_type": "review_landed_cost", "recommended_action": "The notice sets 25% and 30 days for comments.",
                                      "act_by": (TODAY + timedelta(days=3)).isoformat(), "reasoning": "See notice:2026-22750.",
                                      "claims": [{"statement": "Rate is 25 percent.", "evidence_ids": ["notice:2026-22750"]}]})
    assert verify(d, b) == []
    assert verify(JudgeDecision.model_validate({**d.model_dump(mode="json"), "recommended_action": "Duty is 35%."}), b)


# -- judge flow ----------------------------------------------------------------------------------------------------------

def test_model_answer_is_used_cached_and_logged():
    row, bundle = closure_alert()
    llm, log = FakeLLM(decision()), Log()
    judge = make_judge(llm, log=log)
    first = judge.judge(row, bundle)
    assert first.source == "model" and first.issues == [] and first.decision.action_type == "order_replacement"
    assert first.decision.cited_ids() == ["article:a1", "article:a2", "facts"] and first.input_tokens == 900
    again = judge.judge(row, bundle)                      # same facts and prompt -> cache, no second model call
    assert again.source == "cache" and llm.calls == 1
    assert [r["status"] for r in log.rows] == ["ok", "cache"] and log.rows[0]["purpose"] == "judge" and log.rows[0]["latency_ms"] == 40.0


def test_fenced_json_answer_is_accepted():
    row, bundle = closure_alert()
    r = make_judge(FakeLLM("```json\n" + json.dumps(decision()) + "\n```")).judge(row, bundle)
    assert r.source == "model"


@pytest.mark.parametrize("answer,expect", [
    (decision(reasoning="Loss will be $99,999."), "number 99999"),
    (decision(claims=[{"statement": "x", "evidence_ids": ["article:ghost"]}]), "unknown evidence id"),
    (decision(act_by="2027-01-01"), "after the latest allowed date"),
    ("I cannot answer that", "not valid"),
    ({"action_type": "order_replacement"}, "not valid"),
])
def test_unverifiable_answers_fall_back_to_rules_with_the_reason_recorded(answer, expect):
    row, bundle = closure_alert()
    log = Log()
    res = make_judge(FakeLLM(answer), log=log).judge(row, bundle)
    assert res.source == "fallback" and any(expect in i for i in res.issues)
    assert res.decision.recommended_action == row.action and res.decision.act_by == row.act_by
    assert log.rows[-1]["status"] in ("rejected", "parse_error")
    assert verify(res.decision, bundle) == []             # the fallback itself is always clean


def test_api_failure_and_missing_client_fall_back_without_error():
    row, bundle = closure_alert()
    down = make_judge(FakeLLM(*[LLMError("503 overloaded", 503)] * 4))
    r = down.judge(row, bundle)
    assert r.source == "fallback" and "model unavailable" in r.issues[0]
    nokey = Judge(None, None, model="m").judge(row, bundle)
    assert nokey.source == "fallback" and "GEMINI_API_KEY" in nokey.issues[0] and nokey.decision.action_type == "order_replacement"


def test_retries_a_rate_limited_call_then_uses_the_answer():
    row, bundle = closure_alert()
    llm = FakeLLM(LLMError("429", 429), decision())
    r = make_judge(llm).judge(row, bundle)
    assert r.source == "model" and llm.calls == 2


def test_fallback_decisions_by_alert_kind():
    row, bundle = closure_alert()
    assert fallback_decision(row, bundle).action_type == "order_replacement"
    sig = tariff_signal(evidence=[])
    (trow,) = evaluate([sig], [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    tb = build_bundle(trow, company(), TODAY)
    fb = fallback_decision(trow, tb)
    assert fb.action_type == "review_landed_cost" and fb.act_by == TODAY + timedelta(days=4) and verify(fb, tb) == []


# -- storage -------------------------------------------------------------------------------------------------------------------

def test_judgement_is_saved_on_the_alert_and_news_text_comes_from_the_database(pg_url):
    from datetime import datetime, timezone

    from src.ingestion.db import execute, insert_rows, run_query
    from src.judge.run import judge_rows
    from src.risk.pipeline import persist

    for t in ("alerts", "news_cluster_articles", "news_clusters"):
        execute(f'TRUNCATE TABLE "{t}" CASCADE')
    now = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    insert_rows("news_clusters", [{"cluster_id": "c1", "representative_title": "t", "first_seen": now, "last_seen": now,
                                   "article_count": 2, "distinct_domains": 2, "independent_sources": 2}])
    insert_rows("news_cluster_articles", [
        {"article_id": "a1", "cluster_id": "c1", "title": "Dockworkers vote to strike at Baltimore", "domain": "cnn.com", "seen_at": now},
        {"article_id": "a2", "cluster_id": "c1", "title": "Baltimore port braces for closure", "domain": "reuters.com", "seen_at": now}])
    sig = delay_signal(event_type="port_closure", expected_delay_days=10.0, end=TODAY + timedelta(days=9), independent_sources=4,
                       evidence=[{"type": "news_cluster", "id": "c1"}])
    rows = evaluate([sig], [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    persist(rows, CFG, now=now)

    answer = decision(claims=[{"statement": "Stock is short.", "evidence_ids": ["facts"]},
                              {"statement": "Strike vote reported.", "evidence_ids": ["article:a1"]}])
    llm = FakeLLM(answer)
    out = judge_rows(rows, company(), TODAY, make_judge(llm))
    assert len(out) == 1 and out[0][1].source == "model" and "article:a1" in llm.prompts[0] and "Dockworkers vote to strike" in llm.prompts[0]
    saved = run_query("SELECT * FROM alerts")[0]
    assert saved["judge_source"] == "model" and saved["judge_model"] == "judge-test" and saved["judge_action_type"] == "order_replacement"
    assert saved["action"].startswith("Order replacement auto_parts from Harrisburg") and saved["act_by"] == TODAY
    assert saved["judge_claims"][1]["evidence_ids"] == ["article:a1"] and saved["judge_issues"] == [] and saved["judged_at"] is not None


def test_per_run_cap_sends_only_the_biggest_alerts_to_the_model(pg_url):
    from src.judge.run import judge_rows

    sigs = [delay_signal(signal_id=f"s{i}", dedupe_key=f"s{i}", event_type="port_closure", expected_delay_days=10.0, end=TODAY + timedelta(days=9),
                         independent_sources=4) for i in range(3)]
    rows = evaluate(sigs, [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    assert len(rows) == 3
    for i, r in enumerate(rows):                       # make the alerts differ in size
        r.decision.expected_loss_usd = 1000.0 * (i + 1)
    llm = FakeLLM(decision(claims=[{"statement": "Stock is short.", "evidence_ids": ["facts"]}]))
    out = judge_rows(rows, company(), TODAY, make_judge(llm), max_model_calls=1)
    by_loss = {r.decision.expected_loss_usd: res for r, res in out}
    assert llm.calls == 1 and by_loss[3000.0].source == "model"                 # the biggest one got the model call
    assert by_loss[2000.0].source == "fallback" and "per-run cap of 1" in by_loss[2000.0].issues[0]
    assert by_loss[1000.0].source == "fallback"
    assert [r.decision.expected_loss_usd for r, _ in out] == [3000.0, 2000.0, 1000.0]


def test_fallback_for_an_unpriced_duty_notice_passes_verification():
    sig = tariff_signal(rate_percent=None, evidence=[])
    (row,) = evaluate([sig], [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    b = build_bundle(row, company(), TODAY)
    fb = fallback_decision(row, b)
    assert b.facts["tariff"] == {"rate_percent": None, "rate_stated": False}
    assert "cannot be priced" in fb.claims[0].statement and verify(fb, b) == []


def test_a_date_quoted_from_the_evidence_text_is_allowed_but_an_unseen_date_is_not():
    # live case: the notice says "Applicable October 19, 2026" but no system date matched it, so a correct answer was rejected
    sig = tariff_signal(rate_percent=None, start=None, evidence=[{"type": "federal_register", "id": "2026-21295"}])
    (row,) = evaluate([sig], [shipment()], company(), PORTS, CFG, TODAY, 2000.0, "biz")
    b = build_bundle(row, company(), TODAY, {"t1": [EvidenceItem("notice:2026-21295", "notice", "Final determination | dates: Applicable October 19, 2026.")]})
    ok = JudgeDecision.model_validate({"action_type": "monitor", "recommended_action": "Monitor.", "act_by": None,
                                       "reasoning": "The determination applies from 2026-10-19.",
                                       "claims": [{"statement": "Applicable 2026-10-19.", "evidence_ids": ["notice:2026-21295"]}]})
    assert verify(ok, b) == []
    bad = JudgeDecision.model_validate({**ok.model_dump(mode="json"), "reasoning": "It applies from 2026-10-20."})
    assert any("2026-10-20" in i for i in verify(bad, b))
