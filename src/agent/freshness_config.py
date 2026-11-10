"""Configuration for data freshness checks: which Fivetran-loaded table belongs to which connection.

Freshness = newest `_fivetran_synced` in the table (Fivetran stamps every row it writes). One representative
table per connection, chosen because every sync re-writes at least one of its rows (GDELT: new articles,
GDACS/Federal Register/ECB: the overlap window is re-upserted, Open-Meteo: forecast replaced each run).
PortWatch's disruptions layer is stale at the source, so its catalogue table (refreshed monthly) is used.
Company sample data (suppliers, orders, inventory) has no connector and is not tracked here.
"""

from __future__ import annotations

from dataclasses import dataclass

FIVETRAN_SYNCED_COLUMN = "_fivetran_synced"


@dataclass(frozen=True)
class FreshnessTableConfig:
    table_name: str        # logical name used by the API / UI / agent tools
    schema: str            # Postgres schema Fivetran writes to (one per connection)
    table: str
    connector_id: str      # Fivetran connection id
    max_age_minutes: int   # older than this = stale
    column: str = FIVETRAN_SYNCED_COLUMN


# max_age = about 3x the sync interval (see FREQUENCY_MINUTES in scripts/fivetran_api.py)
FRESHNESS_TABLES: dict[str, FreshnessTableConfig] = {
    "gdelt_articles": FreshnessTableConfig("gdelt_articles", "fivetran_raw_gdelt", "articles", "diplomat_umpire", 90),
    "gdacs_events": FreshnessTableConfig("gdacs_events", "fivetran_raw_gdacs", "events", "visiting_reminiscent", 9 * 60),
    "portwatch_ports": FreshnessTableConfig("portwatch_ports", "fivetran_raw_portwatch", "ports", "tonsils_assistance", 35 * 24 * 60),
    "federal_register_documents": FreshnessTableConfig(
        "federal_register_documents", "fivetran_raw_federal_register", "documents", "derivation_popular", 18 * 60),
    "open_meteo_forecast": FreshnessTableConfig(
        "open_meteo_forecast", "fivetran_raw_open_meteo", "daily_forecast", "reflector_chose", 18 * 60),
    "ecb_exchange_rates": FreshnessTableConfig(
        "ecb_exchange_rates", "fivetran_raw_ecb", "exchange_rates", "flourishing_unsnap", 3 * 24 * 60),
}


def get_table_config(table_name: str) -> FreshnessTableConfig:
    try:
        return FRESHNESS_TABLES[table_name]
    except KeyError as exc:
        expected = ", ".join(sorted(FRESHNESS_TABLES))
        raise ValueError(f"Unsupported freshness table {table_name!r}. Expected one of: {expected}") from exc


def configured_table_names() -> list[str]:
    return list(FRESHNESS_TABLES)
