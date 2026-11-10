"""Step 6 tests: the reader with a fake Gemini client (no key, no network), cache, limiter, retries and storage."""

import json
import re
from datetime import date, datetime, timedelta, timezone

import fakeredis
import pytest

from src.reader import cache as cache_mod
from src.reader.client import LLMResponse
from src.reader.limiter import LLMError, RateLimiter, call_with_retry, is_retryable
from src.reader.prompt import PROMPT_VERSION, build_prompt
from src.reader.reader import Reader, extract_json, parse_response
from src.reader.schema import ReadEvent, ReadItem, normalize

REF = date(2026, 11, 10)


def item(i, text="Dockworkers at Rotterdam announce a 48-hour strike from Monday", ref=REF, **meta):
    return ReadItem(f"news:c{i}", "news", ref, [f"headline: {text} #{i}"], meta or {"independent_sources": 2})


def good(item_id, **over):
    ev = {"item_id": item_id, "relevant": True, "event_type": "port_strike", "status": "expected", "direction": "delay",
          "locations": ["Rotterdam"], "countries": ["Netherlands"], "products": [], "start_date": "2026-11-16",
          "end_date": "2026-11-18", "date_clarity": "implied", "location_clarity": "explicit", "summary": "Strike."}
    ev.update(over)
    return ev


class FakeLLM:
    """Answers every item in the prompt with a valid event unless `script` says otherwise."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.prompts, self.calls = [], 0

    def generate(self, prompt, model, **kw):
        self.calls += 1
        self.prompts.append(prompt)
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, Exception):
                raise step
            if isinstance(step, LLMResponse):
                return step
            if callable(step):
                return step(prompt)
            return LLMResponse(step, 100, 50, 12.0)
        ids = re.findall(r"--- item_id: (\S+)", prompt)
        return LLMResponse(json.dumps({"items": [good(i) for i in ids]}), 100 * len(ids), 40 * len(ids), 25.0)


class Log:
    def __init__(self):
        self.rows = []

    def log(self, entry):
        self.rows.append(entry)


def make_reader(llm=None, cache=None, log=None, **kw):
    return Reader(llm or FakeLLM(), cache or cache_mod.MemoryCache(), RateLimiter(600, sleep=lambda s: None),
                  model="test-model", call_logger=log, sleep=lambda s: None, **kw)


# -- JSON handling ---------------------------------------------------------------

def test_extract_json_handles_fences_and_surrounding_text():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! Here it is:\n{"items": [1]}\nHope this helps') == {"items": [1]}
    assert extract_json("[1, 2]") == [1, 2]
    with pytest.raises(ValueError):
        extract_json("I cannot help with that")


def test_parse_response_valid_invalid_missing_and_invented_ids():
    text = json.dumps({"items": [good("a"), good("b", status="maybe"), good("zzz")]})
    events, errors = parse_response(text, {"a", "b", "c"})
    assert set(events) == {"a"} and set(errors) == {"b", "c"}   # b: bad enum; c: missing; zzz: ignored
    assert "status" in errors["b"] and errors["c"] == "item missing from model answer"
    assert set(parse_response(json.dumps([good("a")]), {"a"})[0]) == {"a"}          # bare list accepted
    assert set(parse_response(json.dumps(good("a")), {"a"})[0]) == {"a"}            # single object accepted


def test_read_event_cleans_lists_and_blank_dates():
    e = ReadEvent.model_validate(good("a", locations=["Rotterdam", "unknown", "", "Rotterdam"], countries="Netherlands",
                                      start_date="unknown", end_date=""))
    assert e.locations == ["Rotterdam"] and e.countries == ["Netherlands"] and e.start_date is None and e.end_date is None


def test_normalize_rejects_impossible_dates_and_weak_signals():
    far = ReadEvent.model_validate(good("a", start_date="2031-01-01", end_date="2031-01-05"))
    n = normalize(far, REF)
    assert n.start_date is None and n.end_date is None and n.date_clarity == "unclear"
    backwards = normalize(ReadEvent.model_validate(good("a", start_date="2026-11-18", end_date="2026-11-16")), REF)
    assert backwards.start_date == date(2026, 11, 18) and backwards.end_date is None and backwards.date_clarity == "unclear"
    ok = normalize(ReadEvent.model_validate(good("a")), REF)
    assert ok.start_date == date(2026, 11, 16) and ok.date_clarity == "implied"
    nowhere = normalize(ReadEvent.model_validate(good("a", locations=[], countries=[])), REF)
    assert nowhere.location_clarity == "unclear"


# -- limiter and retry --------------------------------------------------------------

def test_rate_limiter_spaces_calls():
    now, slept = [0.0], []

    def sleep(s):
        slept.append(s)
        now[0] += s

    lim = RateLimiter(6, clock=lambda: now[0], sleep=sleep)   # 6 per minute = one every 10 s
    for _ in range(3):
        lim.wait()
    assert slept == [10.0, 10.0] and lim.waited_seconds == 20.0
    now[0] += 100                                              # idle for a long time: no wait owed
    assert lim.wait() == 0.0
    with pytest.raises(ValueError):
        RateLimiter(0)


def test_retry_backoff_then_success_and_hints():
    sleeps, tries = [], []
    seq = [LLMError("429", 429), LLMError("503", 503), "ok"]

    def fn():
        v = seq.pop(0)
        if isinstance(v, Exception):
            raise v
        return v

    assert call_with_retry(fn, sleep=sleeps.append, jitter=lambda: 0.0, base_delay=4.0,
                           on_retry=lambda n, e, d: tries.append(n)) == "ok"
    assert sleeps == [4.0, 8.0] and tries == [1, 2]
    hinted = [LLMError("429", 429, retry_after=17.0), "ok"]
    sleeps.clear()
    call_with_retry(lambda: (_ for _ in ()).throw(hinted.pop(0)) if isinstance(hinted[0], Exception) else hinted.pop(0),
                    sleep=sleeps.append, jitter=lambda: 0.0)
    assert sleeps == [17.0]


def test_retry_does_not_retry_client_errors_and_gives_up():
    calls = []

    def bad():
        calls.append(1)
        raise LLMError("bad request", 400)

    with pytest.raises(LLMError):
        call_with_retry(bad, sleep=lambda s: None)
    assert len(calls) == 1
    calls.clear()

    def down():
        calls.append(1)
        raise LLMError("overloaded", 503)

    with pytest.raises(LLMError):
        call_with_retry(down, sleep=lambda s: None, max_retries=2, jitter=lambda: 0.0)
    assert len(calls) == 3 and is_retryable(TimeoutError()) and not is_retryable(ValueError())


# -- cache ----------------------------------------------------------------------------

def test_redis_cache_roundtrip_with_fakeredis_and_ttl():
    r = fakeredis.FakeRedis(decode_responses=True)
    c = cache_mod.RedisCache(r)
    assert c.get("k") is None
    c.set("k", {"event": {"x": 1}}, ttl=60)
    assert c.get("k") == {"event": {"x": 1}} and 0 < r.ttl("chainguard:reader:k") <= 60 and c.backend == "redis"


def test_redis_outage_degrades_to_miss_not_error():
    class Broken:
        def get(self, *a):
            raise ConnectionError("down")

        def set(self, *a, **k):
            raise ConnectionError("down")

    c = cache_mod.RedisCache(Broken())
    assert c.get("k") is None
    c.set("k", {"a": 1})  # must not raise


def test_make_cache_falls_back_to_memory():
    assert cache_mod.make_cache("").backend == "memory"
    assert cache_mod.make_cache("redis://127.0.0.1:1/0").backend == "memory"   # nothing listens there


# -- reader end to end --------------------------------------------------------------------

def test_batches_cache_and_call_savings():
    llm, log = FakeLLM(), Log()
    reader = make_reader(llm, log=log, batch_size=10)
    items = [item(i) for i in range(25)]
    results, stats = reader.read(items)
    assert llm.calls == 3 and [len(re.findall("--- item_id:", p)) for p in llm.prompts] == [10, 10, 5]
    assert all(r.source == "llm" and r.event.event_type == "port_strike" for r in results)
    d = stats.to_dict()
    assert d["cache_hits"] == 0 and d["cache_misses"] == 25 and d["llm_calls"] == 3
    assert d["naive_calls"] == 25 and d["calls_saved"] == 22 and d["call_reduction_pct"] == 88.0
    assert stats.input_tokens == 2500 and stats.output_tokens == 1000
    assert [r["status"] for r in log.rows if r["kind"] == "call"] == ["ok"] * 3
    assert log.rows[0]["kind"] == "cache_summary" and log.rows[0]["cache_misses"] == 25

    results2, stats2 = reader.read(items)               # same text again: everything from cache, no model call
    assert llm.calls == 3 and stats2.cache_hits == 25 and stats2.llm_calls == 0
    assert all(r.source == "cache" for r in results2) and stats2.to_dict()["call_reduction_pct"] == 100.0


def test_cache_key_changes_with_text_model_and_prompt_version():
    base = item(1)
    h = base.content_hash("m", PROMPT_VERSION)
    assert h == item(1).content_hash("m", PROMPT_VERSION)
    assert h != base.content_hash("other-model", PROMPT_VERSION) and h != base.content_hash("m", "reader-v2")
    assert h != item(1, text="Different headline").content_hash("m", PROMPT_VERSION)
    assert h != item(1, ref=REF + timedelta(days=1)).content_hash("m", PROMPT_VERSION)


def test_prompt_shows_only_item_text_not_meta():
    secret = ReadItem("news:x", "news", REF, ["headline: Port closed"], {"cluster_id": "SECRET-META", "independent_sources": 9})
    p = build_prompt([secret])
    assert "news:x" in p and "Port closed" in p and "SECRET-META" not in p and "published: 2026-11-10" in p
    assert "unknown" in p and "Never invent" in p


def test_rate_limited_then_ok_counts_retry_and_logs_it():
    log = Log()
    llm = FakeLLM([LLMError("429 slow down", 429)])  # first try rate-limited, second uses the default valid answer
    results, stats = make_reader(llm, log=log).read([item(1)])
    assert results[0].source == "llm" and stats.retried_calls == 1 and stats.llm_calls == 2
    assert [r["status"] for r in log.rows if r["kind"] == "call"] == ["retry", "ok"]


def test_invalid_item_is_read_again_on_its_own():
    first = lambda prompt: LLMResponse(json.dumps({"items": [good("news:c1"), good("news:c2", status="maybe")]}), 10, 5, 1.0)
    llm = FakeLLM([first])
    results, stats = make_reader(llm).read([item(1), item(2)])
    assert [r.source for r in results] == ["llm", "llm"]
    assert llm.calls == 2 and stats.parse_failures == 1
    assert len(re.findall("--- item_id:", llm.prompts[1])) == 1 and "news:c2" in llm.prompts[1]


def test_garbage_answer_twice_marks_item_failed_and_not_cached():
    cache = cache_mod.MemoryCache()
    llm = FakeLLM([LLMResponse("I am sorry, I cannot do that", 5, 5, 1.0), LLMResponse("still no JSON", 5, 5, 1.0)])
    results, stats = make_reader(llm, cache).read([item(1)])
    assert results[0].source == "failed" and results[0].event is None and stats.failed_items == 1
    assert cache._data == {}                                   # failures are never cached


def test_api_error_marks_batch_failed_and_keeps_other_cached_items():
    cache = cache_mod.MemoryCache()
    make_reader(FakeLLM(), cache).read([item(1)])              # item 1 cached
    llm = FakeLLM([LLMError("bad request", 400)])
    results, stats = make_reader(llm, cache).read([item(1), item(2)])
    assert [r.source for r in results] == ["cache", "failed"] and stats.failed_items == 1 and llm.calls == 1


def test_model_dates_that_are_impossible_are_dropped_by_code():
    far = lambda prompt: LLMResponse(json.dumps({"items": [good("news:c1", start_date="2040-05-05", end_date=None)]}), 1, 1, 1.0)
    results, _ = make_reader(FakeLLM([far])).read([item(1)])
    assert results[0].event.start_date is None and results[0].event.date_clarity == "unclear"


def test_batch_split_by_prompt_size():
    long_text = "x" * 3000
    reader = make_reader(max_prompt_chars=7000, batch_size=10)
    batches = list(reader._batches([item(i, text=long_text) for i in range(5)]))
    assert [len(b) for b in batches] == [2, 2, 1]


# -- database ----------------------------------------------------------------------------------

@pytest.fixture()
def fr_raw(pg_url):
    import psycopg

    with psycopg.connect(pg_url, autocommit=True) as c:
        c.execute('DROP SCHEMA IF EXISTS "fivetran_raw_federal_register" CASCADE')
        c.execute('CREATE SCHEMA "fivetran_raw_federal_register"')
        c.execute("""CREATE TABLE fivetran_raw_federal_register.documents (document_number text primary key, title text,
                     doc_type text, publication_date date, effective_on date, comments_close_on date, dates_text text,
                     abstract text, agencies text, url text, _fivetran_deleted boolean, _fivetran_synced timestamptz)""")
        yield c
        c.execute('DROP SCHEMA IF EXISTS "fivetran_raw_federal_register" CASCADE')


def test_store_builds_items_saves_events_and_skips_unchanged(pg_url, fr_raw):
    from src.ingestion.db import execute, insert_rows, run_query
    from src.reader import store

    for t in ("events", "llm_calls", "news_cluster_articles", "news_clusters"):
        execute(f'TRUNCATE TABLE "{t}" CASCADE')
    now = datetime.now(timezone.utc)
    insert_rows("news_clusters", [{"cluster_id": "c1", "representative_title": "Rotterdam strike", "first_seen": now,
                                   "last_seen": now, "article_count": 2, "distinct_domains": 2, "independent_sources": 2}])
    insert_rows("news_cluster_articles", [
        {"article_id": "a1", "cluster_id": "c1", "title": "Rotterdam dockworkers strike from Monday", "domain": "a.com", "seen_at": now},
        {"article_id": "a2", "cluster_id": "c1", "title": "Port of Rotterdam strike announced", "domain": "b.com", "seen_at": now},
    ])
    items = [i for i in store.build_items() if i.source_type == "news"]
    assert len(items) == 1 and items[0].item_id == "news:c1" and "reported by 2 independent" in items[0].text()

    reader = make_reader(FakeLLM(), log=store.DbCallLogger())
    pending = store.pending_items(items, "test-model")
    assert len(pending) == 1
    results, stats = reader.read(pending)
    assert store.save_results(results, "test-model") == 1
    row = run_query("SELECT * FROM events")[0]
    assert row["event_id"] == "news:c1" and row["status"] == "expected" and row["start_date"] == date(2026, 11, 16)
    assert row["independent_sources"] == 2 and row["locations"] == ["Rotterdam"] and row["read_from"] == "llm"
    assert store.pending_items(items, "test-model") == []                  # unchanged text -> nothing to do
    changed = ReadItem(items[0].item_id, "news", items[0].reference_date, items[0].lines + ["headline: more news"], items[0].meta)
    assert store.pending_items([changed], "test-model") == [changed]       # changed text -> read again
    calls = run_query("SELECT kind, status, batch_size, input_tokens FROM llm_calls ORDER BY call_id")
    assert [c["kind"] for c in calls] == ["cache_summary", "call"] and calls[1]["status"] == "ok" and calls[1]["batch_size"] == 1


def test_store_builds_notice_items_from_federal_register(fr_raw):
    from src.reader import store

    fr_raw.execute("""INSERT INTO fivetran_raw_federal_register.documents VALUES ('2026-1', 'Steel duties', 'Proposed Rule',
                      current_date, current_date + 30, NULL, 'Effective in 30 days.', 'Raises duties.', 'ITC', 'u', false, now())""")
    notices = [i for i in store.build_items() if i.source_type == "notice"]
    assert len(notices) == 1 and notices[0].item_id == "notice:2026-1"
    assert "title: Steel duties" in notices[0].text() and "dates: Effective in 30 days." in notices[0].text()


# -- tracing -------------------------------------------------------------------------------------

def test_tracing_is_a_noop_without_phoenix_key(monkeypatch):
    from src.agent import observability
    from src.reader import tracing

    monkeypatch.delenv("PHOENIX_API_KEY", raising=False)
    monkeypatch.setattr(observability, "_configured", False)
    assert tracing.setup_tracing() is None
    with tracing.span("reader.test", items=3) as s:
        assert s is not None
