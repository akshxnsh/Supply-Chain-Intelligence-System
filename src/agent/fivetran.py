import json
import os
import shlex
from typing import Any


FIVETRAN_TOOLS = [
    "check_connector_status",
    "get_last_sync_time",
    "list_connectors",
    "trigger_sync",
    "monitor_sync",
]


def _headers() -> dict[str, str]:
    raw_headers = os.getenv("FIVETRAN_MCP_HEADERS_JSON", "")
    if raw_headers:
        return {str(k): str(v) for k, v in json.loads(raw_headers).items()}
    token = os.getenv("FIVETRAN_MCP_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def create_fivetran_toolset() -> Any | None:
    """Create an ADK MCP toolset when Fivetran MCP is configured."""
    url = os.getenv("FIVETRAN_MCP_URL")
    command = os.getenv("FIVETRAN_MCP_COMMAND")
    if not url and not command:
        return None

    try:
        from google.adk.tools.mcp_tool.mcp_session_manager import (
            StdioConnectionParams,
            StreamableHTTPConnectionParams,
        )
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
        from mcp import StdioServerParameters
    except ImportError as exc:
        raise RuntimeError(
            "Fivetran MCP is configured but MCP dependencies are unavailable."
        ) from exc

    if url:
        connection = StreamableHTTPConnectionParams(
            url=url,
            headers=_headers() or None,
            timeout=float(os.getenv("FIVETRAN_MCP_TIMEOUT_SECONDS", "30")),
        )
    else:
        parts = shlex.split(command or "")
        if not parts:
            raise ValueError("FIVETRAN_MCP_COMMAND must include an executable.")
        connection = StdioConnectionParams(
            server_params=StdioServerParameters(
                command=parts[0],
                args=parts[1:],
                env=dict(os.environ),
            ),
            timeout=float(os.getenv("FIVETRAN_MCP_TIMEOUT_SECONDS", "30")),
        )

    return McpToolset(
        connection_params=connection,
        tool_filter=FIVETRAN_TOOLS,
    )
