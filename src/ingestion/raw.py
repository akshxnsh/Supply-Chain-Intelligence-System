"""Read-only access to the tables Fivetran loads (one schema per connection, `fivetran_raw_<source>`).

We never create or migrate these tables: Fivetran owns them. Our own tables (events, alerts, ...) are built
from them in later steps. Every table has `_fivetran_deleted` (soft delete flag) and `_fivetran_synced`.
"""

from __future__ import annotations

from src.ingestion.db import run_query

SCHEMAS = {
    "gdelt": "fivetran_raw_gdelt",
    "gdacs": "fivetran_raw_gdacs",
    "portwatch": "fivetran_raw_portwatch",
    "federal_register": "fivetran_raw_federal_register",
    "open_meteo": "fivetran_raw_open_meteo",
    "ecb": "fivetran_raw_ecb",
}

SQL_ARTICLES = """
    SELECT article_id, url, title, domain, language, source_country, seen_at, query_name
    FROM fivetran_raw_gdelt.articles
    WHERE NOT _fivetran_deleted AND seen_at >= now() - make_interval(hours => %(hours)s)
    ORDER BY seen_at DESC
"""

SQL_DISASTERS = """
    SELECT event_id, event_type, name, alert_level, alert_score, from_date, to_date, date_modified,
           is_current, lat, lon, country, affected_countries_iso3, severity_value, severity_unit, severity_text
    FROM fivetran_raw_gdacs.events
    WHERE NOT _fivetran_deleted AND (is_current OR date_modified >= now() - make_interval(days => %(days)s))
    ORDER BY date_modified DESC
"""

SQL_TARIFF_DOCUMENTS = """
    SELECT document_number, title, doc_type, publication_date, effective_on, comments_close_on,
           dates_text, abstract, agencies, url
    FROM fivetran_raw_federal_register.documents
    WHERE NOT _fivetran_deleted AND publication_date >= current_date - %(days)s::int
    ORDER BY publication_date DESC
"""

SQL_FORECAST = """
    SELECT location_id, forecast_date, wind_gust_max_kmh, wind_speed_max_kmh, precipitation_sum_mm,
           weather_code, wave_height_max_m, wave_period_max_s, fetched_at
    FROM fivetran_raw_open_meteo.daily_forecast
    WHERE NOT _fivetran_deleted AND forecast_date >= current_date
    ORDER BY location_id, forecast_date
"""

SQL_LATEST_RATES = """
    SELECT DISTINCT ON (currency) currency, rate_date, eur_rate
    FROM fivetran_raw_ecb.exchange_rates
    WHERE NOT _fivetran_deleted
    ORDER BY currency, rate_date DESC
"""

SQL_RATE_HISTORY = """
    SELECT currency, rate_date, eur_rate
    FROM fivetran_raw_ecb.exchange_rates
    WHERE NOT _fivetran_deleted AND currency = %(currency)s AND rate_date >= current_date - %(days)s::int
    ORDER BY rate_date
"""

SQL_LOCATIONS = """
    SELECT location_id, 'port' AS kind, name, country, iso3, locode, lat, lon FROM fivetran_raw_portwatch.ports
    WHERE NOT _fivetran_deleted
    UNION ALL
    SELECT location_id, 'chokepoint', name, country, iso3, locode, lat, lon FROM fivetran_raw_portwatch.chokepoints
    WHERE NOT _fivetran_deleted
"""


def recent_articles(hours: int = 24) -> list[dict]:
    return run_query(SQL_ARTICLES, {"hours": hours})


def active_disasters(days: int = 7) -> list[dict]:
    return run_query(SQL_DISASTERS, {"days": days})


def recent_tariff_documents(days: int = 60) -> list[dict]:
    return run_query(SQL_TARIFF_DOCUMENTS, {"days": days})


def upcoming_forecast() -> list[dict]:
    return run_query(SQL_FORECAST)


def latest_rates() -> list[dict]:
    return run_query(SQL_LATEST_RATES)


def rate_history(currency: str, days: int = 90) -> list[dict]:
    return run_query(SQL_RATE_HISTORY, {"currency": currency, "days": days})


def port_and_chokepoint_locations() -> list[dict]:
    return run_query(SQL_LOCATIONS)
