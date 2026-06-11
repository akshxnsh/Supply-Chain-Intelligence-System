"""Configuration for BigQuery table freshness checks and connector mapping."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MAX_AGE_MINUTES = 60


@dataclass(frozen=True)
class FreshnessTableConfig:
    table_name: str
    connector_id: str
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES


FRESHNESS_TABLES: dict[str, FreshnessTableConfig] = {
    "alternative_suppliers": FreshnessTableConfig(
        table_name="alternative_suppliers",
        connector_id="deserving_emancipated",
        max_age_minutes=24 * 60,
    ),
    "business_suppliers": FreshnessTableConfig(
        table_name="business_suppliers",
        connector_id="incomparably_winning",
        max_age_minutes=24 * 60,
    ),
    "completed_orders": FreshnessTableConfig(
        table_name="completed_orders",
        connector_id="guess_jawless",
        max_age_minutes=24 * 60,
    ),
    "disruption_events": FreshnessTableConfig(
        table_name="disruption_events",
        connector_id="baritone_tadpole",
        max_age_minutes=1,
    ),
    "inventory": FreshnessTableConfig(
        table_name="inventory",
        connector_id="mayflower_chief",
        max_age_minutes=30,
    ),
    "pending_orders": FreshnessTableConfig(
        table_name="pending_orders",
        connector_id="disordered_forbidden",
        max_age_minutes=30,
    ),
    "port_activity": FreshnessTableConfig(
        table_name="port_activity",
        connector_id="utilizing_vehement",
        max_age_minutes=60,
    ),
    "shipment_timetable": FreshnessTableConfig(
        table_name="shipment_timetable",
        connector_id="capitalistic_cherub",
        max_age_minutes=30,
    ),
    "supplier_reviews": FreshnessTableConfig(
        table_name="supplier_reviews",
        connector_id="investigating_release",
        max_age_minutes=24 * 60,
    ),
    "tariff_updates": FreshnessTableConfig(
        table_name="tariff_updates",
        connector_id="proximate_nourish",
        max_age_minutes=24 * 60,
    ),
    "weather_alerts": FreshnessTableConfig(
        table_name="weather_alerts",
        connector_id="catlike_snowbird",
        max_age_minutes=60,
    ),
}


def get_table_config(table_name: str) -> FreshnessTableConfig:
    try:
        return FRESHNESS_TABLES[table_name]
    except KeyError as exc:
        expected = ", ".join(sorted(FRESHNESS_TABLES))
        raise ValueError(f"Unsupported freshness table {table_name!r}. Expected one of: {expected}") from exc


def configured_table_names() -> list[str]:
    return list(FRESHNESS_TABLES)
