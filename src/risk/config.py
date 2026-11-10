"""Risk configuration: loads config/risk.yaml (all thresholds live there, none in code)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "risk.yaml"


@lru_cache(maxsize=1)
def _load(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """The parsed risk config (cached per path). Tests pass their own dict instead of calling this."""
    return _load(str(path or CONFIG_PATH))


def reload_config() -> None:
    _load.cache_clear()
