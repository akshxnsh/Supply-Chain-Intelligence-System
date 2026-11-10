"""Places: name matching and distances, built on the PortWatch port / chokepoint catalogue (with coordinates)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi, dlmb = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def norm_place(name: str) -> str:
    """'Port of Houston (US-TX)' -> 'houston'; 'Los Angeles-Long Beach' -> 'los angeles long beach'."""
    n = re.sub(r"\(.*?\)", " ", name or "").lower()
    n = re.sub(r"^\s*(port|harbou?r) of\s+", "", n.strip())
    n = re.sub(r"\b(port|harbou?r|terminal|terminals|canal|strait)\b", " ", n) if len(n.split()) > 1 else n
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


@dataclass(frozen=True)
class Place:
    location_id: str
    kind: str                      # port | chokepoint
    name: str
    country: str | None
    lat: float | None
    lon: float | None


class PortIndex:
    """Looks places up by (fuzzy) name. Built from PortWatch rows (location_id, kind, name, country, lat, lon)."""

    def __init__(self, rows: list[dict]):
        self.places = [Place(r["location_id"], r["kind"], r["name"], r.get("country"), r.get("lat"), r.get("lon"))
                       for r in rows if r.get("name")]
        self._by_norm: dict[str, list[Place]] = {}
        for p in self.places:
            self._by_norm.setdefault(norm_place(p.name), []).append(p)
        self._by_id = {p.location_id: p for p in self.places}

    def by_id(self, location_id: str) -> Place | None:
        return self._by_id.get(location_id)

    def find(self, name: str) -> Place | None:
        """Exact normalised name first, then a unique 'one name contains the other' match (chokepoints win ties)."""
        n = norm_place(name)
        if not n:
            return None
        if n in self._by_norm:
            return self._pick(self._by_norm[n])
        hits = [p for key, ps in self._by_norm.items() if key and (n in key.split() or key in n.split() or n in key)
                for p in ps if len(key) >= 4]
        return self._pick(hits) if hits else None

    @staticmethod
    def _pick(places: list[Place]) -> Place:
        return sorted(places, key=lambda p: (p.kind != "chokepoint", p.name))[0]

    def country_of(self, name: str) -> str | None:
        p = self.find(name)
        return p.country if p else None

    def kind_of(self, name: str) -> str | None:
        p = self.find(name)
        return p.kind if p else None
