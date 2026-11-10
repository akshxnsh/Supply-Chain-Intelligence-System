-- 002: secondary indexes, one per real query shape in src/ingestion/queries.py.
-- (A tariff_updates(effective_date) index was tried and removed: the query matches too many rows, and it measured slower.)
-- scripts/benchmark_db.py measures every query before and after this file.

CREATE INDEX IF NOT EXISTS idx_events_published_at      ON disruption_events (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_weather_start_time       ON weather_alerts (start_time DESC);

CREATE INDEX IF NOT EXISTS idx_bsup_business_category   ON business_suppliers (business_id, product_category);
CREATE INDEX IF NOT EXISTS idx_bsup_business_country    ON business_suppliers (business_id, lower(country));
CREATE INDEX IF NOT EXISTS idx_altsup_category_rel      ON alternative_suppliers (product_category, reliability_score DESC);

CREATE INDEX IF NOT EXISTS idx_orders_business_status   ON pending_orders (business_id, status);
CREATE INDEX IF NOT EXISTS idx_ship_business_status_eta ON shipment_timetable (business_id, status, expected_arrival_date);
CREATE INDEX IF NOT EXISTS idx_ship_supplier            ON shipment_timetable (supplier_id);
CREATE INDEX IF NOT EXISTS idx_inventory_business       ON inventory (business_id);

CREATE INDEX IF NOT EXISTS idx_completed_supplier       ON completed_orders (supplier_id, status, expected_delivery_date DESC);
CREATE INDEX IF NOT EXISTS idx_reviews_supplier         ON supplier_reviews (supplier_id, review_date DESC);

CREATE INDEX IF NOT EXISTS idx_alerts_business_created  ON agent_alerts (business_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_severity          ON agent_alerts (severity_score DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_business_disrup   ON agent_alerts (business_id, disruption_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_calib_type_region        ON agent_calibration (event_type, region, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_calib_region_created     ON agent_calibration (region, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_traces_span_created      ON phoenix_traces (span_id, created_at DESC);
