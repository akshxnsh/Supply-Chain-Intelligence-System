import contextvars
import json
import os
from collections.abc import Callable
from typing import Any

from opentelemetry import trace


_log_callback: contextvars.ContextVar[Callable[[str], None] | None] = (
    contextvars.ContextVar("agent_log_callback", default=None)
)
_configured = False
_tracer_provider = None


def configure_phoenix():
    """Configure Phoenix once and auto-instrument ADK/OpenInference."""
    global _configured, _tracer_provider
    if _configured:
        return _tracer_provider
    _configured = True

    api_key = os.getenv("PHOENIX_API_KEY")
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT") or os.getenv(
        "PHOENIX_ENDPOINT",
        "https://app.phoenix.arize.com/s/singhamiya9/v1/traces",
    )
    if not api_key:
        return None

    try:
        from phoenix.otel import register
    except Exception as exc:
        emit_log(f"Phoenix tracing disabled: {exc}")
        return None

    try:
        _tracer_provider = register(
            project_name=os.getenv("PHOENIX_PROJECT_NAME", "supply-chain-agent"),
            endpoint=endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            auto_instrument=True,
        )
    except Exception as exc:
        emit_log(f"Phoenix tracing disabled: {exc}")
        _tracer_provider = None
    return _tracer_provider


def get_tracer():
    configure_phoenix()
    return trace.get_tracer("supply-chain-agent.adk")


def set_log_callback(callback: Callable[[str], None] | None):
    return _log_callback.set(callback)


def reset_log_callback(token) -> None:
    _log_callback.reset(token)


def emit_log(message: str) -> None:
    print(message)
    callback = _log_callback.get()
    if callback:
        callback(message)


def before_agent(callback_context) -> None:
    emit_log(f"Agent started: {callback_context.agent_name}")


def after_agent(callback_context) -> None:
    emit_log(f"Agent completed: {callback_context.agent_name}")


def before_tool(tool, args: dict[str, Any], tool_context) -> None:
    emit_log(f"Tool call: {tool.name}({json.dumps(args, default=str)})")
    tool_context.state["last_tool_name"] = tool.name


def after_tool(tool, args: dict[str, Any], tool_context, tool_response: dict) -> None:
    size = len(json.dumps(tool_response, default=str))
    emit_log(f"Tool completed: {tool.name} ({size} chars)")


def on_tool_error(tool, args: dict[str, Any], tool_context, error: Exception) -> None:
    emit_log(f"Tool failed: {tool.name}: {error}")
