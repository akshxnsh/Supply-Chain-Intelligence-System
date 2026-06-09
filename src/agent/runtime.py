import asyncio
import hashlib
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

_log = logging.getLogger(__name__)

from google.adk.events import event as adk_event
from google.adk.runners import Runner
from opentelemetry.trace import SpanKind, StatusCode

from src.agent.agents import MODEL, create_root_agent
from src.agent.business_registry import get_business
from src.agent.observability import (
    emit_log,
    get_tracer,
    reset_log_callback,
    set_log_callback,
)
from src.agent.schemas import SupplyChainAnalysis
from src.agent.session import create_session_service
from src.ingestion.bq_client import check_duplicate_alert, query_business_suppliers, save_alert, save_phoenix_trace_summary


APP_NAME = "supply-chain-intelligence"
_session_service = None


def _get_session_service():
    global _session_service
    if _session_service is None:
        _session_service = create_session_service()
    return _session_service


def _configure_google_credentials() -> None:
    """ADK reads GOOGLE_API_KEY; preserve the project's GEMINI_API_KEY config."""
    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]


def _validate_result(result: dict, business_id: str) -> dict:
    """Deterministically override fields that the LLM may have hallucinated."""
    flags: list[str] = []

    # --- alert_fired: derive from objective evidence ---
    has_exposure = (result.get("exposure_usd") or 0) > 0
    has_affected = bool(result.get("affected_suppliers"))
    evidence_supports_alert = has_exposure and has_affected
    llm_alert_fired = result.get("alert_fired", False)

    if llm_alert_fired and not evidence_supports_alert:
        flags.append("alert_fired=True but exposure_usd=0 or no affected_suppliers — overriding to False")
        result["alert_fired"] = False
    elif not llm_alert_fired and evidence_supports_alert:
        flags.append("alert_fired=False despite positive exposure and affected suppliers — overriding to True")
        result["alert_fired"] = True

    # --- severity_score: must be in [0.0, 1.0] ---
    score = result.get("severity_score")
    if score is not None:
        if not isinstance(score, (int, float)):
            flags.append(f"severity_score is not numeric ({score!r}) — resetting to 0")
            result["severity_score"] = 0
        elif not (0.0 <= float(score) <= 1.0):
            clamped = max(0.0, min(1.0, float(score)))
            flags.append(f"severity_score={score} out of [0,1] — clamped to {clamped}")
            result["severity_score"] = clamped

    # --- alert_fired=True requires a stable disruption id ---
    if result.get("alert_fired"):
        disruption = result.get("disruption") or {}
        has_id = any(disruption.get(k) for k in ("id", "disruption_id", "event_id"))
        if not has_id:
            flags.append("alert_fired=True but disruption has no stable id — overriding alert_fired to False")
            result["alert_fired"] = False

    # --- exposure_usd must be non-negative ---
    exposure = result.get("exposure_usd")
    if exposure is not None and isinstance(exposure, (int, float)) and exposure < 0:
        flags.append(f"exposure_usd={exposure} is negative — resetting to 0")
        result["exposure_usd"] = 0

    # --- supplier ID cross-check: flag any returned ID not in BQ ---
    try:
        known_ids = {row["id"] for row in query_business_suppliers(business_id)}
        llm_ids = {
            s.get("supplier_id") or s.get("id")
            for s in result.get("affected_suppliers", [])
            if isinstance(s, dict)
        }
        llm_ids.discard(None)
        phantom_ids = llm_ids - known_ids
        if phantom_ids:
            flags.append(f"affected_suppliers contains unknown supplier IDs: {phantom_ids}")
    except Exception as exc:
        _log.warning("[VALIDATE] Supplier ID cross-check skipped: %s", exc)

    # --- H5: black swan — null out PO and email unconditionally ---
    if result.get("black_swan_detected"):
        if result.get("purchase_order") is not None:
            flags.append("black_swan_detected=True — nulling purchase_order (requires human review)")
            result["purchase_order"] = None
        if result.get("owner_email") is not None:
            flags.append("black_swan_detected=True — nulling owner_email (requires human review)")
            result["owner_email"] = None

    if flags:
        _log.warning(
            "[VALIDATE] Hallucination flags for business=%s: %s",
            business_id,
            "; ".join(flags),
        )
        result["validation_flags"] = flags

    return result


def _content_text(content) -> str:
    if not content or not getattr(content, "parts", None):
        return ""
    return "".join(
        part.text
        for part in content.parts
        if getattr(part, "text", None)
    )


def _parse_result(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned)

    payload = None
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    if payload is None:
        _log.error(
            "[PARSE] LLM response is not valid JSON — raw text (first 500 chars): %.500s",
            text,
        )
        return {"error": "parse_failure", "raw_response": text}

    try:
        return SupplyChainAnalysis.model_validate(payload).model_dump()
    except Exception as exc:
        _log.error(
            "[PARSE] Schema validation failed: %s — payload keys: %s",
            exc,
            list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
        )
        return {"error": "parse_failure", "raw_response": text}


def _save_cycle_trace(
    session_id: str,
    business_id: str,
    tool_calls: list,
    success: bool,
    latency_ms: float,
    severity_score: float,
    alert_fired: bool,
) -> None:
    """Best-effort write of one cycle summary to phoenix_traces BQ table."""
    try:
        save_phoenix_trace_summary({
            "trace_id":   session_id,
            "span_id":    f"{business_id}-cycle",
            "tool_name":  "agent_cycle",
            "input_json": json.dumps({"business_id": business_id, "tool_count": len(tool_calls)}),
            "output_json": json.dumps({
                "success":        success,
                "alert_fired":    alert_fired,
                "severity_score": severity_score,
            }),
            "latency_ms":   round(latency_ms, 1),
            "token_count":  None,
            "created_at":   datetime.now(timezone.utc).isoformat(),
        })
    except Exception as exc:
        _log.warning("[TRACE] Phoenix trace write failed (non-fatal): %s", exc)


async def run_agent_cycle_async(
    business_id: str = "demo-business-001",
    log_callback=None,
    session_id: str | None = None,
) -> dict | None:
    """Run one supply-chain cycle through ADK Runner and SessionService."""
    _configure_google_credentials()
    business = get_business(business_id)
    session_id = session_id or f"{business_id}-{uuid.uuid4().hex}"
    session_service = _get_session_service()
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=business_id,
        session_id=session_id,
        state={
            "business_id": business_id,
            "business_name": business["name"],
            "cycle_started_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    runner = Runner(
        agent=create_root_agent(),
        app_name=APP_NAME,
        session_service=session_service,
    )
    prompt = (
        "Run the complete supply-chain disruption analysis now. Delegate every "
        "specialist stage, use current tool data, and return the final structured "
        "recommendation."
    )
    message = adk_event.types.Content(
        role="user",
        parts=[adk_event.types.Part(text=prompt)],
    )

    token = set_log_callback(log_callback)
    tool_calls: list[dict[str, Any]] = []
    final_text = ""
    _cycle_start = time.monotonic()
    tracer = get_tracer()
    try:
        with tracer.start_as_current_span("agent_cycle", kind=SpanKind.INTERNAL) as span:
            span.set_attribute("business_id", business_id)
            span.set_attribute("session_id", session_id)
            span.set_attribute("model", MODEL)
            span.set_attribute("input.value", json.dumps({
                "business_id": business_id,
                "prompt": prompt[:500],
            }))
            emit_log(
                f"ADK cycle starting: {business['name']} [{business_id}]"
            )

            async for event in runner.run_async(
                user_id=business_id,
                session_id=session_id,
                new_message=message,
            ):
                for call in event.get_function_calls():
                    args = dict(call.args) if call.args else {}
                    tool_calls.append({"tool": call.name, "args": args})
                if event.author == "SupplyChainIntelligenceAgent":
                    text = _content_text(event.content)
                    if text and event.is_final_response():
                        final_text = text

            if not final_text:
                session = await session_service.get_session(
                    app_name=APP_NAME,
                    user_id=business_id,
                    session_id=session_id,
                )
                if session:
                    _fallback_keys = [
                        "final_analysis",
                        "procurement_analysis",
                        "supplier_risk_analysis",
                        "calibration_analysis",
                        "disruption_analysis",
                    ]
                    for _key in _fallback_keys:
                        state_result = session.state.get(_key)
                        if state_result is not None:
                            if _key != "final_analysis":
                                _log.warning(
                                    "[CYCLE] final_analysis absent; falling back to session state key '%s'",
                                    _key,
                                )
                            if isinstance(state_result, str):
                                final_text = state_result
                            elif isinstance(state_result, dict):
                                final_text = json.dumps(state_result)
                            if final_text:
                                break

            if not final_text:
                span.set_status(StatusCode.ERROR, "no_final_response")
                span.set_attribute("output.value", json.dumps({"error": "no_final_response"}))
                return {"error": "ADK completed without a final root-agent response."}

            result = _parse_result(final_text)
            result["tool_calls"] = tool_calls
            result["session_id"] = session_id
            if not result.get("error"):
                result = _validate_result(result, business_id)
            if result.get("error") == "parse_failure":
                span.set_status(StatusCode.ERROR, "parse_failure")
                span.set_attribute("output.value", json.dumps({"error": "parse_failure"}))
                _log.error(
                    "[CYCLE] Parse failure for business=%s session=%s",
                    business_id,
                    session_id,
                )
            else:
                span.set_attribute("tool_call_count", len(tool_calls))
                span.set_attribute("output.value", json.dumps({
                    "alert_fired":    result.get("alert_fired", False),
                    "severity_score": result.get("severity_score", 0),
                    "disruption_id":  (result.get("disruption") or {}).get("id"),
                    "tool_calls":     len(tool_calls),
                }))
                span.set_status(StatusCode.OK)
                latency_ms = (time.monotonic() - _cycle_start) * 1000
                asyncio.ensure_future(
                    asyncio.to_thread(
                        _save_cycle_trace,
                        session_id,
                        business_id,
                        tool_calls,
                        True,
                        latency_ms,
                        result.get("severity_score", 0),
                        result.get("alert_fired", False),
                    )
                )
            return result
    finally:
        reset_log_callback(token)
        await runner.close()


def run_agent_cycle(
    business_id: str = "demo-business-001",
    log_callback=None,
) -> dict | None:
    """Synchronous compatibility entrypoint backed entirely by ADK."""
    return asyncio.run(
        run_agent_cycle_async(
            business_id=business_id,
            log_callback=log_callback,
        )
    )


def _persist_alert_if_new(result: dict, business_id: str) -> None:
    """Preserve the existing post-run BigQuery alert persistence behavior."""
    if not result.get("alert_fired"):
        return

    # H2: hard minimum-exposure guard — defence-in-depth alongside _validate_result()
    exposure = result.get("exposure_usd") or result.get("exposure") or 0
    if exposure <= 0:
        _log.warning(
            "[ALERT] Skipping persist for business=%s: exposure_usd=%s — no financial impact",
            business_id, exposure,
        )
        return

    disruption = result.get("disruption") or {}
    disruption_id = (
        disruption.get("id")
        or disruption.get("disruption_id")
        or disruption.get("event_id")
    )
    if not disruption_id:
        headline = disruption.get("headline") or disruption.get("summary")
        if not headline:
            print("[ALERT] Skipping persist: no stable disruption identifier")
            return
        digest = hashlib.sha1(headline.encode("utf-8")).hexdigest()[:12]
        disruption_id = f"{business_id}-{digest}"
        # H1: log when the SHA1 fallback fires so operators can investigate
        _log.warning(
            "[DEDUP] No stable disruption id — SHA1 fallback used. "
            "Rephrased headline will produce a different id and duplicate the alert. "
            "headline=%.120s  derived_id=%s",
            headline, disruption_id,
        )

    if check_duplicate_alert(business_id, str(disruption_id)):
        print(f"[DEDUP] Skipping duplicate alert for '{disruption_id}'")
        return

    now = datetime.now(timezone.utc)
    alert = {
        "id": f"alert-{now.strftime('%Y%m%d%H%M%S')}-{business_id}",
        "business_id": business_id,
        "disruption_id": str(disruption_id),
        "severity_score": result.get("severity_score"),
        "exposure_usd": result.get("exposure_usd") or result.get("exposure"),
        "actions_json": json.dumps(result.get("suggested_alternatives", [])),
        "status": "active",
        "created_at": now.isoformat(),
    }
    save_alert(alert)


def run_loop() -> None:
    """Run the ADK agent every 15 minutes."""
    print("Supply Chain ADK agent starting...")
    while True:
        # H4: separate agent errors from persistence errors
        try:
            result = run_agent_cycle()
        except Exception as exc:
            _log.error("[LOOP] Agent cycle failed: %s", exc)
            print("Next cycle in 15 minutes...")
            time.sleep(900)
            continue

        if result:
            print(json.dumps(result, indent=2))
            try:
                _persist_alert_if_new(result, "demo-business-001")
            except Exception as exc:
                _log.error("[LOOP] Alert persistence failed (agent cycle succeeded): %s", exc)

        print("Next cycle in 15 minutes...")
        time.sleep(900)
