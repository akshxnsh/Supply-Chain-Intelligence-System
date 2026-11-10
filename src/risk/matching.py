"""Match risk signals to shipments.

Delay signals reuse the route-checkpoint logic of src/prediction/utils.py: estimate WHERE each shipment will be at time T
(`checkpoint_windows`) and check whether a forecast / expected event covers that place at that time.
Tariff signals match on origin country + product + the effective date vs the shipment's arrival.
Exchange-rate signals match on the supplier's country.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.prediction.utils import checkpoint_windows
from src.risk.geo import PortIndex, haversine_km, norm_place
from src.risk.signals import DELAY, FX, TARIFF, Signal


@dataclass
class Match:
    signal: Signal
    shipment: dict[str, Any]
    precision: str                       # port | chokepoint | country | region
    checkpoint: str | None = None        # the route checkpoint that matched (None for country-level matches)
    window: tuple[date, date] | None = None   # when the ship is expected at that checkpoint
    why: str = ""


def place_matches(a: str, b: str) -> bool:
    na, nb = norm_place(a), norm_place(b)
    return bool(na and nb and (na == nb or (len(na) >= 4 and len(nb) >= 4 and (na in nb or nb in na))))


def same_country(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    a, b = a.strip().lower(), b.strip().lower()
    aliases = {"usa": "united states", "us": "united states", "u.s.": "united states", "uk": "united kingdom",
               "south korea": "south korea", "republic of korea": "south korea", "korea": "south korea"}
    return aliases.get(a, a) == aliases.get(b, b)


def product_matches(products: list[str], category: str, cfg: dict) -> bool:
    words = {w.lower() for w in cfg["product_keywords"].get(category, [])} | {w for w in category.lower().replace("_", " ").split()}
    text = " ".join(p.lower() for p in products)
    return any(w in text for w in words)


def _date(dt: datetime) -> date:
    return dt.astimezone(timezone.utc).date() if dt.tzinfo else dt.date()


def _overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    return a_start <= b_end and b_start <= a_end


def _shipment_countries(shipment: dict, ports: PortIndex) -> set[str]:
    out = {shipment.get("country")} if shipment.get("country") else set()
    for key in ("origin_port", "destination_port"):
        c = ports.country_of(shipment.get(key) or "")
        if c:
            out.add(c)
    return out


def match_delay(sig: Signal, shipment: dict, ports: PortIndex, cfg: dict, today: date) -> Match | None:
    slack = timedelta(days=cfg["checkpoint_slack_days"])
    s_start, s_end = sig.window(today, cfg)
    windows = checkpoint_windows(shipment)
    if not windows:
        return None
    now = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)

    # 1) the signal names a place that is on the route, and the ship will be there at that time
    for w in windows:
        if _date(w["end"]) < today - timedelta(days=1):
            continue  # already passed
        place = ports.find(w["checkpoint"])
        by_name = any(place_matches(w["checkpoint"], loc) for loc in sig.locations)
        by_distance = False
        if not by_name and sig.lat is not None and place and place.lat is not None:
            by_distance = haversine_km(sig.lat, sig.lon, place.lat, place.lon) <= (sig.radius_km or 0)
        if not (by_name or by_distance):
            continue
        ship_start, ship_end = _date(w["start"] - slack), _date(w["end"] + slack)
        if _overlap(ship_start, ship_end, s_start, s_end):
            kind = (place.kind if place else None) or "port"
            precision = ("chokepoint" if kind == "chokepoint" else "port") if by_name else (
                "port" if (sig.radius_km or 0) <= 50 else "region")
            how = "named on the route" if by_name else f"within {sig.radius_km:.0f} km of it"
            return Match(sig, shipment, precision, w["checkpoint"], (_date(w["start"]), _date(w["end"])),
                         f"{w['checkpoint']} ({how}), ship there {_date(w['start'])}..{_date(w['end'])}")

    # 2) only a country is known: the supplier's / route's countries vs the signal's countries, any time on the journey
    if sig.countries:
        mine = _shipment_countries(shipment, ports)
        if any(same_country(c, m) for c in sig.countries for m in mine):
            j_start, j_end = _date(windows[0]["start"] - slack), _date(windows[-1]["end"] + slack)
            if _overlap(max(j_start, today - timedelta(days=1)), j_end, s_start, s_end):
                return Match(sig, shipment, "country", None, None,
                             f"signal is about {', '.join(sig.countries)}; shipment route touches it")
    return None


def match_tariff(sig: Signal, shipment: dict, ports: PortIndex, cfg: dict, today: date) -> Match | None:
    mine = _shipment_countries(shipment, ports)
    if sig.countries and not any(same_country(c, m) for c in sig.countries for m in mine):
        return None
    if sig.products and not product_matches(sig.products, shipment.get("product_category", ""), cfg):
        return None
    if not sig.countries and not sig.products:
        return None  # a notice about neither a country nor a product cannot be tied to this shipment
    eta = shipment.get("eta") or shipment.get("estimated_arrival") or shipment.get("eta_date")
    eta_d = _date(datetime.fromisoformat(str(eta).replace("Z", "+00:00"))) if eta else None
    horizon = timedelta(days=cfg["loss_model"]["tariff_horizon_days"])
    if sig.start and eta_d and not (sig.start <= eta_d <= sig.start + horizon):
        return None  # arrives before the rule takes effect (or far after it)
    return Match(sig, shipment, "country", None, None,
                 f"origin {shipment.get('country')}, {shipment.get('product_category')}"
                 + (f", arrives {eta_d} vs effective {sig.start}" if sig.start and eta_d else ", effective date not stated"))


def match_fx(sig: Signal, shipment: dict, ports: PortIndex, cfg: dict, today: date) -> Match | None:
    if any(same_country(c, shipment.get("country")) for c in sig.countries):
        return Match(sig, shipment, "country", None, None, f"supplier in {shipment.get('country')} is paid in {sig.fx_currency}")
    return None


_MATCHERS = {DELAY: match_delay, TARIFF: match_tariff, FX: match_fx}


def match_all(signals: list[Signal], shipments: list[dict], ports: PortIndex, cfg: dict, today: date) -> dict[str, list[Match]]:
    out: dict[str, list[Match]] = {}
    for sig in signals:
        fn = _MATCHERS[sig.kind]
        hits = [m for s in shipments if (m := fn(sig, s, ports, cfg, today))]
        if hits:
            out[sig.signal_id] = hits
    return out
