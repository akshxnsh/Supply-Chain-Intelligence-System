from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

from src.tools.fivetran_mcp_client import FivetranMcpClient  # noqa: E402


def _connection_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        for key in ("items", "connections", "results"):
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _sync_state(row: dict[str, Any]) -> str | None:
    status = row.get("status")
    if isinstance(status, dict):
        value = status.get("sync_state")
        if value is not None:
            return str(value)
    value = row.get("sync_state")
    return str(value) if value is not None else None


def _export_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "connection_id": row.get("id") or row.get("connection_id"),
        "schema": row.get("schema"),
        "service": row.get("service"),
        "sync_state": _sync_state(row),
        "succeeded_at": row.get("succeeded_at"),
    }


def _print_table(rows: list[dict[str, Any]]) -> None:
    columns = ["connection_id", "schema", "service", "sync_state", "succeeded_at"]
    widths = {
        column: max(
            len(column),
            *(len(str(row.get(column) or "")) for row in rows),
        )
        for column in columns
    }
    print(" | ".join(column.ljust(widths[column]) for column in columns))
    print("-+-".join("-" * widths[column] for column in columns))
    for row in rows:
        print(" | ".join(str(row.get(column) or "").ljust(widths[column]) for column in columns))


async def main() -> int:
    load_dotenv(ROOT / ".env")
    async with FivetranMcpClient() as client:
        result = await client.list_connections()

    rows = [_export_row(row) for row in _connection_rows(result.get("result"))]
    print(json.dumps(rows, indent=2, default=str))
    print()
    _print_table(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
