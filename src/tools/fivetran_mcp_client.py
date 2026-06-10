"""Async client for the local Fivetran stdio MCP server."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


logger = logging.getLogger(__name__)

TRIGGER_SYNC_TOOL_CANDIDATES = (
    "sync_connection",
)
STATUS_TOOL_CANDIDATES = (
    "get_connection_details",
)
LIST_CONNECTIONS_TOOL_CANDIDATES = (
    "list_connections",
)

LIST_CONNECTIONS_SCHEMA_FILE = "open-api-definitions/connections/list_connections.json"
CONNECTION_DETAILS_SCHEMA_FILE = "open-api-definitions/connections/connection_details.json"
SYNC_CONNECTION_SCHEMA_FILE = "open-api-definitions/connections/sync_connection.json"


def _timeout_seconds() -> float:
    return float(os.getenv("FIVETRAN_MCP_TIMEOUT_SECONDS", "30"))


def _retry_count() -> int:
    return int(os.getenv("FIVETRAN_MCP_RETRIES", "3"))


def _retry_delay_seconds() -> float:
    return float(os.getenv("FIVETRAN_MCP_RETRY_DELAY_SECONDS", "1"))


def _server_parameters() -> StdioServerParameters:
    command = os.getenv("FIVETRAN_MCP_COMMAND")
    if not command:
        raise RuntimeError(
            "FIVETRAN_MCP_COMMAND is required to launch the local Fivetran MCP server."
        )

    parts = shlex.split(command)
    if not parts:
        raise ValueError("FIVETRAN_MCP_COMMAND must include an executable.")

    env = dict(os.environ)
    credential_names = [
        name
        for name in (
            "FIVETRAN_API_KEY",
            "FIVETRAN_API_SECRET",
            "FIVETRAN_MCP_TOKEN",
            "FIVETRAN_MCP_HEADERS_JSON",
        )
        if env.get(name)
    ]
    logger.info(
        "Launching Fivetran MCP server with command %s and credential env vars: %s.",
        parts[0],
        ", ".join(credential_names) or "none detected",
    )

    return StdioServerParameters(
        command=parts[0],
        args=parts[1:],
        env=env,
    )


def _json_or_text(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _model_dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if hasattr(value, "dict"):
        return value.dict()
    return {"value": value}


def _normalize_tool_result(
    tool_name: str,
    connector_id: str,
    result: Any,
) -> dict[str, Any]:
    raw = _model_dump(result)
    content = raw.get("content") or []
    parsed_content = []

    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            parsed_content.append(_json_or_text(str(item.get("text", ""))))
        else:
            parsed_content.append(item)

    structured = (
        raw.get("structuredContent")
        or raw.get("structured_content")
        or (parsed_content[0] if len(parsed_content) == 1 else parsed_content)
    )

    return {
        "connector_id": connector_id,
        "tool_name": tool_name,
        "is_error": bool(raw.get("isError") or raw.get("is_error")),
        "result": structured,
        "raw": raw,
    }


class FivetranMcpClient:
    """Manage a stdio MCP subprocess and session for Fivetran connector tools."""

    def __init__(
        self,
        *,
        timeout_seconds: float | None = None,
        retries: int | None = None,
        retry_delay_seconds: float | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds or _timeout_seconds()
        self.retries = retries or _retry_count()
        self.retry_delay_seconds = retry_delay_seconds or _retry_delay_seconds()
        self._exit_stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None
        self._tools: dict[str, dict[str, Any]] = {}

    async def __aenter__(self) -> "FivetranMcpClient":
        self._exit_stack = AsyncExitStack()
        read_stream, write_stream = await self._exit_stack.enter_async_context(
            stdio_client(_server_parameters())
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await asyncio.wait_for(self._session.initialize(), timeout=self.timeout_seconds)
        await self.discover_tools()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._exit_stack:
            await self._exit_stack.aclose()
        self._exit_stack = None
        self._session = None
        self._tools = {}

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("Fivetran MCP session is not open.")
        return self._session

    async def discover_tools(self) -> list[dict[str, Any]]:
        logger.info("Discovering Fivetran MCP tools.")
        result = await asyncio.wait_for(
            self.session.list_tools(),
            timeout=self.timeout_seconds,
        )
        tools = []
        for tool in result.tools:
            tool_data = _model_dump(tool)
            tools.append(tool_data)
            self._tools[str(tool_data.get("name"))] = tool_data
        logger.info("Discovered %s Fivetran MCP tools.", len(tools))
        return tools

    def _select_tool(self, candidates: tuple[str, ...]) -> str:
        for candidate in candidates:
            if candidate in self._tools:
                return candidate

        available = ", ".join(sorted(self._tools)) or "none"
        expected = ", ".join(candidates)
        raise RuntimeError(
            f"Fivetran MCP tool not found. Expected one of: {expected}. Available: {available}."
        )

    async def _call_tool(
        self,
        tool_name: str,
        connector_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                logger.info(
                    "Calling Fivetran MCP tool %s for connector %s (attempt %s/%s).",
                    tool_name,
                    connector_id,
                    attempt,
                    self.retries,
                )
                result = await self.session.call_tool(
                    tool_name,
                    arguments=arguments,
                    read_timeout_seconds=timedelta(seconds=self.timeout_seconds),
                )
                normalized = _normalize_tool_result(tool_name, connector_id, result)
                if normalized["is_error"]:
                    raise RuntimeError(
                        f"Fivetran MCP tool {tool_name} returned an error: {normalized['result']}"
                    )
                return normalized
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Fivetran MCP tool %s failed for connector %s on attempt %s/%s: %s",
                    tool_name,
                    connector_id,
                    attempt,
                    self.retries,
                    exc,
                )
                if attempt < self.retries:
                    await asyncio.sleep(self.retry_delay_seconds)

        raise RuntimeError(
            f"Fivetran MCP tool {tool_name} failed after {self.retries} attempts."
        ) from last_error

    async def trigger_connector_sync(self, connector_id: str) -> dict[str, Any]:
        tool_name = self._select_tool(TRIGGER_SYNC_TOOL_CANDIDATES)
        return await self._call_tool(
            tool_name,
            connector_id,
            {
                "schema_file": SYNC_CONNECTION_SCHEMA_FILE,
                "connection_id": connector_id,
                "request_body": json.dumps({"force": False}),
            },
        )

    async def get_connector_status(self, connector_id: str) -> dict[str, Any]:
        tool_name = self._select_tool(STATUS_TOOL_CANDIDATES)
        return await self._call_tool(
            tool_name,
            connector_id,
            {
                "schema_file": CONNECTION_DETAILS_SCHEMA_FILE,
                "connection_id": connector_id,
            },
        )

    async def list_connections(self) -> dict[str, Any]:
        tool_name = self._select_tool(LIST_CONNECTIONS_TOOL_CANDIDATES)
        return await self._call_tool(
            tool_name,
            "all",
            {"schema_file": LIST_CONNECTIONS_SCHEMA_FILE},
        )


async def discover_available_tools() -> list[dict[str, Any]]:
    async with FivetranMcpClient() as client:
        return list(client._tools.values())


async def trigger_connector_sync(connector_id: str) -> dict[str, Any]:
    async with FivetranMcpClient() as client:
        return await client.trigger_connector_sync(connector_id)


async def get_connector_status(connector_id: str) -> dict[str, Any]:
    async with FivetranMcpClient() as client:
        return await client.get_connector_status(connector_id)


async def list_connections() -> dict[str, Any]:
    async with FivetranMcpClient() as client:
        return await client.list_connections()
