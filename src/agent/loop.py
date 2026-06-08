"""Backward-compatible imports for callers of the former custom loop."""

from src.agent.runtime import (
    _persist_alert_if_new,
    run_agent_cycle,
    run_agent_cycle_async,
    run_loop,
)


__all__ = [
    "run_agent_cycle",
    "run_agent_cycle_async",
    "run_loop",
    "_persist_alert_if_new",
]
