"""Database side of step 5: read new GDELT articles, cluster them, store clusters + membership.

    python -m src.events.cluster_store          # cluster everything not clustered yet, print the numbers

Idempotent: an article that already belongs to a cluster is never reprocessed; re-running only handles new rows.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from src.events.dedupe import WINDOW_HOURS, Article, Cluster, Clusterer
from src.ingestion.db import get_pool, run_query

logger = logging.getLogger(__name__)

SQL_NEW_ARTICLES = """
    SELECT a.article_id, a.title, a.domain, a.url, a.seen_at, a.source_country AS country, a.query_name
    FROM fivetran_raw_gdelt.articles a
    WHERE NOT a._fivetran_deleted
      AND a.title IS NOT NULL AND a.seen_at IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM news_cluster_articles c WHERE c.article_id = a.article_id)
    ORDER BY a.seen_at, a.article_id
"""

SQL_OPEN_CLUSTER_MEMBERS = """
    SELECT m.cluster_id, m.article_id, m.title, m.domain, m.url, m.seen_at, m.syndicated
    FROM news_cluster_articles m
    JOIN news_clusters c ON c.cluster_id = m.cluster_id
    WHERE c.last_seen >= %(since)s
"""

UPSERT_CLUSTER = """
    INSERT INTO news_clusters (cluster_id, representative_title, representative_url, first_seen, last_seen,
                               article_count, distinct_domains, independent_sources, countries, query_names)
    VALUES (%(cluster_id)s, %(representative_title)s, %(representative_url)s, %(first_seen)s, %(last_seen)s,
            %(article_count)s, %(distinct_domains)s, %(independent_sources)s, %(countries)s, %(query_names)s)
    ON CONFLICT (cluster_id) DO UPDATE SET
        representative_title = EXCLUDED.representative_title, representative_url = EXCLUDED.representative_url,
        first_seen = EXCLUDED.first_seen, last_seen = EXCLUDED.last_seen, article_count = EXCLUDED.article_count,
        distinct_domains = EXCLUDED.distinct_domains, independent_sources = EXCLUDED.independent_sources,
        countries = EXCLUDED.countries, query_names = EXCLUDED.query_names, updated_at = now()
"""

INSERT_MEMBER = """
    INSERT INTO news_cluster_articles (article_id, cluster_id, title, domain, url, seen_at, syndicated)
    VALUES (%(article_id)s, %(cluster_id)s, %(title)s, %(domain)s, %(url)s, %(seen_at)s, %(syndicated)s)
    ON CONFLICT (article_id) DO NOTHING
"""


def _load_open_clusters(since) -> list[Cluster]:
    by_cluster: dict[str, list[Article]] = {}
    for r in run_query(SQL_OPEN_CLUSTER_MEMBERS, {"since": since}):
        by_cluster.setdefault(r["cluster_id"], []).append(
            Article(r["article_id"], r["title"], r["domain"], r["url"], r["seen_at"], syndicated=r["syndicated"]))
    return [Cluster(cid, arts) for cid, arts in by_cluster.items()]


def run_dedupe(window_hours: int = WINDOW_HOURS) -> dict:
    """Cluster all not-yet-clustered articles. Returns counts for logging / PROGRESS."""
    new_rows = run_query(SQL_NEW_ARTICLES)
    if not new_rows:
        return {"new_articles": 0, "new_clusters": 0, "joined_existing": 0, "touched_clusters": 0}

    first_seen = new_rows[0]["seen_at"]
    existing = _load_open_clusters(first_seen - timedelta(hours=window_hours))
    existing_ids = {c.cluster_id for c in existing}
    clusterer = Clusterer(existing, window_hours=window_hours)
    new_articles = [Article(r["article_id"], r["title"], r["domain"], r["url"], r["seen_at"],
                            r["country"], r["query_name"]) for r in new_rows]
    for art in new_articles:
        clusterer.add(art)

    new_cluster_ids = {cid for cid in clusterer.touched if cid not in existing_ids}
    with get_pool().connection() as conn:
        with conn.cursor() as cur:
            for cid in clusterer.touched:
                cur.execute(UPSERT_CLUSTER, clusterer.clusters[cid].summary())  # parent row first (foreign key)
            for art in new_articles:
                cur.execute(INSERT_MEMBER, {"article_id": art.article_id, "cluster_id": clusterer.assigned[art.article_id],
                                            "title": art.title, "domain": art.domain, "url": art.url,
                                            "seen_at": art.seen_at, "syndicated": art.syndicated})
    stats = {
        "new_articles": len(new_articles),
        "new_clusters": len(new_cluster_ids),
        "joined_existing": len(new_articles) - len(new_cluster_ids),  # every new cluster is opened by exactly one article
        "touched_clusters": len(clusterer.touched),
    }
    logger.info("dedupe: %s", stats)
    return stats


def summary_numbers() -> dict:
    """Whole-table numbers (for the PROGRESS log)."""
    r = run_query("""
        SELECT count(*) AS clusters, coalesce(sum(article_count), 0) AS articles,
               count(*) FILTER (WHERE article_count > 1) AS multi_article_clusters,
               coalesce(max(article_count), 0) AS largest_cluster,
               coalesce(round(avg(independent_sources)::numeric, 2), 0)::float AS avg_independent_sources
        FROM news_clusters""")[0]
    return r


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    print(run_dedupe())
    print(summary_numbers())
