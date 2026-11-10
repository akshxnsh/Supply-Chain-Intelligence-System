"""Build what the judge may see: code-computed FACTS plus citable EVIDENCE (real article / notice / event ids).

The model is never asked to compute money, dates or stock cover: those arrive here as facts. It may only choose an action,
give an act-by date inside the window the code allows, and justify itself by citing evidence ids that exist.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from src.ingestion.db import run_query
from src.judge.schema import EvidenceBundle, EvidenceItem
from src.risk.exposure import CompanyData
from src.risk.pipeline import AlertRow

FACTS_ID = "facts"

SQL_CLUSTER_ARTICLES = """
    SELECT cluster_id, article_id, title, domain, url
    FROM news_cluster_articles WHERE cluster_id = ANY(%(ids)s) AND NOT syndicated
    ORDER BY cluster_id, seen_at LIMIT 200
"""
SQL_NOTICES = """
    SELECT document_number, title, doc_type, abstract, dates_text, url, publication_date, effective_on
    FROM fivetran_raw_federal_register.documents WHERE document_number = ANY(%(ids)s)
"""


def fetch_source_texts(rows: list[AlertRow]) -> dict[str, list[EvidenceItem]]:
    """signal_id -> evidence items for news clusters and notices (the only sources whose text lives in the database)."""
    cluster_ids = {e["id"]: r.signal.signal_id for r in rows for e in r.signal.evidence if e["type"] == "news_cluster"}
    notice_ids = {e["id"]: r.signal.signal_id for r in rows for e in r.signal.evidence if e["type"] == "federal_register"}
    out: dict[str, list[EvidenceItem]] = {}
    if cluster_ids:
        for a in run_query(SQL_CLUSTER_ARTICLES, {"ids": list(cluster_ids)}):
            out.setdefault(cluster_ids[a["cluster_id"]], []).append(
                EvidenceItem(f"article:{a['article_id']}", "news_article", f"{a['title']} ({a['domain']})", a.get("url")))
    if notice_ids:
        for d in run_query(SQL_NOTICES, {"ids": list(notice_ids)}):
            text = f"{d['doc_type']}: {d['title']}"
            if d.get("abstract"):
                text += f" | {d['abstract'][:400]}"
            if d.get("dates_text"):
                text += f" | dates: {d['dates_text'][:200]}"
            out.setdefault(notice_ids[d["document_number"]], []).append(
                EvidenceItem(f"notice:{d['document_number']}", "notice", text, d.get("url")))
    return out


def _own_evidence(row: AlertRow) -> list[EvidenceItem]:
    """Evidence that comes from the signal itself (disasters, forecasts, exchange rates)."""
    sig, items = row.signal, []
    for e in sig.evidence:
        if e["type"] == "gdacs":
            items.append(EvidenceItem(f"gdacs:{e['id']}", "disaster", sig.title, e.get("url")))
        elif e["type"] == "open_meteo":
            items.append(EvidenceItem(f"forecast:{e['id']}", "forecast", sig.title))
        elif e["type"] == "ecb":
            items.append(EvidenceItem(f"ecb:{e['id']}", "exchange_rate", sig.title))
    return items


def _facts(row: AlertRow, company: CompanyData, today: date) -> dict:
    sig, exp, conf = row.signal, row.exposure, row.confidence
    facts: dict = {
        "today": today.isoformat(),
        "alert_type": row.alert_type,                 # now | heads_up
        "signal_kind": sig.kind, "event_type": sig.event_type, "status": sig.status,
        "event_start": sig.start.isoformat() if sig.start else None,
        "event_end": sig.end.isoformat() if sig.end else None,
        "lead_time_days": row.lead_time_days,
        "possible_loss_usd": round(exp.loss_if_happens_usd), "expected_loss_usd": round(row.decision.expected_loss_usd),
        "likelihood": row.decision.likelihood, "confidence_band": conf.band,
        "affected_suppliers": [f"{s['supplier_name']} ({s['country']})" for s in exp.affected_suppliers],
        "affected_shipments": exp.affected_shipment_ids,
        "stock": [{"category": s.category, "days_of_stock": s.days_of_stock, "expected_delay_days": s.delay_days,
                   "replacement_lead_time_days": s.replacement_lead_days, "stockout_risk": s.stockout_risk,
                   "stockout_date": s.stockout_date.isoformat() if s.stockout_date else None,
                   "latest_order_date": s.act_by.isoformat() if s.act_by else None} for s in exp.stock],
        "assumptions": exp.assumptions,
    }
    if sig.kind == "tariff":
        facts["tariff"] = {"rate_percent": sig.rate_percent, "rate_stated": sig.rate_percent is not None}
    if sig.kind == "fx":
        facts["exchange_rate"] = {"currency": sig.fx_currency, "move_percent": sig.fx_move_pct}
    alts = [company.alternatives[c] for c in exp.categories if c in company.alternatives]
    if alts:
        facts["best_alternative_suppliers"] = [{"name": a["name"], "country": a["country"], "lead_time_days": a.get("lead_time_days"),
                                                "reliability_score": a.get("reliability_score")} for a in alts]
    return facts


def _allowed_actions(row: AlertRow) -> set[str]:
    if row.signal.kind == "tariff":
        return {"review_landed_cost", "monitor"}
    if row.signal.kind == "fx":
        return {"hedge_exchange_rate", "monitor"}
    return {"order_replacement", "notify_customers", "monitor"} if row.exposure.stockout_risk else {"notify_customers", "monitor", "none"}


def build_bundle(row: AlertRow, company: CompanyData, today: date, source_texts: dict[str, list[EvidenceItem]] | None = None) -> EvidenceBundle:
    facts = _facts(row, company, today)
    items = [EvidenceItem(FACTS_ID, "computed_facts", "numbers and dates computed by code (see FACTS)")]
    items += (source_texts or {}).get(row.signal.signal_id, [])[:5] + _own_evidence(row)

    dates = {today}
    for d in (row.signal.start, row.signal.end, row.act_by):
        if d:
            dates.add(d)
    for s in row.exposure.stock:
        dates.update(x for x in (s.stockout_date, s.act_by) if x)
    for m in row.exposure.matches:
        eta = m.shipment.get("eta") or m.shipment.get("eta_date")
        if eta:
            try:
                dates.add(datetime.fromisoformat(str(eta).replace("Z", "+00:00")).astimezone(timezone.utc).date())
            except ValueError:
                pass
    limit = row.act_by or (row.signal.start if row.signal.start and row.signal.start >= today else None)
    return EvidenceBundle(facts=facts, items=items, allowed_dates=dates, act_by_limit=limit, act_by_floor=today,
                          allowed_action_types=_allowed_actions(row))


def facts_json(bundle: EvidenceBundle) -> str:
    return json.dumps(bundle.facts, sort_keys=True, default=str, indent=1)
