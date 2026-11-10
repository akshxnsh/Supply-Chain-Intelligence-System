"""Every source becomes the same kind of RISK SIGNAL: what it is, where, when, how confident, which direction.

Builders turn rows of each source into Signals; matching.py then matches signals to shipments and orders.
No new data source exists unless it feeds a part of the output.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from src.risk.geo import PortIndex

# signal kinds
DELAY, TARIFF, FX = "delay", "tariff", "fx"


@dataclass
class Signal:
    signal_id: str
    dedupe_key: str                      # stable across runs: the same real-world thing gets the same key
    kind: str                            # delay | tariff | fx
    source: str                          # gdelt | federal_register | gdacs | open_meteo | ecb
    source_class: str                    # official_notice | official_alert | observed_data | forecast_model | news
    event_type: str
    title: str
    status: str                          # happened | ongoing | expected | forecast | unknown
    reference_date: date                 # when the information was published / observed
    locations: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    lat: float | None = None
    lon: float | None = None
    radius_km: float | None = None
    start: date | None = None
    end: date | None = None
    expected_delay_days: float = 0.0
    rate_percent: float | None = None    # tariff signals: only a rate the notice STATES (None = unknown, never guessed)
    imposing_country: str | None = None  # tariff signals: who charges the duty (None = the text does not say)
    fx_currency: str | None = None
    fx_move_pct: float | None = None
    independent_sources: int = 1
    date_clarity: str | None = None
    location_clarity: str | None = None
    days_ahead: float | None = None      # forecast signals
    evidence: list[dict] = field(default_factory=list)

    def window(self, today: date, cfg: dict) -> tuple[date, date]:
        """(start, end) of the period this signal acts on; unknown dates fall back to 'now until the horizon'."""
        duration = timedelta(days=cfg["default_event_duration_days"])
        if self.start is None:
            if self.status in ("happened", "ongoing"):
                s = self.reference_date
                return s, max(s + duration, today)
            return today, today + timedelta(days=cfg["horizon_days"])
        return self.start, self.end or (self.start + duration)

    def is_now(self, today: date) -> bool:
        """'Happening now' alert (vs a heads-up about something that has not started yet)."""
        if self.status in ("happened", "ongoing"):
            return True
        return self.start is not None and self.start <= today


def _key(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _to_date(v) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v.astimezone(timezone.utc) if v.tzinfo else v).date()
    return v


# -- reader events (news clusters and official notices) ----------------------------------------------------

def signals_from_events(rows: list[dict], cfg: dict, today: date) -> list[Signal]:
    out = []
    for r in rows:
        if not r.get("relevant"):
            continue
        etype = r["event_type"]
        is_notice = r["source_type"] == "notice"
        tariff = etype == "tariff_or_trade_rule" or r.get("direction") == "higher_cost"
        sig = Signal(
            signal_id=r["event_id"], dedupe_key=r["event_id"], kind=TARIFF if tariff else DELAY,
            source="federal_register" if is_notice else "gdelt",
            source_class="official_notice" if is_notice else "news",
            event_type=etype, title=r["summary"] or r["event_id"], status=r["status"],
            reference_date=r["reference_date"], locations=list(r["locations"] or []),
            countries=list(r["countries"] or []), products=list(r["products"] or []),
            start=r["start_date"], end=r["end_date"], imposing_country=r.get("imposing_country"),
            expected_delay_days=0.0 if tariff else float(cfg["default_delay_days"].get(etype, cfg["default_delay_days"]["unknown"])),
            independent_sources=int(r.get("independent_sources") or 1),
            date_clarity=r["date_clarity"], location_clarity=r["location_clarity"],
            evidence=[{"type": "federal_register" if is_notice else "news_cluster", "id": r["source_ref"]}],
        )
        if tariff:
            rate = r.get("rate_percent")
            sig.rate_percent = float(rate) if rate is not None else None
        out.append(sig)
    return out


# -- GDACS disasters ---------------------------------------------------------------------------------------

def signals_from_disasters(rows: list[dict], cfg: dict, today: date) -> list[Signal]:
    out = []
    for r in rows:
        if r.get("alert_level") not in cfg["disaster_alert_levels"] or r.get("lat") is None:
            continue
        gtype = r["event_type"]
        etype = cfg["disaster_event_type"].get(gtype, "natural_disaster")
        current = bool(r.get("is_current"))
        out.append(Signal(
            signal_id=f"gdacs:{r['event_id']}", dedupe_key=f"gdacs:{r['event_id']}", kind=DELAY, source="gdacs",
            source_class="official_alert", event_type=etype, title=f"{r.get('name') or r['event_id']} ({r['alert_level']} alert)",
            status="ongoing" if current else "happened", reference_date=_to_date(r["date_modified"]) or today,
            countries=[c for c in (r.get("country"),) if c], lat=r["lat"], lon=r["lon"],
            radius_km=float(cfg["disaster_radius_km"].get(gtype, 200)), start=_to_date(r["from_date"]), end=_to_date(r["to_date"]),
            expected_delay_days=float(cfg["default_delay_days"][etype]),
            evidence=[{"type": "gdacs", "id": r["event_id"], "url": r.get("report_url")}],
        ))
    return out


# -- Open-Meteo forecasts ----------------------------------------------------------------------------------

def signals_from_forecast(rows: list[dict], ports: PortIndex, cfg: dict, today: date) -> list[Signal]:
    """One signal per (location, rule) covering the first..last day the forecast crosses the threshold."""
    hits: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        for rule in cfg["forecast_rules"]:
            v = r.get(rule["field"])
            if v is not None and v >= rule["at_least"]:
                hits.setdefault((r["location_id"], rule["name"]), []).append({**r, "_rule": rule, "_value": v})
                break  # first matching rule wins for that location-day
    out = []
    for (loc_id, rule_name), days in hits.items():
        place = ports.by_id(loc_id)
        if place is None:
            continue
        rule = days[0]["_rule"]
        first, last = min(d["forecast_date"] for d in days), max(d["forecast_date"] for d in days)
        peak = max(d["_value"] for d in days)
        out.append(Signal(
            signal_id=f"forecast:{loc_id}:{rule_name}", dedupe_key=f"forecast:{loc_id}:{rule_name}", kind=DELAY,
            source="open_meteo", source_class="forecast_model", event_type=rule["event_type"],
            title=f"{rule_name.replace('_', ' ')} forecast at {place.name}: {rule['field']} up to {peak:g}",
            status="forecast", reference_date=today, locations=[place.name], countries=[c for c in (place.country,) if c],
            lat=place.lat, lon=place.lon, radius_km=50.0, start=first, end=last,
            expected_delay_days=float(rule["delay_days"]), days_ahead=max(0, (first - today).days),
            evidence=[{"type": "open_meteo", "id": f"{loc_id}:{first}..{last}"}],
        ))
    return out


# -- ECB exchange rates ------------------------------------------------------------------------------------

def usd_per_unit(rates: dict[str, float], currency: str) -> float | None:
    """ECB gives units of each currency per 1 EUR; USD per 1 unit of `currency` = rate[USD] / rate[currency]."""
    if "USD" not in rates:
        return None
    if currency == "EUR":
        return rates["USD"]
    return rates["USD"] / rates[currency] if currency in rates else None


def signals_from_fx(history: dict[date, dict[str, float]], cfg: dict, today: date) -> list[Signal]:
    """A supplier currency that strengthened against USD by >= min_move_pct over the lookback makes imports dearer."""
    fx = cfg["fx"]
    if len(history) < 2:
        return []
    days = sorted(history)
    latest = days[-1]
    base_day = next((d for d in days if (latest - d).days <= fx["lookback_days"]), days[0])
    currency_countries: dict[str, list[str]] = {}
    for country, ccy in fx["country_currency"].items():
        currency_countries.setdefault(ccy, []).append(country)
    out = []
    for ccy, countries in currency_countries.items():
        now_v, then_v = usd_per_unit(history[latest], ccy), usd_per_unit(history[base_day], ccy)
        if not now_v or not then_v:
            continue
        move = (now_v / then_v - 1.0) * 100.0
        if move >= fx["min_move_pct"]:
            out.append(Signal(
                signal_id=f"fx:{ccy}:{latest.isoformat()[:7]}", dedupe_key=f"fx:{ccy}:{latest.isoformat()[:7]}", kind=FX,
                source="ecb", source_class="observed_data", event_type="other",
                title=f"{ccy} up {move:.1f}% against USD since {base_day} (suppliers in {', '.join(countries)} cost more)",
                status="ongoing", reference_date=latest, countries=countries, fx_currency=ccy, fx_move_pct=round(move, 2),
                evidence=[{"type": "ecb", "id": f"{ccy}:{base_day}..{latest}"}],
            ))
    return out
