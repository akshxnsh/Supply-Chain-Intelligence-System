-- 001: core tables (PostgreSQL). No secondary indexes yet - see 002.
-- Every table has a primary key and an updated_at column (used for freshness checks).
-- No schema qualifier on purpose: scripts/benchmark_db.py runs this file inside a scratch schema.

CREATE TABLE IF NOT EXISTS disruption_events (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    headline      TEXT NOT NULL,
    location_name TEXT,
    lat           DOUBLE PRECISION,
    lon           DOUBLE PRECISION,
    severity_raw  DOUBLE PRECISION,
    published_at  TIMESTAMPTZ NOT NULL,
    inserted_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS weather_alerts (
    id             TEXT PRIMARY KEY,
    region         TEXT NOT NULL,
    alert_type     TEXT NOT NULL,
    severity       DOUBLE PRECISION,
    start_time     TIMESTAMPTZ NOT NULL,
    end_time       TIMESTAMPTZ,
    affected_ports TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alternative_suppliers (
    id                    TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    country               TEXT NOT NULL,
    product_category      TEXT NOT NULL,
    moq                   INTEGER,
    lead_time_days        INTEGER,
    unit_price_usd        DOUBLE PRECISION,
    reliability_score     DOUBLE PRECISION,
    geographic_risk_score DOUBLE PRECISION,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS business_suppliers (
    id               TEXT PRIMARY KEY,
    business_id      TEXT NOT NULL,
    supplier_name    TEXT NOT NULL,
    country          TEXT NOT NULL,
    product_category TEXT NOT NULL,
    annual_spend_usd DOUBLE PRECISION,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pending_orders (
    id               TEXT PRIMARY KEY,
    business_id      TEXT NOT NULL,
    client_id        TEXT,
    product_category TEXT NOT NULL,
    quantity         INTEGER NOT NULL,
    order_value_usd  DOUBLE PRECISION NOT NULL,
    required_by_date DATE NOT NULL,
    status           TEXT NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS shipment_timetable (
    id                    TEXT PRIMARY KEY,
    business_id           TEXT NOT NULL,
    supplier_id           TEXT NOT NULL,
    product_category      TEXT NOT NULL,
    quantity              INTEGER NOT NULL,
    shipment_value_usd    DOUBLE PRECISION NOT NULL,
    origin_port           TEXT,
    destination_port      TEXT,
    dispatched_date       DATE,
    expected_arrival_date DATE NOT NULL,
    etd                   TIMESTAMPTZ NOT NULL,
    eta                   TIMESTAMPTZ NOT NULL,
    journey_time_hours    DOUBLE PRECISION NOT NULL,
    route                 TEXT NOT NULL,
    status                TEXT NOT NULL,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_alerts (
    id            TEXT PRIMARY KEY,
    business_id   TEXT NOT NULL,
    disruption_id TEXT,
    severity_score DOUBLE PRECISION,
    exposure_usd  DOUBLE PRECISION,
    actions_json  TEXT,
    status        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS agent_calibration (
    id                   TEXT PRIMARY KEY,
    event_type           TEXT NOT NULL,
    region               TEXT,
    severity_scored      DOUBLE PRECISION,
    delay_days_predicted INTEGER,
    supplier_recommended TEXT,
    exposure_calculated  DOUBLE PRECISION,
    owner_approved       BOOLEAN,
    owner_override       BOOLEAN,
    rejection_reason     TEXT,
    actual_delay_days    INTEGER,
    supplier_delivered   BOOLEAN,
    hallucination_score  DOUBLE PRECISION,
    relevance_score      DOUBLE PRECISION,
    helpfulness_score    DOUBLE PRECISION,
    reasoning_score      DOUBLE PRECISION,
    calibration_applied  BOOLEAN,
    weighted_baseline    DOUBLE PRECISION,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS phoenix_traces (
    trace_id    TEXT NOT NULL,
    span_id     TEXT NOT NULL,
    tool_name   TEXT,
    input_json  TEXT,
    output_json TEXT,
    latency_ms  DOUBLE PRECISION,
    token_count INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trace_id, span_id)
);

CREATE TABLE IF NOT EXISTS port_activity (
    port_id            TEXT PRIMARY KEY,
    port_name          TEXT NOT NULL,
    congestion_score   DOUBLE PRECISION,
    vessel_delay_hours DOUBLE PRECISION,
    strike_flag        BOOLEAN,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tariff_updates (
    id                     TEXT PRIMARY KEY,
    country_of_origin      TEXT NOT NULL,
    product_category       TEXT NOT NULL,
    tariff_rate_percentage DOUBLE PRECISION NOT NULL,
    effective_date         DATE NOT NULL,
    description            TEXT,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS inventory (
    id                  TEXT PRIMARY KEY,
    business_id         TEXT NOT NULL,
    product_category    TEXT NOT NULL,
    inventory_value_usd DOUBLE PRECISION NOT NULL,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS completed_orders (
    id                     TEXT PRIMARY KEY,
    business_id            TEXT NOT NULL,
    supplier_id            TEXT NOT NULL,
    order_value_usd        DOUBLE PRECISION NOT NULL,
    ordered_date           DATE NOT NULL,
    expected_delivery_date DATE NOT NULL,
    actual_delivery_date   DATE,
    delay_days             INTEGER,
    defective_items_count  INTEGER,
    status                 TEXT NOT NULL,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS supplier_reviews (
    id          TEXT PRIMARY KEY,
    supplier_id TEXT NOT NULL,
    business_id TEXT NOT NULL,
    rating      DOUBLE PRECISION NOT NULL,
    review_text TEXT,
    review_date TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
