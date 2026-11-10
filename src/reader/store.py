"""Database side of the reader: build items from clusters/notices, save events, write the LLM call log."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from src.reader.prompt import PROMPT_VERSION
from src.reader.reader import ReadResult
from src.reader.schema import ReadItem
from src.ingestion.db import get_pool, run_query

logger = logging.getLogger(__name__)

SQL_RECENT_CLUSTERS = """
    SELECT c.cluster_id, c.first_seen, c.independent_sources, c.article_count, c.representative_url
    FROM news_clusters c
    WHERE c.last_seen >= now() - make_interval(days => %(days)s)
    ORDER BY c.last_seen DESC
    LIMIT %(limit)s
"""

SQL_CLUSTER_TITLES = """
    SELECT cluster_id, title, domain, seen_at
    FROM news_cluster_articles
    WHERE cluster_id = ANY(%(ids)s) AND NOT syndicated
    ORDER BY cluster_id, seen_at
"""

SQL_RECENT_NOTICES = """
    SELECT document_number, title, doc_type, publication_date, effective_on, comments_close_on, dates_text, abstract, agencies, url
    FROM fivetran_raw_federal_register.documents
    WHERE NOT _fivetran_deleted AND publication_date >= current_date - %(days)s::int
    ORDER BY publication_date DESC
    LIMIT %(limit)s
"""

SQL_EXISTING_HASHES = "SELECT event_id, content_hash FROM events WHERE event_id = ANY(%(ids)s)"

UPSERT_EVENT = """
    INSERT INTO events (event_id, source_type, source_ref, relevant, event_type, status, direction, locations, countries,
                        products, start_date, end_date, rate_percent, date_clarity, location_clarity, summary, independent_sources,
                        reference_date, content_hash, reader_model, prompt_version, read_from)
    VALUES (%(event_id)s, %(source_type)s, %(source_ref)s, %(relevant)s, %(event_type)s, %(status)s, %(direction)s,
            %(locations)s, %(countries)s, %(products)s, %(start_date)s, %(end_date)s, %(rate_percent)s, %(date_clarity)s,
            %(location_clarity)s, %(summary)s, %(independent_sources)s, %(reference_date)s, %(content_hash)s,
            %(reader_model)s, %(prompt_version)s, %(read_from)s)
    ON CONFLICT (event_id) DO UPDATE SET
        relevant = EXCLUDED.relevant, event_type = EXCLUDED.event_type, status = EXCLUDED.status,
        direction = EXCLUDED.direction, locations = EXCLUDED.locations, countries = EXCLUDED.countries,
        products = EXCLUDED.products, start_date = EXCLUDED.start_date, end_date = EXCLUDED.end_date, rate_percent = EXCLUDED.rate_percent,
        date_clarity = EXCLUDED.date_clarity, location_clarity = EXCLUDED.location_clarity, summary = EXCLUDED.summary,
        independent_sources = EXCLUDED.independent_sources, reference_date = EXCLUDED.reference_date,
        content_hash = EXCLUDED.content_hash, reader_model = EXCLUDED.reader_model,
        prompt_version = EXCLUDED.prompt_version, read_from = EXCLUDED.read_from, read_at = now(), updated_at = now()
"""

INSERT_LLM_CALL = """
    INSERT INTO llm_calls (purpose, kind, model, prompt_version, batch_size, attempt, input_tokens, output_tokens,
                           latency_ms, cache_hits, cache_misses, status, error)
    VALUES (%(purpose)s, %(kind)s, %(model)s, %(prompt_version)s, %(batch_size)s, %(attempt)s, %(input_tokens)s,
            %(output_tokens)s, %(latency_ms)s, %(cache_hits)s, %(cache_misses)s, %(status)s, %(error)s)
"""


class DbCallLogger:
    """Writes every model call (and the per-run cache summary) to the llm_calls table."""

    def log(self, entry: dict) -> None:
        row = {"purpose": "reader", "kind": "call", "model": None, "prompt_version": None, "batch_size": None,
               "attempt": None, "input_tokens": None, "output_tokens": None, "latency_ms": None,
               "cache_hits": 0, "cache_misses": 0, "status": "ok", "error": None, **entry}
        try:
            with get_pool().connection() as conn:
                conn.execute(INSERT_LLM_CALL, row)
        except Exception as exc:  # noqa: BLE001 - logging must never break a read
            logger.warning("could not write llm_calls row: %s", exc)


def _news_item(c: dict, titles: list[dict]) -> ReadItem | None:
    if not titles:
        return None
    lines = [f"headline: {t['title']}" for t in titles[:4]]
    lines.append(f"reported by {c['independent_sources']} independent outlet(s)")
    first = c["first_seen"]
    ref = (first.astimezone(timezone.utc) if isinstance(first, datetime) else first).date() if first else date.today()
    return ReadItem(f"news:{c['cluster_id']}", "news", ref, lines,
                    {"cluster_id": c["cluster_id"], "independent_sources": c["independent_sources"],
                     "url": c.get("representative_url")})


def _notice_item(d: dict) -> ReadItem:
    lines = [f"type: {d['doc_type']}", f"agencies: {d['agencies']}", f"title: {d['title']}"]
    if d.get("abstract"):
        lines.append(f"abstract: {d['abstract'][:600]}")
    if d.get("dates_text"):
        lines.append(f"dates: {d['dates_text'][:300]}")
    if d.get("effective_on"):
        lines.append(f"effective_on: {d['effective_on'].isoformat()}")
    if d.get("comments_close_on"):
        lines.append(f"comments_close_on: {d['comments_close_on'].isoformat()}")
    return ReadItem(f"notice:{d['document_number']}", "notice", d["publication_date"], lines,
                    {"document_number": d["document_number"], "independent_sources": 1, "url": d.get("url")})


def build_items(days: int = 7, notice_days: int = 60, limit: int = 500) -> list[ReadItem]:
    """All recent news clusters and trade notices as reader items."""
    clusters = run_query(SQL_RECENT_CLUSTERS, {"days": days, "limit": limit})
    titles: dict[str, list[dict]] = {}
    if clusters:
        for t in run_query(SQL_CLUSTER_TITLES, {"ids": [c["cluster_id"] for c in clusters]}):
            titles.setdefault(t["cluster_id"], []).append(t)
    items = [i for c in clusters if (i := _news_item(c, titles.get(c["cluster_id"], [])))]
    items += [_notice_item(d) for d in run_query(SQL_RECENT_NOTICES, {"days": notice_days, "limit": limit})]
    return items


def pending_items(items: list[ReadItem], model: str) -> list[ReadItem]:
    """Items whose text (or the prompt/model) changed since the stored event; unchanged ones are skipped."""
    if not items:
        return []
    existing = {r["event_id"]: r["content_hash"]
                for r in run_query(SQL_EXISTING_HASHES, {"ids": [i.item_id for i in items]})}
    return [i for i in items if existing.get(i.item_id) != i.content_hash(model, PROMPT_VERSION)]


def save_results(results: list[ReadResult], model: str) -> int:
    """Upsert one events row per successfully read item. Failed items are left for the next run."""
    saved = 0
    with get_pool().connection() as conn:
        for r in results:
            if r.event is None:
                continue
            e = r.event
            conn.execute(UPSERT_EVENT, {
                "event_id": r.item.item_id, "source_type": r.item.source_type,
                "source_ref": r.item.item_id.split(":", 1)[1], "relevant": e.relevant, "event_type": e.event_type,
                "status": e.status, "direction": e.direction, "locations": e.locations, "countries": e.countries,
                "products": e.products, "start_date": e.start_date, "end_date": e.end_date, "rate_percent": e.rate_percent,
                "date_clarity": e.date_clarity, "location_clarity": e.location_clarity, "summary": e.summary or "",
                "independent_sources": int(r.item.meta.get("independent_sources", 1)),
                "reference_date": r.item.reference_date, "content_hash": r.item.content_hash(model, PROMPT_VERSION),
                "reader_model": model, "prompt_version": PROMPT_VERSION, "read_from": r.source,
            })
            saved += 1
    return saved
