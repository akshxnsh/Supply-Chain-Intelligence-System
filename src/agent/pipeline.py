"""Deterministic supply-chain pipeline — replaces the 5-agent LLM delegation.

Goal (see project optimization task): run the entire analysis in Python using
the EXACT same deterministic functions the agents called as tools, passing
structured results forward, and make exactly ONE model call (synthesis) for the
genuine judgment fields. This collapses ~25-40 model calls/simulation to 1.

Nothing here changes business logic: detection, exposure, scoring, black-swan,
calibration, PO/email templates, and alert rules all call the original
functions unchanged. Only the *orchestration* moved from the LLM to code.

Stage map (mirrors the former agents):
    DisruptionDetectionAgent-> code only (detect_disruptions + detect_black_swan)
    SupplierRiskAgent       -> code only (calculate_impact + search + score)
    CalibrationAgent        -> code only (calibration baseline + drift + cycles)
    ProcurementAgent        -> code only (PO/email templates)
    Synthesis               -> single model call (severity + PO sizing judgment)

FreshnessAgent is not on the simulation hot path: it does not feed the analysis
schema and is already exposed as the code-only /api/freshness endpoint (no model
call). It can be invoked on demand from the dashboard's freshness panel.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.agent.quota import CallBudget, cached_call
from src.agent.schemas import SupplyChainAnalysis
from src.agent.synthesis import synthesize
from src.agent.tools import (
    detect_black_swan,
    generate_owner_email,
    generate_purchase_order,
)

# Deterministic business-logic functions (the originals the tools wrapped).
from src.detection.disruption_detector import detect_disruptions as _detect_disruptions
from src.exposure.calculator import calculate_impact as _calculate_impact
from src.suppliers.scorer import score_suppliers as _score_suppliers
from src.ingestion.bq_client import (
    query_alternative_suppliers,
    query_business_suppliers,
    query_calibration_with_recency,
    query_port_status,
    query_recent_cycle_performance,
    query_recent_events,
    query_recent_weather_alerts,
    query_severity_drift,
)

_log = logging.getLogger(__name__)

# TTL for caching slow, historical, slow-changing lookups across simulations.
_CALIBRATION_TTL = 600.0  # 10 min — calibration baseline barely moves run-to-run
_SCORING_TTL = 300.0      # 5 min — supplier scoring for an identical candidate set


def _emit(log_callback, msg: str) -> None:
    _log.info("[PIPELINE] %s", msg)
    if log_callback:
        try:
            log_callback(msg)
        except Exception:  # noqa: BLE001 — logging must never break the cycle
            pass


def _relevant_port_congestion(business_id: str) -> list[dict[str, Any]]:
    """Gather port-status rows for ports on this business's active shipments.

    Mirrors how detect_disruptions scopes port queries, so detect_black_swan
    receives the same port universe it would have under the agent flow.
    """
    try:
        from src.prediction.utils import fetch_shipment_schedule, split_route

        shipments = fetch_shipment_schedule(business_id)
        ports: set[str] = set()
        for sh in shipments:
            for key in ("origin_port", "destination_port"):
                pn = sh.get(key)
                if pn and pn != "Domestic":
                    ports.add(pn)
            for checkpoint in split_route(sh.get("route") or ""):
                if checkpoint and checkpoint != "Domestic":
                    ports.add(checkpoint)
        rows: list[dict[str, Any]] = []
        for pn in ports:
            rows.extend(query_port_status(pn))
        return rows
    except Exception as exc:  # noqa: BLE001
        _log.warning("[PIPELINE] port congestion gather failed (%s) — using []", exc)
        return []


def _primary_event(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Most material recent event by raw severity — used for calibration keys."""
    if not events:
        return {}
    return max(events, key=lambda e: e.get("severity_raw", 0) or 0)


def _alternatives_for(
    affected: list[dict[str, Any]],
    supplier_meta: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Search alternatives for every affected (category, country) pair, deduped.

    Uses original-case category/country from business_suppliers because
    query_alternative_suppliers does a case-sensitive country exclusion.
    """
    seen: dict[str, dict[str, Any]] = {}
    pairs: set[tuple[str, str]] = set()
    for supp in affected:
        meta = supplier_meta.get(supp.get("supplier_id"), {})
        category = meta.get("product_category") or supp.get("product_category", "")
        country = meta.get("country") or supp.get("country", "")
        if category:
            pairs.add((category, country))
    for category, country in pairs:
        for cand in query_alternative_suppliers(
            product_category=category, exclude_country=country
        ):
            cid = cand.get("id")
            if cid and cid not in seen:
                seen[cid] = cand
    return list(seen.values())


def _to_alternative_records(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map score_suppliers output onto AlternativeSupplier-shaped dicts."""
    records: list[dict[str, Any]] = []
    for rank, s in enumerate(scored, start=1):
        records.append({
            "rank": rank,
            "supplier_id": s.get("id", ""),
            "name": s.get("name", ""),
            "country": s.get("country", ""),
            "unit_price_usd": s.get("unit_price_usd", 0),
            "lead_time_days": s.get("lead_time_days", 0),
            "dynamic_reliability_score": s.get("dynamic_reliability_score", 0),
            "on_time_rate": s.get("on_time_rate"),
            "avg_review_rating": s.get("avg_review_rating"),
            "completed_orders_count": s.get("completed_orders_count", 0),
            "total_score": s.get("total_score", 0),
            "tradeoff_summary": (
                f"reliability {s.get('dynamic_reliability_score', 0)}/10, "
                f"lead {s.get('lead_time_days', 0)}d, "
                f"${s.get('unit_price_usd', 0)}/unit"
            ),
        })
    return records


async def run_pipeline(
    business_id: str = "demo-business-001",
    log_callback=None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Run the full deterministic pipeline + single synthesis call.

    Returns (result, tool_calls_trace, usage). `result` matches the shape the
    former ADK path produced (a SupplyChainAnalysis dump) so all callers,
    _validate_result, persistence, and the dashboard are unaffected.
    """
    budget = CallBudget()
    trace: list[dict[str, Any]] = []

    def step(tool: str, args: dict[str, Any], response: Any) -> None:
        serialized = response if isinstance(response, str) else json.dumps(response, default=str)
        trace.append({
            "tool": tool,
            "args": args,
            "author": "DeterministicPipeline",
            "response": serialized[:5000],
            "started_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": None,
        })

    # ── Stage 1: Disruption detection (code only) ──────────────────────────────
    _emit(log_callback, "Detecting disruptions across all signals...")
    detection = json.loads(_detect_disruptions(business_id))
    step("detect_disruptions", {"business_id": business_id}, detection)
    affected = detection.get("affected_suppliers", [])
    tariff_impact = detection.get("total_cost_impact_usd", 0.0)

    # Original-case supplier metadata (detection lowercases country/category).
    supplier_meta = {
        row["id"]: {"country": row.get("country", ""), "product_category": row.get("product_category", "")}
        for row in query_business_suppliers(business_id)
    }

    signals: list[str] = sorted({sig for s in affected for sig in s.get("signals", [])})

    # ── Stage 1b: Black-swan anomaly (code only) ───────────────────────────────
    events = query_recent_events(hours=24)
    weather = query_recent_weather_alerts(hours_back=48)
    ports = _relevant_port_congestion(business_id)
    black_swan = json.loads(await detect_black_swan(events, weather, ports))
    step("detect_black_swan", {"events": len(events), "weather": len(weather)}, black_swan)

    # ── Stage 2: Calibration baseline (code only, cached) ──────────────────────
    _emit(log_callback, "Querying calibration baseline...")
    primary = _primary_event(events)
    event_type = (primary.get("source") or "disruption")
    region = (primary.get("location_name") or "")
    calibration = cached_call(
        "calibration", (event_type, region),
        lambda: query_calibration_with_recency(event_type, region),
        ttl_seconds=_CALIBRATION_TTL,
    )
    step("query_calibration_baseline", {"event_type": event_type, "region": region}, calibration)
    try:
        drift = query_severity_drift(business_id, 30)
    except Exception as exc:  # noqa: BLE001
        drift = {"error": str(exc)}
    try:
        cycles = query_recent_cycle_performance(business_id, 10)
    except Exception as exc:  # noqa: BLE001
        cycles = {"error": str(exc)}
    step("query_recent_cycle_performance", {"business_id": business_id}, cycles)

    # ── Stage 3: Financial exposure (code only) ────────────────────────────────
    _emit(log_callback, "Calculating financial exposure...")
    affected_ids = [s.get("supplier_id") for s in affected if s.get("supplier_id")]
    disruption_date = datetime.now(timezone.utc).date().isoformat()
    impact = json.loads(
        _calculate_impact(business_id, affected_ids, disruption_date, tariff_impact)
    )
    step("calculate_impact", {"affected_supplier_ids": affected_ids}, impact)

    # ── Stage 4: Alternative suppliers + scoring (code only, cached) ───────────
    _emit(log_callback, "Scoring alternative suppliers...")
    candidates = _alternatives_for(affected, supplier_meta)
    baseline_sev = (calibration or {}).get("weighted_baseline_severity")
    cand_ids = tuple(sorted(c.get("id", "") for c in candidates))
    scored = cached_call(
        "scoring", (cand_ids, baseline_sev),
        lambda: json.loads(_score_suppliers(candidates, baseline_sev)),
        ttl_seconds=_SCORING_TTL,
    )
    step("score_suppliers", {"candidate_count": len(candidates)}, scored)
    alternatives = _to_alternative_records(scored)

    # ── Stage 5: Single synthesis model call (severity + PO sizing) ────────────
    _emit(log_callback, "Synthesizing final recommendation (single model call)...")
    evidence = {
        "business_id": business_id,
        "candidate_events": [
            {k: e.get(k) for k in ("id", "source", "headline", "location_name", "severity_raw", "published_at")}
            for e in events[:8]
        ],
        "affected_suppliers": affected,
        "signals_detected": signals,
        "impact": impact,
        "black_swan": black_swan,
        "calibration": calibration,
        "calibration_drift": drift,
        "alternatives": alternatives,
    }
    decision, synth_mode, _ = synthesize(evidence, budget)
    step("synthesis", {"mode": synth_mode}, decision.model_dump())

    # ── Assemble final result (deterministic; same shape as old path) ──────────
    chosen_event = next(
        (e for e in events if str(e.get("id")) == decision.chosen_event_id),
        primary,
    )
    headline = decision.disruption_summary or chosen_event.get("headline", "")
    disruption_id = decision.chosen_event_id or chosen_event.get("id")
    if not disruption_id and headline:
        disruption_id = f"{business_id}-{hashlib.sha1(headline.encode()).hexdigest()[:12]}"

    disruption = {
        "id": disruption_id,
        "headline": chosen_event.get("headline", headline),
        "summary": decision.disruption_summary,
        "type": decision.disruption_type or chosen_event.get("source", ""),
        "region": decision.disruption_region or chosen_event.get("location_name", ""),
        "date": chosen_event.get("published_at", disruption_date),
    } if affected else {}

    black_swan_detected = bool(black_swan.get("is_anomaly"))

    # ── Procurement: deterministic templates using the synthesized PO params ───
    purchase_order: Any = None
    owner_email: Any = None
    top_supplier: Any = None
    if alternatives:
        rank = decision.po_supplier_rank
        chosen = next((a for a in alternatives if a["rank"] == rank), alternatives[0])
        top_supplier = chosen
        if rank >= 1 and decision.po_quantity > 0 and not black_swan_detected:
            unit_price = chosen.get("unit_price_usd", 0) or 0
            po = json.loads(await generate_purchase_order(
                supplier_name=chosen.get("name", ""),
                supplier_country=chosen.get("country", ""),
                product=(
                    supplier_meta.get(affected[0].get("supplier_id"), {}).get("product_category")
                    or affected[0].get("product_category", "")
                ) if affected else "",
                quantity=decision.po_quantity,
                unit_price=unit_price,
                required_by=decision.po_required_by or disruption_date,
                business_id=business_id,
            ))
            purchase_order = po.get("purchase_order")
            step("generate_purchase_order", {"supplier": chosen.get("name")}, po)
            email = json.loads(await generate_owner_email(
                disruption_summary=headline,
                affected_supplier=affected[0].get("supplier_name", "") if affected else "",
                exposure_usd=impact.get("exposure_usd", 0),
                estimated_loss_usd=impact.get("expected_loss_usd", 0),
                delay_days=0,
                recommended_alternative=chosen.get("name", ""),
                po_quantity=decision.po_quantity,
                po_total_value=po.get("total_value", 0),
                business_id=business_id,
            ))
            owner_email = email.get("email_draft")
            step("generate_owner_email", {"recipient": email.get("recipient")}, email)

    payload = {
        "alert_fired": bool(affected) and (impact.get("exposure_usd", 0) or 0) > 0,
        "disruption": disruption,
        "signals_detected": signals,
        "exposure_usd": impact.get("exposure_usd", 0),
        "expected_loss_usd": impact.get("expected_loss_usd", 0),
        "affected_suppliers": affected,
        "severity_score": decision.severity_score,
        "calibration_confidence": (calibration or {}).get("confidence_score", 0),
        "black_swan_detected": black_swan_detected,
        "suggested_alternatives": alternatives,
        "top_supplier": top_supplier,
        "purchase_order": purchase_order,
        "owner_email": owner_email,
        "synthesis_mode": synth_mode,
    }

    # Normalize through the schema so the shape exactly matches the old path.
    result = SupplyChainAnalysis.model_validate(payload).model_dump()

    usage = {
        **budget.summary(),
        "synthesis_mode": synth_mode,
        "pipeline_stages": len(trace),
    }
    _emit(
        log_callback,
        f"Cycle complete — {budget.calls_made} model call(s), "
        f"severity={decision.severity_score}, alert={payload['alert_fired']}",
    )
    return result, trace, usage
