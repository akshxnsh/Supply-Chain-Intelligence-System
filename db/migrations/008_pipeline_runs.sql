-- 008: one row per run of the whole pipeline (scheduled or manual), so "when did it last run and what did it do" is answerable.

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id       BIGSERIAL PRIMARY KEY,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    trigger      TEXT NOT NULL,                    -- schedule | manual-cli | manual-api
    status       TEXT NOT NULL DEFAULT 'running',  -- running | ok | partial | error | skipped_locked
    steps        JSONB NOT NULL DEFAULT '[]',      -- [{name, status, seconds, summary | error}]
    summary      TEXT
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_started ON pipeline_runs (started_at DESC);
