import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from google.adk.events import event as adk_event
from google.adk.runners import Runner

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
from src.ingestion.bq_client import check_duplicate_alert, save_alert


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
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return {"raw_response": text}
        payload = json.loads(match.group(0))
    return SupplyChainAnalysis.model_validate(payload).model_dump()


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
    tracer = get_tracer()
    try:
        with tracer.start_as_current_span("agent_cycle") as span:
            span.set_attribute("business_id", business_id)
            span.set_attribute("session_id", session_id)
            span.set_attribute("model", MODEL)
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
                    state_result = session.state.get("final_analysis")
                    if isinstance(state_result, str):
                        final_text = state_result
                    elif isinstance(state_result, dict):
                        final_text = json.dumps(state_result)

            if not final_text:
                span.set_attribute("success", False)
                return {"error": "ADK completed without a final root-agent response."}

            result = _parse_result(final_text)
            result["tool_calls"] = tool_calls
            result["session_id"] = session_id
            span.set_attribute("success", True)
            span.set_attribute("tool_call_count", len(tool_calls))
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
        try:
            result = run_agent_cycle()
            if result:
                print(json.dumps(result, indent=2))
                _persist_alert_if_new(result, "demo-business-001")
        except Exception as exc:
            print(f"Cycle error: {exc}")
        print("Next cycle in 15 minutes...")
        time.sleep(900)
