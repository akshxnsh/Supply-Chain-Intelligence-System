"""raw.py readers against Fivetran-shaped tables (created here in throw-away schemas)."""

import os
from datetime import date, datetime, timedelta, timezone

import pytest

NOW = datetime.now(timezone.utc)

DDL = {
    "fivetran_raw_gdelt": """CREATE TABLE fivetran_raw_gdelt.articles (article_id text primary key, url text, title text, domain text,
        language text, source_country text, seen_at timestamptz, query_name text, _fivetran_deleted boolean, _fivetran_synced timestamptz)""",
    "fivetran_raw_gdacs": """CREATE TABLE fivetran_raw_gdacs.events (event_id text primary key, event_type text, name text, alert_level text,
        alert_score double precision, from_date timestamp, to_date timestamp, date_modified timestamp, is_current boolean, lat double precision,
        lon double precision, country text, affected_countries_iso_3 text, severity_value double precision, severity_unit text, severity_text text, report_url text,
        _fivetran_deleted boolean, _fivetran_synced timestamptz)""",
    "fivetran_raw_federal_register": """CREATE TABLE fivetran_raw_federal_register.documents (document_number text primary key, title text,
        doc_type text, publication_date date, effective_on date, comments_close_on date, dates_text text, abstract text, agencies text, url text,
        _fivetran_deleted boolean, _fivetran_synced timestamptz)""",
    "fivetran_raw_open_meteo": """CREATE TABLE fivetran_raw_open_meteo.daily_forecast (location_id text, forecast_date date,
        wind_gust_max_kmh double precision, wind_speed_max_kmh double precision, precipitation_sum_mm double precision, weather_code int,
        wave_height_max_m double precision, wave_period_max_s double precision, fetched_at timestamptz, _fivetran_deleted boolean,
        _fivetran_synced timestamptz, primary key (location_id, forecast_date))""",
    "fivetran_raw_ecb": """CREATE TABLE fivetran_raw_ecb.exchange_rates (currency text, rate_date date, eur_rate double precision,
        _fivetran_deleted boolean, _fivetran_synced timestamptz, primary key (currency, rate_date))""",
    "fivetran_raw_portwatch": """CREATE TABLE fivetran_raw_portwatch.ports (location_id text primary key, kind text, name text, country text,
        iso_3 text, locode text, lat double precision, lon double precision, _fivetran_deleted boolean, _fivetran_synced timestamptz);
        -- real Fivetran layout: the chokepoint table has no country / iso / locode columns (they carry no data)
        CREATE TABLE fivetran_raw_portwatch.chokepoints (location_id text primary key, kind text, name text,
        lat double precision, lon double precision, _fivetran_deleted boolean, _fivetran_synced timestamptz)""",
}


@pytest.fixture()
def raw(pg_url):
    import psycopg

    from src.ingestion import raw as raw_mod

    base = os.environ["TEST_DATABASE_URL"]
    with psycopg.connect(base, autocommit=True) as c:
        for schema, ddl in DDL.items():
            c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            c.execute(f'CREATE SCHEMA "{schema}"')
            c.execute(ddl)
        yield raw_mod, c
        for schema in DDL:
            c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


def test_recent_articles_window_and_soft_delete(raw):
    mod, c = raw
    ins = "INSERT INTO fivetran_raw_gdelt.articles VALUES (%s,'u','t','d','English','X',%s,'ports',%s,now())"
    c.execute(ins, ("new", NOW - timedelta(hours=2), False))
    c.execute(ins, ("old", NOW - timedelta(hours=50), False))
    c.execute(ins, ("gone", NOW - timedelta(hours=1), True))
    assert [r["article_id"] for r in mod.recent_articles(24)] == ["new"]


def test_disasters_current_or_recent(raw):
    mod, c = raw
    ins = ("INSERT INTO fivetran_raw_gdacs.events (event_id, event_type, date_modified, is_current, _fivetran_deleted) "
           "VALUES (%s,'TC',%s,%s,false)")
    c.execute(ins, ("TC-1", NOW - timedelta(days=30), True))    # old but still current
    c.execute(ins, ("TC-2", NOW - timedelta(days=1), False))    # recent
    c.execute(ins, ("TC-3", NOW - timedelta(days=30), False))   # old and over
    assert {r["event_id"] for r in mod.active_disasters(7)} == {"TC-1", "TC-2"}


def test_tariff_documents_recent_only(raw):
    mod, c = raw
    ins = ("INSERT INTO fivetran_raw_federal_register.documents (document_number, publication_date, _fivetran_deleted) "
           "VALUES (%s,%s,false)")
    c.execute(ins, ("d-new", date.today() - timedelta(days=3)))
    c.execute(ins, ("d-old", date.today() - timedelta(days=200)))
    assert [r["document_number"] for r in mod.recent_tariff_documents(60)] == ["d-new"]


def test_forecast_only_today_and_later(raw):
    mod, c = raw
    ins = "INSERT INTO fivetran_raw_open_meteo.daily_forecast (location_id, forecast_date, _fivetran_deleted) VALUES (%s,%s,false)"
    c.execute(ins, ("L1", date.today() - timedelta(days=1)))
    c.execute(ins, ("L1", date.today() + timedelta(days=2)))
    assert [r["forecast_date"] for r in mod.upcoming_forecast()] == [date.today() + timedelta(days=2)]


def test_latest_rates_one_row_per_currency_and_history(raw):
    mod, c = raw
    ins = "INSERT INTO fivetran_raw_ecb.exchange_rates VALUES (%s,%s,%s,false,now())"
    c.execute(ins, ("USD", date.today() - timedelta(days=2), 1.10))
    c.execute(ins, ("USD", date.today() - timedelta(days=1), 1.12))
    c.execute(ins, ("CNY", date.today() - timedelta(days=1), 8.0))
    latest = {r["currency"]: r["eur_rate"] for r in mod.latest_rates()}
    assert latest == {"USD": 1.12, "CNY": 8.0}
    assert [r["eur_rate"] for r in mod.rate_history("USD", 30)] == [1.10, 1.12]


def test_port_and_chokepoint_locations_union(raw):
    mod, c = raw
    c.execute("INSERT INTO fivetran_raw_portwatch.ports (location_id, name, lat, lon, _fivetran_deleted) "
              "VALUES ('p1','Baltimore',39.2,-76.5,false)")
    c.execute("INSERT INTO fivetran_raw_portwatch.chokepoints (location_id, name, lat, lon, _fivetran_deleted) "
              "VALUES ('c1','Suez Canal',30.5,32.4,false)")
    kinds = {r["location_id"]: r["kind"] for r in mod.port_and_chokepoint_locations()}
    assert kinds == {"p1": "port", "c1": "chokepoint"}


def test_freshness_config_points_at_existing_schemas():
    from src.agent.freshness_config import FRESHNESS_TABLES
    from src.ingestion import raw as raw_mod

    for cfg in FRESHNESS_TABLES.values():
        assert cfg.schema in raw_mod.SCHEMAS.values() and cfg.connector_id and cfg.max_age_minutes > 0
