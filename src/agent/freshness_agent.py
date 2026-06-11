"""ADK freshness tools for BigQuery-backed supply-chain tables."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from src.agent.freshness_config import configured_table_names, get_table_config
from src.ingestion.bq_client import DATASET, PROJECT_ID, client
from src.ingestion.sync_postgres_to_bigquery import sync_table
from src.tools.fivetran_mcp_client import (
    get_connector_status as get_fivetran_connector_status,
)
from src.tools.fivetran_mcp_client import trigger_connector_sync


__all__ = [
    "check_bigquery_table_freshness",
    "identify_stale_tables",
    "refresh_connector",
    "get_connector_status",
    "wait_for_connector_completion",
    "sync_postgres_table_to_bigquery",
    "refresh_stale_table",
    "refresh_all_stale_tables",
]

TERMINAL_CONNECTOR_STATUSES = {
    "connected",
    "completed",
    "idle",
    "ready",
    "scheduled",
    "success",
    "succeeded",
}
FAILED_CONNECTOR_STATUSES = {"broken", "cancelled", "error", "failed"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_tables(table_names: list[str] | None = None) -> list[str]:
    if not table_names:
        return configured_table_names()
    for table_name in table_names:
        get_table_config(table_name)
    return table_names


def _table_freshness(table_name: str) -> dict[str, Any]:
    config = get_table_config(table_name)
    table = client.get_table(f"{PROJECT_ID}.{DATASET}.{table_name}")
    modified_at = table.modified
    if modified_at.tzinfo is None:
        modified_at = modified_at.replace(tzinfo=timezone.utc)

    age_minutes = (_utc_now() - modified_at).total_seconds() / 60
    return {
        "table_name": table_name,
        "connector_id": config.connector_id,
        "last_modified": modified_at.isoformat(),
        "age_minutes": round(age_minutes, 2),
        "max_age_minutes": config.max_age_minutes,
        "is_stale": age_minutes > config.max_age_minutes,
    }


async def check_bigquery_table_freshness(table_names: list[str] | None = None) -> str:
    """Return freshness metadata for configured BigQuery tables."""
    rows = await asyncio.gather(
        *[
            asyncio.to_thread(_table_freshness, table_name)
            for table_name in _normalize_tables(table_names)
        ]
    )
    return json.dumps(rows, default=str)


async def identify_stale_tables(table_names: list[str] | None = None) -> str:
    """Identify configured BigQuery tables whose metadata is older than policy."""
    freshness = json.loads(await check_bigquery_table_freshness(table_names))
    stale_tables = [row for row in freshness if row["is_stale"]]
    return json.dumps({"stale_tables": stale_tables, "stale_count": len(stale_tables)}, default=str)


async def refresh_connector(table_name: str) -> str:
    """Trigger a Fivetran connector sync for the table's configured connector."""
    config = get_table_config(table_name)
    result = await trigger_connector_sync(config.connector_id)
    return json.dumps(
        {
            "table_name": table_name,
            "connector_id": config.connector_id,
            "refresh_requested": True,
            "mcp": result,
        },
        default=str,
    )


async def get_connector_status(table_name: str) -> str:
    """Fetch Fivetran connector status for the table's configured connector."""
    config = get_table_config(table_name)
    result = await get_fivetran_connector_status(config.connector_id)
    return json.dumps(
        {
            "table_name": table_name,
            "connector_id": config.connector_id,
            "status": _extract_connector_status(result),
            "mcp": result,
        },
        default=str,
    )


def _extract_connector_status(result: dict[str, Any]) -> str:
    try:
        return result["result"]["data"]["status"]["sync_state"]
    except (KeyError, TypeError):
        return "unknown"


async def wait_for_connector_completion(
    table_name: str,
    poll_interval_seconds: float = 5,
    timeout_seconds: float = 300,
) -> str:
    """Poll Fivetran MCP status until connector refresh completes."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    attempts = 0

    while True:
        attempts += 1
        status_payload = json.loads(await get_connector_status(table_name))
        status = str(status_payload.get("status", "")).lower()
        if status in TERMINAL_CONNECTOR_STATUSES:
            status_payload["attempts"] = attempts
            return json.dumps(status_payload)
        if status in FAILED_CONNECTOR_STATUSES:
            raise RuntimeError(f"Connector refresh failed for {table_name}: {status}")
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Connector refresh timed out for {table_name}")
        await asyncio.sleep(poll_interval_seconds)


async def sync_postgres_table_to_bigquery(table_name: str) -> str:
    """Run sync_postgres_to_bigquery.py logic for a single configured table."""
    get_table_config(table_name)
    synced = await asyncio.to_thread(sync_table, table_name)
    return json.dumps({"table_name": table_name, "synced": synced})


async def refresh_stale_table(table_name: str) -> str:
    """Refresh one stale table, sync PostgreSQL to BigQuery, then verify freshness."""
    before = _table_freshness(table_name)
    if not before["is_stale"]:
        return json.dumps(
            {
                "table_name": table_name,
                "skipped": True,
                "reason": "table is already fresh",
                "freshness": before,
            },
            default=str,
        )

    connector_refresh = json.loads(await refresh_connector(table_name))
    connector_status = json.loads(await wait_for_connector_completion(table_name))
    sync_result = json.loads(await sync_postgres_table_to_bigquery(table_name))
    after = await asyncio.to_thread(_table_freshness, table_name)

    return json.dumps(
        {
            "table_name": table_name,
            "connector_refresh": connector_refresh,
            "connector_status": connector_status,
            "sync_result": sync_result,
            "freshness_before": before,
            "freshness_after": after,
            "verified_fresh": not after["is_stale"],
        },
        default=str,
    )


async def refresh_all_stale_tables(table_names: list[str] | None = None) -> str:
    """Refresh every configured stale table and report per-table outcomes."""
    stale_payload = json.loads(await identify_stale_tables(table_names))
    results = []
    for row in stale_payload["stale_tables"]:
        results.append(json.loads(await refresh_stale_table(row["table_name"])))
    return json.dumps(
        {
            "stale_count": stale_payload["stale_count"],
            "refreshed_count": len(results),
            "results": results,
        },
        default=str,
    )
