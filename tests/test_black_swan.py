"""The black-swan bug: a news COUNT was compared with the mean of calibration SEVERITY scores (different units).
Now the baseline is real daily news counts, and with too little history the check refuses to flag news."""

import asyncio
import json

import pytest

from src.risk import black_swan as bs
from src.risk.black_swan import NewsBaseline, news_volume_zscore

HISTORY = [96, 104, 100, 98, 102, 101, 99, 100]   # 8 complete days, about 100 articles/day


def test_normal_day_is_not_a_spike_and_a_big_jump_is():
    normal = news_volume_zscore(103, HISTORY)
    assert normal.enough_history and abs(normal.zscore) < 1.0 and normal.mean == pytest.approx(100.0, abs=1)
    spike = news_volume_zscore(220, HISTORY)
    assert spike.zscore > 2.5 and "8 days" in spike.note


def test_too_little_history_gives_no_baseline_instead_of_a_guess():
    b = news_volume_zscore(500, [90, 110, 100])
    assert not b.enough_history and b.zscore is None and b.mean is None and "need 7" in b.note and b.history_days == 3


def test_flat_history_does_not_turn_one_extra_article_into_a_spike():
    flat = news_volume_zscore(11, [10] * 10)
    assert flat.std >= bs.MIN_STD and flat.zscore < 2.5
    assert news_volume_zscore(10, [0] * 10).zscore == pytest.approx(10.0)  # dead feed suddenly alive: still a big jump


def test_old_bug_scenario_ordinary_news_volume_is_not_a_4_sigma_spike():
    # old code: 18 events vs mean 8.0 / std 2.5 of severity scores -> z = 4.0 (false "news_volume_spike")
    assert (18 - 8.0) / 2.5 == 4.0
    ordinary_days = [17, 19, 18, 16, 20, 18, 18]     # real unit: articles per day, today's 18 is normal
    assert news_volume_zscore(18, ordinary_days).zscore == pytest.approx(0.0, abs=0.5)


def run_tool(monkeypatch, baseline, ports):
    from src.agent import tools

    monkeypatch.setattr("src.risk.black_swan.load_news_baseline", lambda: baseline)
    return json.loads(asyncio.run(tools.detect_black_swan([{}] * 18, [], ports)))


CONGESTED = [{"congestion_score": 9.0}] * 8


def test_tool_needs_news_and_port_spikes_together(monkeypatch):
    spike = NewsBaseline(300, 10, 100.0, 10.0, 20.0, True, "baseline from 10 days")
    both = run_tool(monkeypatch, spike, CONGESTED)
    assert both["is_anomaly"] and set(both["triggered_signals"]) == {"news_volume_spike", "port_congestion_spike"}
    only_news = run_tool(monkeypatch, spike, [])
    assert not only_news["is_anomaly"] and only_news["triggered_signals"] == ["news_volume_spike"]


def test_tool_does_not_flag_news_without_enough_history(monkeypatch):
    short = NewsBaseline(300, 3, None, None, None, False, "only 3 complete day(s) of news history; need 7 for a baseline")
    out = run_tool(monkeypatch, short, CONGESTED)
    assert not out["is_anomaly"] and out["triggered_signals"] == ["port_congestion_spike"]
    assert out["z_scores"]["news"] == 0.0 and out["news_baseline"]["enough_history"] is False and "need 7" in out["news_baseline"]["note"]
    assert "assumed" in out["port_baseline"]


def test_tool_survives_a_missing_news_table(monkeypatch):
    from src.agent import tools

    def boom():
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr("src.risk.black_swan.load_news_baseline", boom)
    out = json.loads(asyncio.run(tools.detect_black_swan([], [], [])))
    assert out["is_anomaly"] is False and "unavailable" in out["news_baseline"]["note"]


def test_baseline_reads_complete_days_from_the_news_table(pg_url):
    import psycopg

    from src.ingestion.db import run_query  # noqa: F401  (scratch schema search_path is active)

    with psycopg.connect(pg_url, autocommit=True) as c:
        c.execute('DROP SCHEMA IF EXISTS "fivetran_raw_gdelt" CASCADE')
        c.execute('CREATE SCHEMA "fivetran_raw_gdelt"')
        c.execute("""CREATE TABLE fivetran_raw_gdelt.articles (article_id text primary key, seen_at timestamptz,
                     _fivetran_deleted boolean)""")
        try:
            # 3 complete earlier days x 4 articles, 2 in the last 24 h, 1 soft-deleted (ignored)
            for d in (1, 2, 3):
                for i in range(4):
                    c.execute("INSERT INTO fivetran_raw_gdelt.articles VALUES (%s, now() - make_interval(days => %s, hours => 1), false)", (f"h{d}{i}", d + 1))
            c.execute("INSERT INTO fivetran_raw_gdelt.articles VALUES ('n1', now() - interval '2 hours', false), ('n2', now() - interval '3 hours', false)")
            c.execute("INSERT INTO fivetran_raw_gdelt.articles VALUES ('gone', now() - interval '1 hours', true)")
            b = bs.load_news_baseline()
        finally:
            c.execute('DROP SCHEMA IF EXISTS "fivetran_raw_gdelt" CASCADE')
    assert b.current_24h == 2 and b.history_days >= 3 and not b.enough_history
