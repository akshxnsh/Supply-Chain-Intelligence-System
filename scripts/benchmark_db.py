"""Measure query times BEFORE and AFTER the indexes in db/migrations/002_indexes.sql.

What it does (all inside a throwaway schema, dropped at the end):
  1. runs 001_core_tables.sql (primary keys only),
  2. fills the tables with SYNTHETIC rows at a realistic scale (server-side generate_series),
  3. runs EXPLAIN (ANALYZE, FORMAT JSON) on every app query (SQL imported from
     src/ingestion/queries.py, so it is exactly what the app runs), several runs each,
  4. applies 002_indexes.sql + ANALYZE, measures again,
  5. writes docs/benchmarks/db_indexes.json and db_indexes.md.

The data is synthetic (random but with realistic skew); the numbers describe THIS database
on THIS machine/network. Say so wherever you quote them.

    python -m scripts.benchmark_db                 # uses DATABASE_URL from .env
    python -m scripts.benchmark_db --scale 0.2     # smaller (e.g. for Neon free tier storage)
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import ClientCursor
from psycopg.rows import dict_row

from src.ingestion.db import database_url
from src.ingestion.queries import BENCHMARK_QUERIES

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "db" / "migrations"
OUT_DIR = ROOT / "docs" / "benchmarks"

# Row counts at --scale 1.0
ROWS = {
    "disruption_events": 300_000,
    "weather_alerts": 100_000,
    "tariff_updates": 20_000,
    "business_suppliers": 5_000,      # 1,000 businesses x 5 suppliers
    "alternative_suppliers": 20_000,
    "pending_orders": 200_000,
    "shipment_timetable": 300_000,
    "completed_orders": 500_000,
    "supplier_reviews": 300_000,
    "agent_alerts": 100_000,
    "agent_calibration": 100_000,
    "inventory": 5_000,
}

BIZ = "biz-42"                                   # business used in the benchmark params
BIZ_SUPPLIERS = [f"sup-{n}" for n in range(206, 211)]  # its 5 suppliers (biz-42 = suppliers 206..210)


def n_(rows: int, scale: float) -> int:
    return max(100, int(rows * scale))


def populate(cur, scale: float) -> dict[str, int]:
    r = {k: n_(v, scale) for k, v in ROWS.items()}
    ns = r["business_suppliers"]
    biz = lambda col: f"'biz-' || ((({col}) - 1) / 5 + 1)"  # noqa: E731  supplier n -> business
    cats = "(ARRAY['auto_parts','fasteners','electronics','textiles','chemicals','food'])[1 + floor(random()*6)::int]"
    ctry = "(ARRAY['China','Germany','South Korea','India','USA','Mexico','Vietnam','Turkey'])[1 + floor(random()*8)::int]"

    cur.execute(f"""INSERT INTO disruption_events (id, source, headline, location_name, lat, lon, severity_raw, published_at)
        SELECT 'ev-'||g, 'gdelt', 'headline '||g, 'loc '||(g%500), random()*180-90, random()*360-180, random()*10,
               now() - random()*interval '730 days'
        FROM generate_series(1,{r['disruption_events']}) g""")
    cur.execute(f"""INSERT INTO weather_alerts (id, region, alert_type, severity, start_time, end_time, affected_ports)
        SELECT 'wx-'||g, 'region '||(g%300), 'storm', random()*10, t, t + interval '2 days', 'Port '||(g%200)
        FROM (SELECT g, now() - random()*interval '730 days' AS t FROM generate_series(1,{r['weather_alerts']}) g) s""")
    cur.execute(f"""INSERT INTO tariff_updates (id, country_of_origin, product_category, tariff_rate_percentage, effective_date)
        SELECT 'tf-'||g, {ctry}, {cats}, random()*30, (current_date - (random()*730)::int + 60)
        FROM generate_series(1,{r['tariff_updates']}) g""")
    cur.execute(f"""INSERT INTO business_suppliers (id, business_id, supplier_name, country, product_category, annual_spend_usd)
        SELECT 'sup-'||g, {biz('g')}, 'Supplier '||g, {ctry}, {cats}, random()*500000
        FROM generate_series(1,{ns}) g""")
    cur.execute(f"""INSERT INTO alternative_suppliers (id, name, country, product_category, moq, lead_time_days, unit_price_usd, reliability_score, geographic_risk_score)
        SELECT 'alt-'||g, 'Alt '||g, {ctry}, {cats}, 100, 3+(random()*30)::int, random()*10, random()*10, random()*10
        FROM generate_series(1,{r['alternative_suppliers']}) g""")
    cur.execute(f"""INSERT INTO pending_orders (id, business_id, client_id, product_category, quantity, order_value_usd, required_by_date, status)
        SELECT 'po-'||g, 'biz-'||(1+floor(random()*1000)::int), 'client-'||(g%5000), {cats}, 100, random()*100000,
               current_date + (random()*60)::int, CASE WHEN random() < 0.15 THEN 'pending' ELSE 'fulfilled' END
        FROM generate_series(1,{r['pending_orders']}) g""")
    cur.execute(f"""INSERT INTO shipment_timetable (id, business_id, supplier_id, product_category, quantity, shipment_value_usd,
                    origin_port, destination_port, dispatched_date, expected_arrival_date, etd, eta, journey_time_hours, route, status)
        SELECT 'shp-'||g, {biz('n')}, 'sup-'||n, {cats}, 100, random()*200000, 'Port A', 'Port B',
               d::date, (d + interval '20 days')::date, d, d + interval '20 days', 480, 'Port A > Port B',
               CASE WHEN transit THEN 'in_transit' ELSE 'delivered' END
        FROM (SELECT g, n, transit,
                     CASE WHEN transit THEN now() - random()*interval '15 days' ELSE now() - interval '30 days' - random()*interval '700 days' END AS d
              FROM (SELECT g, 1+floor(random()*{ns})::int AS n, random() < 0.10 AS transit
                    FROM generate_series(1,{r['shipment_timetable']}) g) a) b""")
    cur.execute(f"""INSERT INTO completed_orders (id, business_id, supplier_id, order_value_usd, ordered_date, expected_delivery_date,
                    actual_delivery_date, delay_days, defective_items_count, status)
        SELECT 'co-'||g, {biz('n')}, 'sup-'||n, random()*50000, d - 30, d, d + dl, dl, (random()*5)::int,
               CASE WHEN random() < 0.95 THEN 'delivered' ELSE 'cancelled' END
        FROM (SELECT g, 1+floor(random()*{ns})::int AS n, (current_date - (random()*730)::int) AS d, (random()*10)::int AS dl
              FROM generate_series(1,{r['completed_orders']}) g) a""")
    cur.execute(f"""INSERT INTO supplier_reviews (id, supplier_id, business_id, rating, review_text, review_date)
        SELECT 'rv-'||g, 'sup-'||n, {biz('n')}, 1+random()*4, 'review text '||g, now() - random()*interval '730 days'
        FROM (SELECT g, 1+floor(random()*{ns})::int AS n FROM generate_series(1,{r['supplier_reviews']}) g) a""")
    cur.execute(f"""INSERT INTO agent_alerts (id, business_id, disruption_id, severity_score, exposure_usd, actions_json, status, created_at)
        SELECT 'al-'||g, 'biz-'||(1+floor(random()*1000)::int), 'ev-'||(1+floor(random()*{r['disruption_events']})::int),
               random()*10, random()*500000, '[]', 'active', now() - random()*interval '365 days'
        FROM generate_series(1,{r['agent_alerts']}) g""")
    cur.execute(f"""INSERT INTO agent_calibration (id, event_type, region, severity_scored, delay_days_predicted, actual_delay_days,
                    hallucination_score, relevance_score, helpfulness_score, reasoning_score, calibration_applied, created_at)
        SELECT 'cal-'||g, 'port_disruption', 'biz-'||(1+floor(random()*1000)::int), random()*10, 5, (random()*10)::int,
               random()*0.3, 0.8, 0.8, 0.8, random() < 0.5, now() - random()*interval '365 days'
        FROM generate_series(1,{r['agent_calibration']}) g""")
    cur.execute(f"""INSERT INTO inventory (id, business_id, product_category, inventory_value_usd)
        SELECT 'inv-'||g, {biz('g')}, {cats}, random()*100000 FROM generate_series(1,{ns}) g""")
    return r


def params_for(cur) -> dict[str, dict]:
    """Realistic parameters; the supplier/business ids exist in the generated data."""
    cur.execute("SELECT id FROM disruption_events LIMIT 1")
    return {
        "recent_events": {"hours": 24},
        "business_suppliers": {"business_id": BIZ},
        "pending_orders": {"business_id": BIZ},
        "alternative_suppliers": {"product_category": "auto_parts", "exclude_country": "China"},
        "shipments_at_risk": {"business_id": BIZ, "supplier_ids": BIZ_SUPPLIERS, "window_days": 30},
        "recent_weather": {"hours_back": 48},
        "tariffs": {"days_back": 30},
        "completed_orders_many": {"supplier_ids": BIZ_SUPPLIERS},
        "reviews_many": {"supplier_ids": BIZ_SUPPLIERS},
        "timetable_join": {"business_id": BIZ},
        "alerts_page": {"business_id": BIZ, "limit": 10, "offset": 0},
        "alerts_all": {"limit": 20},
        "suppliers_overview": {"business_id": BIZ},
        "duplicate_alert": {"business_id": BIZ, "disruption_id": "ev-123", "hours": 24},
        "calibration_records": {"event_type": "port_disruption", "region": BIZ, "days_lookback": 180},
    }


def _nodes(plan: dict):
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


def measure(conn, name: str, sql: str, params: dict, runs: int) -> dict:
    times, plan_ms = [], []
    root = None
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params)  # warm-up (caches, plan)
        for _ in range(runs):
            cur.execute("EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params)
            doc = cur.fetchone()["QUERY PLAN"][0]
            times.append(doc["Execution Time"])
            plan_ms.append(doc["Planning Time"])
            root = doc["Plan"]
    kinds = sorted({n["Node Type"] for n in _nodes(root)})
    return {
        "query": name,
        "exec_ms_median": round(statistics.median(times), 3),
        "exec_ms_min": round(min(times), 3),
        "exec_ms_max": round(max(times), 3),
        "planning_ms_median": round(statistics.median(plan_ms), 3),
        "uses_seq_scan": any(k == "Seq Scan" for k in kinds),
        "uses_index": any("Index" in k for k in kinds),
        "node_types": kinds,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0, help="row-count multiplier (default 1.0)")
    ap.add_argument("--runs", type=int, default=7)
    ap.add_argument("--keep", action="store_true", help="do not drop the scratch schema")
    args = ap.parse_args()

    base = database_url()
    schema = f"bench_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(base, autocommit=True) as c:
        c.execute(f'CREATE SCHEMA "{schema}"')
    try:
        with psycopg.connect(base, cursor_factory=ClientCursor, autocommit=True,
                             options=f"-c search_path={schema}") as conn:
            cur = conn.cursor()
            cur.execute((MIGRATIONS / "001_core_tables.sql").read_text(encoding="utf-8"))
            t0 = time.time()
            counts = populate(cur, args.scale)
            cur.execute("ANALYZE")
            print(f"loaded synthetic data in {time.time() - t0:.0f}s: {counts}")
            params = params_for(cur)

            def run_all(label: str) -> list[dict]:
                out = []
                for name, sql in BENCHMARK_QUERIES.items():
                    res = measure(conn, name, sql, params[name], args.runs)
                    out.append(res)
                    print(f"[{label:6}] {name:24} {res['exec_ms_median']:9.3f} ms  seq_scan={res['uses_seq_scan']}")
                return out

            before = run_all("before")
            cur.execute((MIGRATIONS / "002_indexes.sql").read_text(encoding="utf-8"))
            cur.execute("ANALYZE")
            after = run_all("after")

            cur.execute("SELECT pg_size_pretty(sum(pg_total_relation_size(c.oid))) AS size FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relkind = 'r'",
                        (schema,))
            size = cur.fetchone()[0]
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
    finally:
        if not args.keep:
            with psycopg.connect(base, autocommit=True) as c:
                c.execute(f'DROP SCHEMA "{schema}" CASCADE')

    rows = []
    for b, a in zip(before, after):
        rows.append({
            "query": b["query"],
            "before_ms": b["exec_ms_median"], "after_ms": a["exec_ms_median"],
            "speedup_x": round(b["exec_ms_median"] / a["exec_ms_median"], 1) if a["exec_ms_median"] else None,
            "before_seq_scan": b["uses_seq_scan"], "after_seq_scan": a["uses_seq_scan"],
            "after_nodes": a["node_types"],
        })
    total_b = sum(r["before_ms"] for r in rows)
    total_a = sum(r["after_ms"] for r in rows)
    result = {
        "measured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "postgres": version, "scale": args.scale, "runs_per_query": args.runs,
        "synthetic_rows": counts, "data_size_with_indexes": size,
        "total_before_ms": round(total_b, 2), "total_after_ms": round(total_a, 2),
        "overall_reduction_pct": round((1 - total_a / total_b) * 100, 1) if total_b else None,
        "queries": rows,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "db_indexes.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    md = [f"# Index benchmark ({result['measured_at']})", "",
          f"- Database: {version}", f"- Synthetic rows (scale {args.scale}): {counts}",
          f"- Median of {args.runs} EXPLAIN ANALYZE runs per query, after one warm-up run",
          "- Data is synthetic; numbers apply to this database and machine only.", "",
          "| query | before (ms) | after (ms) | speed-up | seq scan before | seq scan after |",
          "|---|---:|---:|---:|:-:|:-:|"]
    for r in rows:
        md.append(f"| {r['query']} | {r['before_ms']} | {r['after_ms']} | {r['speedup_x']}x | "
                  f"{'yes' if r['before_seq_scan'] else 'no'} | {'yes' if r['after_seq_scan'] else 'no'} |")
    md += ["", f"Sum of all query times: {result['total_before_ms']} ms -> {result['total_after_ms']} ms "
               f"({result['overall_reduction_pct']}% lower)."]
    (OUT_DIR / "db_indexes.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
