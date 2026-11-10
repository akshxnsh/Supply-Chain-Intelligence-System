-- 009: history of notification decisions. One row each time ChainGuard decides an alert should notify the trader
-- (first time, or again because it got worse). Nothing is delivered anywhere yet (no email / chat channel is built): this is the log.
-- The alerts table keeps only the LAST notification per alert; this table keeps all of them.

CREATE TABLE IF NOT EXISTS alert_notifications (
    id                BIGSERIAL PRIMARY KEY,
    alert_id          TEXT NOT NULL,
    business_id       TEXT NOT NULL,
    notified_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    level             TEXT NOT NULL,                 -- always 'notify' today
    reason            TEXT NOT NULL,                 -- first notification | expected loss rose ... | confidence band rose | level rose to notify
    title             TEXT NOT NULL,                 -- snapshot, so the history still reads right if the alert changes later
    source            TEXT,
    expected_loss_usd DOUBLE PRECISION NOT NULL,
    confidence_band   TEXT NOT NULL,
    stockout_risk     BOOLEAN NOT NULL DEFAULT FALSE,
    act_by            DATE,
    action            TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_notifications_business ON alert_notifications (business_id, notified_at DESC);

-- Deliberately NOT backfilled: the only notifications recorded before this table existed came from one early test run made under
-- scoring rules that were later removed (a guessed tariff rate), so they would show decisions ChainGuard would not make today.
-- The history starts with the first notification decided after this migration.
