from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys, os, json, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from src.agent.runtime import run_agent_cycle_async, _persist_alert_if_new
from src.agent.tools import generate_purchase_order
from src.agent.business_registry import list_businesses, get_business
from src.ingestion.bq_client import run_query_safe
from google.cloud import bigquery as _bq
import asyncio as _asyncio
from dataclasses import dataclass, field


@dataclass
class _SimState:
    """Per-business simulation state so concurrent runs don't clobber each other."""
    live_log: list = field(default_factory=list)
    last_result: dict = field(default_factory=dict)
    is_running: bool = False
    lock: _asyncio.Lock = field(default_factory=_asyncio.Lock)


# business_id -> _SimState. Each business gets isolated logs/result/lock.
_sim_states: dict[str, _SimState] = {}


def _get_sim_state(business_id: str) -> _SimState:
    """Return (creating if needed) the isolated simulation state for a business."""
    state = _sim_states.get(business_id)
    if state is None:
        state = _SimState()
        _sim_states[business_id] = state
    return state


app = FastAPI(title="Supply Chain Intelligence Agent API")

# Allow React frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────

DEFAULT_BIZ = "demo-business-001"

@app.get("/api/businesses")
def get_businesses():
    """List all registered businesses."""
    return {"businesses": list_businesses()}

@app.get("/api/status")
def status(business_id: str = Query(default=DEFAULT_BIZ)):
    try:
        biz = get_business(business_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "running", "business_id": business_id, **biz}

@app.post("/api/simulate")
async def simulate_disruption(business_id: str = Query(default=DEFAULT_BIZ)):
    try:
        get_business(business_id)  # validate early
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    state = _get_sim_state(business_id)

    if state.lock.locked():
        raise HTTPException(status_code=409, detail="A simulation is already running for this business. Wait for it to complete.")

    async with state.lock:
        state.is_running = True
        state.live_log = []
        try:
            result = await run_agent_cycle_async(
                business_id=business_id,
                log_callback=lambda msg: state.live_log.append(msg),
            )
            if not result or result.get("error"):
                return {
                    "success": False,
                    "error": result.get("error", "Agent did not complete. This is usually a Gemini quota issue. Wait 1 minute and try again.") if result else "Agent did not complete. This is usually a Gemini quota issue. Wait 1 minute and try again.",
                    **({"raw_response": result.get("raw_response")} if result and result.get("raw_response") else {}),
                }
            state.last_result = result
            try:
                await _asyncio.to_thread(_persist_alert_if_new, result, business_id)
            except Exception as _persist_exc:
                print(f"[PERSIST] Warning: alert persistence failed: {_persist_exc}")
            return {
                "success": True,
                "business_id": business_id,
                "disruption": result.get("disruption", {}),
                "exposure": result.get("exposure_usd", result.get("exposure", 0)),
                "severity_score": result.get("severity_score", 0),
                "top_supplier": result.get("top_supplier", {}),
                "purchase_order": result.get("purchase_order", ""),
                "customer_email": result.get(
                    "owner_email",
                    result.get("customer_email", ""),
                ),
                "raw": result,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            state.is_running = False

@app.get("/api/live-log")
def get_live_log(business_id: str = Query(default=DEFAULT_BIZ)):
    state = _get_sim_state(business_id)
    return {"logs": list(state.live_log), "running": state.is_running}

@app.get("/api/live-log/stream")
async def stream_live_log(business_id: str = Query(default=DEFAULT_BIZ)):
    """SSE endpoint — pushes log lines to the client as they appear."""
    state = _get_sim_state(business_id)

    async def event_generator():
        import asyncio
        last_count = 0
        while True:
            current = list(state.live_log)
            if len(current) > last_count:
                for line in current[last_count:]:
                    yield f"data: {json.dumps({'log': line})}\n\n"
                last_count = len(current)
            if not state.is_running and last_count >= len(current):
                yield f"data: {json.dumps({'done': True})}\n\n"
                break
            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.get("/api/trace")
def get_trace(business_id: str = Query(default=DEFAULT_BIZ)):
    state = _get_sim_state(business_id)
    return {"trace": state.last_result, "business_id": business_id}

@app.get("/api/alerts")
def get_alerts(
    business_id: str = Query(default=DEFAULT_BIZ),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """Returns past agent alerts from BigQuery with pagination support."""
    try:
        rows = run_query_safe("""
            SELECT
                al.id, al.business_id, al.severity_score, al.exposure_usd,
                al.status, CAST(al.created_at AS STRING) as created_at,
                (SELECT ROUND(AVG(
                    (COALESCE(c.relevance_score, 0.85)
                     + COALESCE(c.helpfulness_score, 0.85)
                     + COALESCE(c.reasoning_score, 0.85)
                     + (1 - COALESCE(c.hallucination_score, 0.1))) / 4
                ), 2)
                 FROM `akshxnsh-supplychain.supply_chain.agent_calibration` c
                 WHERE c.region = al.business_id
                   AND c.calibration_applied = TRUE
                 LIMIT 1) AS calibration_confidence
            FROM `akshxnsh-supplychain.supply_chain.agent_alerts` al
            WHERE al.business_id = @business_id
            ORDER BY al.created_at DESC
            LIMIT @limit OFFSET @offset
        """, [
            _bq.ScalarQueryParameter("business_id", "STRING", business_id),
            _bq.ScalarQueryParameter("limit",        "INT64",  limit),
            _bq.ScalarQueryParameter("offset",       "INT64",  offset),
        ])
        return {"alerts": rows, "limit": limit, "offset": offset}
    except Exception as e:
        return {"alerts": [], "error": str(e)}

@app.get("/api/alerts/all")
def get_all_alerts(limit: int = Query(default=20, ge=1, le=100)):
    """Aggregate alerts across all registered businesses, ordered by severity."""
    try:
        rows = run_query_safe("""
            SELECT id, business_id, severity_score, exposure_usd,
                   status, CAST(created_at AS STRING) as created_at
            FROM `akshxnsh-supplychain.supply_chain.agent_alerts`
            ORDER BY severity_score DESC, created_at DESC
            LIMIT @limit
        """, [_bq.ScalarQueryParameter("limit", "INT64", limit)])
        total_exposure = sum(r.get("exposure_usd") or 0 for r in rows)
        return {"alerts": rows, "total_exposure": total_exposure, "count": len(rows)}
    except Exception as e:
        return {"alerts": [], "error": str(e)}

@app.post("/api/alerts/{alert_id}/acknowledge")
def acknowledge_alert_endpoint(alert_id: str):
    from src.ingestion.bq_client import acknowledge_alert
    try:
        acknowledge_alert(alert_id)
        return {"success": True, "alert_id": alert_id, "status": "acknowledged"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/suppliers")
def get_suppliers(business_id: str = Query(default=DEFAULT_BIZ)):
    """Returns the current supplier list with risk signals for the given business."""
    try:
        rows = run_query_safe("""
            SELECT
                bs.supplier_name,
                bs.country,
                bs.product_category,
                bs.annual_spend_usd,
                (SELECT COUNT(*) - 1
                 FROM `akshxnsh-supplychain.supply_chain.business_suppliers`
                 WHERE business_id = @business_id
                   AND product_category = bs.product_category) AS other_suppliers_count,
                (SELECT ROUND(AVG(delay_days), 1)
                 FROM `akshxnsh-supplychain.supply_chain.completed_orders`
                 WHERE supplier_id = bs.id
                   AND status = 'delivered') AS avg_delay_days
            FROM `akshxnsh-supplychain.supply_chain.business_suppliers` bs
            WHERE bs.business_id = @business_id
        """, [_bq.ScalarQueryParameter("business_id", "STRING", business_id)])
        return {"suppliers": rows}
    except Exception as e:
        return {"suppliers": [], "error": str(e)}

# ── Manual PO Generation (user-selected supplier override) ────────────────────

class GeneratePORequest(BaseModel):
    supplier_name: str
    supplier_country: str
    product: str
    quantity: int
    unit_price: float
    required_by: str

@app.post("/api/generate-po")
def generate_po(req: GeneratePORequest):
    """
    Generate a Purchase Order for a specific supplier.
    Called when the user selects an alternative supplier other than the AI's top pick.
    """
    try:
        result = generate_purchase_order(
            supplier_name=req.supplier_name,
            supplier_country=req.supplier_country,
            product=req.product,
            quantity=req.quantity,
            unit_price=req.unit_price,
            required_by=req.required_by,
        )
        return {"success": True, **json.loads(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}

class ApproveActionRequest(BaseModel):
    supplier_name: str
    purchase_order: str
    owner_email: str

@app.post("/api/approve-action")
def approve_action(req: ApproveActionRequest, business_id: str = Query(default=DEFAULT_BIZ)):
    from datetime import datetime, timezone
    from src.ingestion.bq_client import save_calibration_approval, update_calibration_outcomes
    approved_at = datetime.now(timezone.utc).isoformat()
    try:
        save_calibration_approval(
            business_id=business_id,
            supplier_name=req.supplier_name,
            approved=True,
        )
    except Exception as e:
        print(f"[APPROVAL] Warning: could not persist to BigQuery: {e}")

    # Run outcome calibration in the background so the response returns immediately.
    # update_calibration_outcomes() processes all approved records that are 30+ days
    # old — it is idempotent and safe to call after every approval.
    def _run_calibration():
        try:
            update_calibration_outcomes()
        except Exception as exc:
            print(f"[CALIBRATION] Background outcome update failed: {exc}")

    threading.Thread(target=_run_calibration, daemon=True).start()

    return {
        "success": True,
        "approved_at": approved_at,
        "business_id": business_id,
        "supplier_name": req.supplier_name,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.dashboard.api:app", host="0.0.0.0",
                port=8000, reload=True)
