"""Step 5 tests: headline clustering (pure) and the database glue (real Postgres)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.events.dedupe import (Article, Clusterer, cluster_articles, jaccard, registrable_domain,
                               significant_words)

T0 = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)


def art(i, title, domain, hours=0.0, country=None):
    return Article(f"a{i}", title, domain, f"https://{domain}/{i}", T0 + timedelta(hours=hours), country)


BALTIMORE = [
    art(1, "Francis Scott Key Bridge collapses after ship strike, Port of Baltimore closed", "cnn.com", 0),
    art(2, "Baltimore bridge collapses after container ship strike; port closed - Reuters", "reuters.com", 1),
    art(3, "Port of Baltimore closed after Key Bridge collapse", "www.nytimes.com", 2),
    art(4, "Francis Scott Key Bridge collapses after ship strike, Port of Baltimore closed - MSN", "msn.com", 3),
]


def test_registrable_domain():
    assert registrable_domain("www.news.bbc.co.uk") == "bbc.co.uk"
    assert registrable_domain("WWW.Reuters.com") == "reuters.com"
    assert registrable_domain("edition.cnn.com") == "cnn.com"
    assert registrable_domain(None) == "" and registrable_domain("") == ""


def test_significant_words_drops_outlet_suffix_stopwords_and_plurals():
    w = significant_words("Dockworkers strike shuts Rotterdam terminals - Reuters")
    assert w == {"dockworker", "strike", "shut", "rotterdam", "terminal"}
    assert significant_words("The news of the day") == frozenset({"day"})
    assert "2026" in significant_words("Tariff of 25 percent from 2026")  # numbers matter
    assert jaccard(frozenset(), frozenset({"a"})) == 0.0


def test_same_event_headlines_form_one_cluster_and_unrelated_stay_apart():
    unrelated = [
        art(5, "Dockworkers strike shuts Rotterdam container terminals", "dutchnews.nl", 4),
        art(6, "Port strike in Hamburg delays container ships", "dw.com", 5),
        art(7, "Local cricket team wins final", "sports.com", 5),
    ]
    clusters = cluster_articles(BALTIMORE + unrelated)
    sizes = sorted(len(c.articles) for c in clusters)
    assert sizes == [1, 1, 1, 4]  # Baltimore story grouped; Rotterdam, Hamburg, cricket separate


def test_syndicated_copy_is_not_an_independent_source():
    (cluster,) = cluster_articles(BALTIMORE)
    s = cluster.summary()
    assert s["article_count"] == 4 and s["distinct_domains"] == 4
    assert s["independent_sources"] == 3  # the MSN copy of the CNN headline does not count
    msn = next(a for a in cluster.articles if a.domain == "msn.com")
    assert msn.syndicated and not next(a for a in cluster.articles if a.domain == "cnn.com").syndicated


def test_same_outlet_repeating_itself_counts_once():
    arts = [art(1, "Suez Canal closed after grounding of container ship", "bbc.com", 0),
            art(2, "Suez Canal closed after grounding of container ship", "www.bbc.com", 1)]
    (cluster,) = cluster_articles(arts)
    assert cluster.summary()["independent_sources"] == 1 and cluster.summary()["distinct_domains"] == 1


def test_time_window_keeps_old_and_new_stories_apart():
    old = art(1, "Port of Baltimore closed after Key Bridge collapse", "cnn.com", 0)
    new = art(2, "Port of Baltimore closed after Key Bridge collapse", "bbc.com", 24 * 5)  # five days later
    assert len(cluster_articles([old, new])) == 2
    close = art(3, "Port of Baltimore closed after Key Bridge collapse", "bbc.com", 24)
    assert len(cluster_articles([old, close])) == 1


def test_min_shared_words_guards_against_tiny_overlap():
    a = art(1, "Strike halts port", "a.com", 0)       # words: strike, halt, port
    b = art(2, "Strike halts rail", "b.com", 1)       # shares strike, halt (2 < MIN_SHARED)
    assert len(cluster_articles([a, b])) == 2


def test_representative_is_the_most_central_headline():
    (cluster,) = cluster_articles(BALTIMORE[:3])
    assert cluster.summary()["representative_title"] in {a.title for a in BALTIMORE[:3]}
    assert cluster.summary()["first_seen"] == T0 and cluster.summary()["last_seen"] == T0 + timedelta(hours=2)


def test_incremental_clusterer_extends_preloaded_cluster_and_tracks_touched():
    (existing,) = cluster_articles(BALTIMORE[:2])
    c = Clusterer([existing])
    cid = c.add(art(9, "Port of Baltimore closed after Key Bridge collapse", "bloomberg.com", 4))
    assert cid == existing.cluster_id and c.touched == {existing.cluster_id}
    other = c.add(art(10, "Typhoon forces Shanghai port to suspend operations", "scmp.com", 4))
    assert other != existing.cluster_id and other in c.touched


def test_summary_collects_countries_and_queries():
    a1 = art(1, "Port of Baltimore closed after Key Bridge collapse", "cnn.com", 0, country="United States")
    a1.query_name = "ports"
    a2 = art(2, "Baltimore port closed after Key Bridge collapse", "bbc.co.uk", 1, country="United Kingdom")
    a2.query_name = "shipping"
    (cluster,) = cluster_articles([a1, a2])
    s = cluster.summary()
    assert s["countries"] == ["United Kingdom", "United States"] and s["query_names"] == ["ports", "shipping"]


# -- database glue --------------------------------------------------------------

@pytest.fixture()
def gdelt_raw(pg_url):
    import psycopg

    # pg_url's search_path is the scratch schema holding our migrated tables; the Fivetran schema is created qualified
    with psycopg.connect(pg_url, autocommit=True) as c:
        c.execute('DROP SCHEMA IF EXISTS "fivetran_raw_gdelt" CASCADE')
        c.execute('CREATE SCHEMA "fivetran_raw_gdelt"')
        c.execute("""CREATE TABLE fivetran_raw_gdelt.articles (article_id text primary key, url text, title text, domain text,
                     language text, source_country text, seen_at timestamptz, query_name text,
                     _fivetran_deleted boolean, _fivetran_synced timestamptz)""")
        c.execute("TRUNCATE news_cluster_articles, news_clusters CASCADE")
        yield c
        c.execute('DROP SCHEMA IF EXISTS "fivetran_raw_gdelt" CASCADE')


def _insert(c, articles):
    for a in articles:
        c.execute("INSERT INTO fivetran_raw_gdelt.articles VALUES (%s,%s,%s,%s,'English','United States',%s,'ports',false,now())",
                  (a.article_id, a.url, a.title, a.domain, a.seen_at))


def test_run_dedupe_stores_clusters_and_is_idempotent(gdelt_raw):
    from src.events.cluster_store import run_dedupe, summary_numbers
    from src.ingestion.db import run_query

    _insert(gdelt_raw, BALTIMORE + [art(7, "Local cricket team wins final", "sports.com", 5)])
    stats = run_dedupe()
    assert stats == {"new_articles": 5, "new_clusters": 2, "joined_existing": 3, "touched_clusters": 2}
    rows = {r["article_count"]: r for r in run_query("SELECT * FROM news_clusters")}
    assert rows[4]["independent_sources"] == 3 and rows[4]["distinct_domains"] == 4 and rows[1]["independent_sources"] == 1
    assert run_query("SELECT count(*) AS n FROM news_cluster_articles WHERE syndicated")[0]["n"] == 1

    assert run_dedupe()["new_articles"] == 0  # nothing new -> nothing changes
    assert summary_numbers()["clusters"] == 2 and summary_numbers()["articles"] == 5


def test_run_dedupe_adds_new_article_to_existing_cluster(gdelt_raw):
    from src.events.cluster_store import run_dedupe
    from src.ingestion.db import run_query

    _insert(gdelt_raw, BALTIMORE[:2])
    run_dedupe()
    _insert(gdelt_raw, [art(9, "Port of Baltimore closed after Key Bridge collapse", "bloomberg.com", 6)])
    stats = run_dedupe()
    assert stats["new_articles"] == 1 and stats["new_clusters"] == 0 and stats["joined_existing"] == 1
    (row,) = run_query("SELECT article_count, independent_sources FROM news_clusters")
    assert row["article_count"] == 3 and row["independent_sources"] == 3


def test_run_dedupe_ignores_soft_deleted_and_untitled(gdelt_raw):
    from src.events.cluster_store import run_dedupe

    gdelt_raw.execute("INSERT INTO fivetran_raw_gdelt.articles VALUES ('x1','u',NULL,'d.com','English','X',now(),'ports',false,now())")
    gdelt_raw.execute("INSERT INTO fivetran_raw_gdelt.articles VALUES ('x2','u','Port strike delays ships','d.com','English','X',now(),'ports',true,now())")
    assert run_dedupe()["new_articles"] == 0
