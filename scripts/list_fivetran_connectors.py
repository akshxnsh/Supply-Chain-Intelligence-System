from __future__ import annotations

import asyncio
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.tools.fivetran_mcp_client import FivetranMcpClient  # noqa: E402


LIST_CONNECTOR_TOOL_CANDIDATES = (
    "list_connectors",
    "get_connectors",
    "connectors",
)


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if hasattr(value, "dict"):
        return value.dict()
    return {"value": value}


def _parse_text(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _extract_result(call_result: Any) -> Any:
    raw = _dump(call_result)
    structured = raw.get("structuredContent") or raw.get("structured_content")
    if structured is not None:
        return structured

    content = raw.get("content") or []
    parsed = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parsed.append(_parse_text(str(item.get("text", ""))))
        else:
            parsed.append(item)

    if len(parsed) == 1:
        return parsed[0]
    return parsed


def _find_connector_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("connectors", "items", "data", "results"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                rows = _find_connector_rows(value)
                if rows:
                    return rows

    return []


def _value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return str(value)
    return ""


def _status(row: dict[str, Any]) -> str:
    for key in ("status", "sync_state", "state", "setup_state"):
        value = row.get(key)
        if value:
            return str(value)

    data = row.get("data")
    if isinstance(data, dict):
        return _status(data)

    return ""


async def main() -> int:
    async with FivetranMcpClient() as client:
        tool_name = client._select_tool(LIST_CONNECTOR_TOOL_CANDIDATES)
        result = await client.session.call_tool(
            tool_name,
            arguments={},
            read_timeout_seconds=timedelta(seconds=client.timeout_seconds),
        )

    rows = _find_connector_rows(_extract_result(result))
    print("connector_id\tconnector_name\tstatus")
    for row in rows:
        print(
            "\t".join(
                [
                    _value(row, "connector_id", "id"),
                    _value(row, "connector_name", "name"),
                    _status(row),
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
