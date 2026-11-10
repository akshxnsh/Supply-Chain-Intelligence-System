-- 004: clean events (output of the Gemini reader) and the LLM call log.

CREATE TABLE IF NOT EXISTS events (
    event_id            TEXT PRIMARY KEY,            -- 'news:<cluster_id>' or 'notice:<document_number>'
    source_type         TEXT NOT NULL,               -- news | notice
    source_ref          TEXT NOT NULL,               -- cluster_id / document_number
    relevant            BOOLEAN NOT NULL,            -- could this disrupt shipping, trade or import cost?
    event_type          TEXT NOT NULL,
    status              TEXT NOT NULL,               -- happened | ongoing | expected | unknown
    direction           TEXT NOT NULL,               -- delay | higher_cost | both | none | unknown
    locations           TEXT[] NOT NULL DEFAULT '{}',
    countries           TEXT[] NOT NULL DEFAULT '{}',
    products            TEXT[] NOT NULL DEFAULT '{}',
    start_date          DATE,
    end_date            DATE,
    date_clarity        TEXT NOT NULL,               -- explicit | implied | unclear  (how clearly the text states the date)
    location_clarity    TEXT NOT NULL,
    summary             TEXT NOT NULL,
    independent_sources INTEGER NOT NULL DEFAULT 1,  -- from step 5 (news) ; 1 for an official notice
    reference_date      DATE NOT NULL,               -- date the text was published / first seen
    content_hash        TEXT NOT NULL,               -- hash of the text the reader saw (+ prompt version + model)
    reader_model        TEXT NOT NULL,
    prompt_version      TEXT NOT NULL,
    read_from           TEXT NOT NULL,               -- llm | cache
    read_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_events_status_start   ON events (status, start_date);
CREATE INDEX IF NOT EXISTS idx_events_relevant_ref   ON events (relevant, reference_date DESC);
CREATE INDEX IF NOT EXISTS idx_events_source         ON events (source_type, source_ref);

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id        BIGSERIAL PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    purpose        TEXT NOT NULL,                    -- reader | judge
    kind           TEXT NOT NULL,                    -- call | cache_summary
    model          TEXT,
    prompt_version TEXT,
    batch_size     INTEGER,
    attempt        INTEGER,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    latency_ms     DOUBLE PRECISION,
    cache_hits     INTEGER NOT NULL DEFAULT 0,
    cache_misses   INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL,                    -- ok | retry | error | parse_error | cache
    error          TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_purpose ON llm_calls (purpose, created_at DESC);
