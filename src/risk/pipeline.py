"""Run the risk pipeline for one business: signals -> matches -> exposure -> confidence -> decision -> alerts table.

    python -m src.risk.pipeline [business_id]      # prints a summary, writes the `alerts` table

Everything numeric is computed here in code; the model (step 8) only turns the result into a recommendation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from psycopg.types.json import Jsonb

from src.ingestion import raw
from src.ingestion.db import get_pool, run_query
from src.ingestion.queries import (query_alternative_suppliers, query_inventory, query_pending_orders,
                                   query_supplier_timetable)
from src.risk.alerts import Decision, decide, lead_time_days, should_renotify
from src.risk.config import load_config
from src.risk.confidence import ConfidenceInput, ConfidenceResult, compute_confidence
from src.risk.exposure import CompanyData, Exposure, compute_exposure
from src.risk.geo import PortIndex
from src.risk.matching import Match, match_all
from src.risk.signals import (DELAY, FX, TARIFF, Signal, signals_from_disasters, signals_from_events,
                              signals_from_forecast, signals_from_fx)

logger = logging.getLogger(__name__)

PRECISION_ORDER = {"port": 0, "chokepoint": 0, "country": 1, "region": 2}


@dataclass
class AlertRow:
    alert_id: str
    business_id: str
    alert_type: str
    level: str
    signal: Signal
    exposure: Exposure
    confidence: ConfidenceResult
    decision: Decision
    lead_time_days: int | None
    act_by: date | None
    action: str
    explanation: list[str] = field(default_factory=list)
    notify_now: bool = False
    notify_reason: str = ""


# -- loading -------------------------------------------------------------------------------------------------

def load_company(business_id: str, today: date, cfg: dict) -> tuple[list[dict], CompanyData]:
    shipments = query_supplier_timetable(business_id)
    orders = query_pending_orders(business_id)
    inventory = {r["product_category"]: float(r["inventory_value_usd"]) for r in query_inventory(business_id)}
    categories = {o["product_category"] for o in orders} | {s["product_category"] for s in shipments}
    lead, best = {}, {}
    for cat in categories:
        alts = query_alternative_suppliers(cat, "")
        if alts:
            lead[cat] = float(min(a["lead_time_days"] for a in alts if a.get("lead_time_days") is not None))
            best[cat] = alts[0]
    return shipments, CompanyData(orders, inventory, lead, best)


def importing_country(business_id: str) -> str:
    rows = run_query("SELECT importing_country FROM trader_settings WHERE business_id = %(b)s", {"b": business_id})
    return rows[0]["importing_country"] if rows else "United States"


def trader_threshold(business_id: str, cfg: dict) -> float:
    rows = run_query("SELECT notify_threshold_usd FROM trader_settings WHERE business_id = %(b)s", {"b": business_id})
    return float(rows[0]["notify_threshold_usd"]) if rows else float(cfg["alerts"]["default_notify_threshold_usd"])


def load_signals(cfg: dict, today: date, ports: PortIndex) -> list[Signal]:
    ev_rows = run_query("""SELECT * FROM events WHERE relevant AND reference_date >= %(since)s""",
                        {"since": today - timedelta(days=30)})
    history: dict[date, dict[str, float]] = {}
    for r in raw.rates_since(cfg["fx"]["lookback_days"] + 15):
        history.setdefault(r["rate_date"], {})[r["currency"]] = r["eur_rate"]
    signals = signals_from_events(ev_rows, cfg, today)
    signals += signals_from_disasters(raw.active_disasters(days=7), cfg, today)
    signals += signals_from_forecast(raw.upcoming_forecast(), ports, cfg, today)
    signals += signals_from_fx(history, cfg, today)
    return signals


# -- evaluation (pure, easy to test) -------------------------------------------------------------------------

def best_precision(matches: list[Match]) -> str:
    return sorted((m.precision for m in matches), key=lambda p: PRECISION_ORDER[p])[0]


def default_action(exposure: Exposure, company: CompanyData, act_by: date | None, today: date) -> str:
    sig = exposure.signal
    if sig.kind == DELAY and exposure.worst_stock:
        s = exposure.worst_stock
        alt = company.alternatives.get(s.category)
        who = f" from {alt['name']} ({alt['country']})" if alt else ""
        when = "now" if act_by is None or act_by <= today else f"by {act_by.isoformat()}"
        return f"Order replacement {s.category}{who} {when}: stock lasts {s.days_of_stock:g} days, a {s.delay_days:g}-day delay plus {s.replacement_lead_days:g}-day lead time would run it out."
    if sig.kind == DELAY:
        return "Warn customers with orders due soon and monitor; stock should cover the delay."
    if sig.kind == TARIFF and sig.rate_percent is None:
        return "Check the duty rate in the notice: it does not state one, so the cost cannot be priced yet."
    if sig.kind == TARIFF:
        when = f" from {sig.start.isoformat()}" if sig.start else ""
        return f"Check landed cost: {sig.rate_percent:g}% duty{when}. Consider bringing orders forward or another origin."
    return "Consider fixing the exchange rate or paying earlier."


def evaluate(signals: list[Signal], shipments: list[dict], company: CompanyData, ports: PortIndex, cfg: dict,
             today: date, threshold_usd: float, business_id: str, importing_country: str | None = None) -> list[AlertRow]:
    matches = match_all(signals, shipments, ports, cfg, today, importing_country)
    rows: list[AlertRow] = []
    for sig in signals:
        ms = matches.get(sig.signal_id)
        if not ms:
            continue
        exposure = compute_exposure(sig, ms, company, cfg, today)
        if exposure.loss_if_happens_usd <= 0 and not exposure.stockout_risk and not exposure.unpriced_reason:
            continue
        conf = compute_confidence(ConfidenceInput(
            source_class=sig.source_class, independent_sources=sig.independent_sources, days_ahead=sig.days_ahead,
            date_clarity=sig.date_clarity, location_clarity=sig.location_clarity, match_precision=best_precision(ms),
            reference_date=sig.reference_date, today=today), cfg)
        decision = decide(exposure, conf, threshold_usd, cfg)
        act_by = exposure.worst_stock.act_by if exposure.worst_stock else (
            (sig.start - timedelta(days=1)) if sig.kind == TARIFF and sig.start and sig.start > today else None)
        start, _ = sig.window(today, cfg)
        alert_type = "now" if sig.is_now(today) else "heads_up"
        why = list(decision.explanation) + [f"matched: {m.why}" for m in ms[:3]]
        rows.append(AlertRow(
            alert_id=hashlib.sha1(f"{business_id}|{sig.dedupe_key}".encode()).hexdigest()[:20], business_id=business_id,
            alert_type=alert_type, level=decision.level, signal=sig, exposure=exposure, confidence=conf, decision=decision,
            lead_time_days=lead_time_days(start, today) if alert_type == "heads_up" else None, act_by=act_by,
            action=default_action(exposure, company, act_by, today), explanation=why))
    return rows


# -- persistence -----------------------------------------------------------------------------------------------

UPSERT_ALERT = """
INSERT INTO alerts (alert_id, business_id, alert_type, level, signal_kind, source, event_type, title, affected_shipments,
    affected_suppliers, exposure_usd, expected_loss_usd, loss_components, confidence_band, confidence_score,
    confidence_reasons, stockout_risk, lead_time_days, event_start, event_end, act_by, action, evidence, explanation,
    assumptions, last_notified_at, last_notified_level, last_notified_loss, last_notified_band, notified_count)
VALUES (%(alert_id)s, %(business_id)s, %(alert_type)s, %(level)s, %(signal_kind)s, %(source)s, %(event_type)s, %(title)s,
    %(affected_shipments)s, %(affected_suppliers)s, %(exposure_usd)s, %(expected_loss_usd)s, %(loss_components)s,
    %(confidence_band)s, %(confidence_score)s, %(confidence_reasons)s, %(stockout_risk)s, %(lead_time_days)s,
    %(event_start)s, %(event_end)s, %(act_by)s, %(action)s, %(evidence)s, %(explanation)s, %(assumptions)s,
    %(notified_at)s, %(notified_level)s, %(notified_loss)s, %(notified_band)s, %(notified_count)s)
ON CONFLICT (alert_id) DO UPDATE SET
    alert_type = EXCLUDED.alert_type, level = EXCLUDED.level, title = EXCLUDED.title, signal_kind = EXCLUDED.signal_kind,
    source = EXCLUDED.source, event_type = EXCLUDED.event_type, status = CASE WHEN alerts.status = 'resolved' THEN 'open' ELSE alerts.status END,
    affected_shipments = EXCLUDED.affected_shipments, affected_suppliers = EXCLUDED.affected_suppliers,
    exposure_usd = EXCLUDED.exposure_usd, expected_loss_usd = EXCLUDED.expected_loss_usd,
    loss_components = EXCLUDED.loss_components, confidence_band = EXCLUDED.confidence_band,
    confidence_score = EXCLUDED.confidence_score, confidence_reasons = EXCLUDED.confidence_reasons,
    stockout_risk = EXCLUDED.stockout_risk, lead_time_days = EXCLUDED.lead_time_days, event_start = EXCLUDED.event_start,
    event_end = EXCLUDED.event_end, act_by = EXCLUDED.act_by, action = EXCLUDED.action, evidence = EXCLUDED.evidence,
    explanation = EXCLUDED.explanation, assumptions = EXCLUDED.assumptions, last_seen = now(), updated_at = now(),
    last_notified_at = COALESCE(EXCLUDED.last_notified_at, alerts.last_notified_at),
    last_notified_level = COALESCE(EXCLUDED.last_notified_level, alerts.last_notified_level),
    last_notified_loss = COALESCE(EXCLUDED.last_notified_loss, alerts.last_notified_loss),
    last_notified_band = COALESCE(EXCLUDED.last_notified_band, alerts.last_notified_band),
    notified_count = alerts.notified_count + EXCLUDED.notified_count
"""


LOG_NOTIFICATION = """
INSERT INTO alert_notifications (alert_id, business_id, notified_at, level, reason, title, source, expected_loss_usd, confidence_band,
                                 stockout_risk, act_by, action)
VALUES (%(alert_id)s, %(business_id)s, %(at)s, %(level)s, %(reason)s, %(title)s, %(source)s, %(loss)s, %(band)s, %(stockout)s,
        %(act_by)s, %(action)s)
"""


def persist(rows: list[AlertRow], cfg: dict, now: datetime | None = None) -> None:
    """Write alerts; decide per alert whether this run counts as a (new) notification (no repeats unless worse)."""
    now = now or datetime.now(timezone.utc)
    with get_pool().connection() as conn:
        for r in rows:
            prev = conn.execute("SELECT last_notified_at, last_notified_loss, last_notified_band, last_notified_level "
                                "FROM alerts WHERE alert_id = %s", (r.alert_id,)).fetchone()
            r.notify_now, r.notify_reason = should_renotify(prev, r.level, r.decision.expected_loss_usd,
                                                            r.confidence.band, cfg)
            e, sig = r.exposure, r.signal
            start, end = sig.window(now.date(), cfg)
            conn.execute(UPSERT_ALERT, {
                "alert_id": r.alert_id, "business_id": r.business_id, "alert_type": r.alert_type, "level": r.level,
                "signal_kind": sig.kind, "source": sig.source, "event_type": sig.event_type, "title": sig.title[:500],
                "affected_shipments": Jsonb(e.affected_shipment_ids), "affected_suppliers": Jsonb(e.affected_suppliers),
                "exposure_usd": e.loss_if_happens_usd, "expected_loss_usd": r.decision.expected_loss_usd,
                "loss_components": Jsonb({**e.components, **({"value_at_risk_usd": e.value_at_risk_usd} if e.unpriced_reason else {})}), "confidence_band": r.confidence.band,
                "confidence_score": r.confidence.score, "confidence_reasons": Jsonb(r.confidence.reasons),
                "stockout_risk": e.stockout_risk, "lead_time_days": r.lead_time_days, "event_start": start, "event_end": end,
                "act_by": r.act_by, "action": r.action, "evidence": Jsonb(sig.evidence),
                "explanation": Jsonb(r.explanation + [f"notification: {r.notify_reason}"]),
                "assumptions": Jsonb(e.assumptions),
                "notified_at": now if r.notify_now else None, "notified_level": "notify" if r.notify_now else None,
                "notified_loss": r.decision.expected_loss_usd if r.notify_now else None,
                "notified_band": r.confidence.band if r.notify_now else None, "notified_count": 1 if r.notify_now else 0,
            })
            if r.notify_now:                                   # keep every notification decision, not just the latest per alert
                conn.execute(LOG_NOTIFICATION, {
                    "alert_id": r.alert_id, "business_id": r.business_id, "at": now, "level": "notify", "reason": r.notify_reason,
                    "title": sig.title[:500], "source": sig.source, "loss": r.decision.expected_loss_usd, "band": r.confidence.band,
                    "stockout": e.stockout_risk, "act_by": r.act_by, "action": r.action})


RESOLVE_STALE = """
UPDATE alerts SET status = 'resolved', updated_at = now(),
       explanation = explanation || '["closed: the latest run no longer produces this alert"]'::jsonb
WHERE business_id = %(b)s AND status = 'open' AND NOT (alert_id = ANY(%(ids)s))
"""


def resolve_stale(business_id: str, current_ids: list[str]) -> int:
    """Open alerts that this run did NOT produce again (the event ended, the match or the rules changed) are closed.
    Acknowledged alerts are left alone."""
    with get_pool().connection() as conn:
        return conn.execute(RESOLVE_STALE, {"b": business_id, "ids": list(current_ids)}).rowcount


# -- entry point ------------------------------------------------------------------------------------------------

def run_risk(business_id: str = "demo-business-001", today: date | None = None, persist_alerts: bool = True) -> dict:
    cfg = load_config()
    today = today or datetime.now(timezone.utc).date()
    ports = PortIndex(raw.port_and_chokepoint_locations())
    shipments, company = load_company(business_id, today, cfg)
    signals = load_signals(cfg, today, ports)
    threshold = trader_threshold(business_id, cfg)
    rows = evaluate(signals, shipments, company, ports, cfg, today, threshold, business_id, importing_country(business_id))
    resolved = 0
    if persist_alerts:
        persist(rows, cfg)
        resolved = resolve_stale(business_id, [r.alert_id for r in rows])
    return {
        "business_id": business_id, "today": today.isoformat(), "threshold_usd": threshold, "shipments": len(shipments),
        "signals_by_source": dict(Counter(s.source for s in signals)), "alerts": len(rows),
        "alerts_by_level": dict(Counter(r.level for r in rows)), "alerts_by_type": dict(Counter(r.alert_type for r in rows)),
        "notifications_this_run": sum(1 for r in rows if r.notify_now), "resolved_stale_alerts": resolved, "rows": rows, "company": company, "today_date": today,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    result = run_risk(sys.argv[1] if len(sys.argv) > 1 else "demo-business-001")
    rows = result.pop("rows")
    result.pop("company"), result.pop("today_date")
    print(json.dumps(result, indent=2, default=str))
    for r in sorted(rows, key=lambda x: -x.decision.expected_loss_usd)[:10]:
        print(f"- [{r.level:6}] {r.alert_type:8} {r.signal.title[:70]:70} exp.loss ${r.decision.expected_loss_usd:>10,.0f} ({r.confidence.band})")
