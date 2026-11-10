-- 003: news de-duplication. Many articles about one event -> one cluster; the reader (step 6) reads clusters.
-- Source of articles: fivetran_raw_gdelt.articles (owned by Fivetran, never migrated here).

CREATE TABLE IF NOT EXISTS news_clusters (
    cluster_id          TEXT PRIMARY KEY,            -- = article_id of the first article seen
    representative_title TEXT NOT NULL,
    representative_url  TEXT,
    first_seen          TIMESTAMPTZ NOT NULL,
    last_seen           TIMESTAMPTZ NOT NULL,
    article_count       INTEGER NOT NULL,
    distinct_domains    INTEGER NOT NULL,            -- different outlets, duplicates included
    independent_sources INTEGER NOT NULL,            -- different outlets after collapsing near-identical (syndicated) copies
    countries           TEXT[] NOT NULL DEFAULT '{}',
    query_names         TEXT[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS news_cluster_articles (
    article_id  TEXT PRIMARY KEY,                    -- one article belongs to exactly one cluster
    cluster_id  TEXT NOT NULL REFERENCES news_clusters (cluster_id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    domain      TEXT,
    url         TEXT,
    seen_at     TIMESTAMPTZ NOT NULL,
    syndicated  BOOLEAN NOT NULL DEFAULT FALSE       -- near-identical copy of an earlier article in the cluster
);

CREATE INDEX IF NOT EXISTS idx_clusters_last_seen        ON news_clusters (last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_cluster_articles_cluster  ON news_cluster_articles (cluster_id);
CREATE INDEX IF NOT EXISTS idx_cluster_articles_seen     ON news_cluster_articles (seen_at DESC);
