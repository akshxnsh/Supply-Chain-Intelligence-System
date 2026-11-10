-- 005: risk alerts, trader settings, and the tariff rate the reader may extract.

ALTER TABLE events ADD COLUMN IF NOT EXISTS rate_percent DOUBLE PRECISION;

-- the trader's own settings (low default threshold; the trader changes it)
CREATE TABLE IF NOT EXISTS trader_settings (
    business_id          TEXT PRIMARY KEY,
    notify_threshold_usd DOUBLE PRECISION NOT NULL DEFAULT 2000,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- one row per (business, real-world signal); re-evaluated each run, notified only when it gets worse
CREATE TABLE IF NOT EXISTS alerts (
    alert_id             TEXT PRIMARY KEY,              -- hash(business_id, signal dedupe key)
    business_id          TEXT NOT NULL,
    alert_type           TEXT NOT NULL,                 -- now | heads_up
    level                TEXT NOT NULL,                 -- notify | watch | log
    signal_kind          TEXT NOT NULL,                 -- delay | tariff | fx
    source               TEXT NOT NULL,                 -- gdelt | federal_register | gdacs | open_meteo | ecb
    event_type           TEXT NOT NULL,
    title                TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'open',  -- open | acknowledged | resolved
    affected_shipments   JSONB NOT NULL DEFAULT '[]',
    affected_suppliers   JSONB NOT NULL DEFAULT '[]',
    exposure_usd         DOUBLE PRECISION NOT NULL,     -- possible loss if it happens
    expected_loss_usd    DOUBLE PRECISION NOT NULL,     -- likelihood x possible loss (the risk score)
    loss_components      JSONB NOT NULL DEFAULT '{}',
    confidence_band      TEXT NOT NULL,                 -- high | medium | low
    confidence_score     DOUBLE PRECISION NOT NULL,
    confidence_reasons   JSONB NOT NULL DEFAULT '[]',
    stockout_risk        BOOLEAN NOT NULL DEFAULT FALSE,
    lead_time_days       INTEGER,                       -- days until it starts (heads-up alerts)
    event_start          DATE,
    event_end            DATE,
    act_by               DATE,                          -- latest date to act (e.g. order a replacement)
    action               TEXT,                          -- recommended action (step 8 refines it)
    evidence             JSONB NOT NULL DEFAULT '[]',   -- source ids / urls the alert is built from
    explanation          JSONB NOT NULL DEFAULT '[]',   -- why it did (or did not) notify
    assumptions          JSONB NOT NULL DEFAULT '[]',
    first_seen           TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen            TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_notified_at     TIMESTAMPTZ,
    last_notified_level  TEXT,
    last_notified_loss   DOUBLE PRECISION,
    last_notified_band   TEXT,
    notified_count       INTEGER NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alerts2_business_level ON alerts (business_id, level, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_alerts2_act_by         ON alerts (act_by) WHERE act_by IS NOT NULL;
