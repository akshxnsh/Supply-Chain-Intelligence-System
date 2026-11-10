"""Build the Open-Meteo connector's `locations` setting from the route checkpoints of our shipments.

Every checkpoint name in shipment_timetable.route ("Port of Hamburg > English Channel > ...") is matched to
the PortWatch port/chokepoint catalogue (which has coordinates). Unmatched names (e.g. "Atlantic Crossing")
are listed and skipped - they are not places we can forecast.

    python -m scripts.build_open_meteo_locations
Writes connectors/open_meteo/configuration.json (no secrets in it).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.fetchers import portwatch
from src.ingestion.db import run_query

OUT = Path(__file__).resolve().parents[1] / "connectors" / "open_meteo" / "configuration.json"


def checkpoint_names(routes: list[str]) -> list[str]:
    names = []
    for route in routes:
        for part in route.split(">"):
            part = re.sub(r"^\s*Port of\s+", "", part.strip(), flags=re.I)
            if part and part not in names:
                names.append(part)
    return names


def match(name: str, catalogue: list[dict]) -> dict | None:
    """Exact (case-insensitive) name first, then a unique 'contains' match."""
    n = name.lower()
    exact = [c for c in catalogue if (c["name"] or "").lower() == n]
    if exact:
        return max(exact, key=lambda c: c.get("vessel_count_total") or 0)
    part = [c for c in catalogue if n in (c["name"] or "").lower()]
    return max(part, key=lambda c: c.get("vessel_count_total") or 0) if part else None


def main() -> None:
    routes = [r["route"] for r in run_query("SELECT DISTINCT route FROM shipment_timetable")]
    names = checkpoint_names(routes)
    ports, chokes = portwatch.fetch_ports(), portwatch.fetch_chokepoints()
    locations, skipped = [], []
    for name in names:
        hit = match(name, chokes) or match(name, ports)
        if hit and hit["lat"] is not None:
            locations.append({"id": hit["location_id"], "name": hit["name"], "lat": round(hit["lat"], 3), "lon": round(hit["lon"], 3)})
        else:
            skipped.append(name)
    uniq = {l["id"]: l for l in locations}
    cfg = {"days": "7", "locations": json.dumps(list(uniq.values()))}
    OUT.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print(f"{len(uniq)} locations written to {OUT.name}; skipped (no catalogue match): {skipped}")
    for l in uniq.values():
        print(" ", l["id"], l["name"])


if __name__ == "__main__":
    main()
