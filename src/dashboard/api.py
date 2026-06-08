from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from src.agent.loop import run_agent_cycle
from src.agent.tools import generate_purchase_order
from src.agent.business_registry import list_businesses, get_business
from src.ingestion.bq_client import run_query
import asyncio as _asyncio

_live_log: list = []
_last_result: dict = {}
_is_running: bool = False

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
    global _live_log, _last_result, _is_running
    try:
        get_business(business_id)  # validate early
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    _is_running = True
    _live_log = []
    try:
        import asyncio, functools
        result = await asyncio.to_thread(
            functools.partial(run_agent_cycle, business_id=business_id, log_callback=lambda msg: _live_log.append(msg))
        )
        if not result:
            return {
                "success": False,
                "error": "Agent did not complete. This is usually a Gemini quota issue. Wait 1 minute and try again."
            }
        _last_result = result
        return {
            "success": True,
            "business_id": business_id,
            "disruption": result.get("disruption", {}),
            "exposure": result.get("exposure", 0),
            "severity_score": result.get("severity_score", 0),
            "top_supplier": result.get("top_supplier", {}),
            "purchase_order": result.get("purchase_order", ""),
            "customer_email": result.get("customer_email", ""),
            "raw": result,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        _is_running = False

@app.get("/api/live-log")
def get_live_log():
    global _live_log, _is_running
    return {"logs": list(_live_log), "running": _is_running}

@app.get("/api/trace")
def get_trace(business_id: str = Query(default=DEFAULT_BIZ)):
    global _last_result
    return {"trace": _last_result, "business_id": business_id}

@app.get("/api/alerts")
def get_alerts(business_id: str = Query(default=DEFAULT_BIZ)):
    """Returns past agent alerts from BigQuery for the given business."""
    try:
        rows = run_query(f"""
            SELECT id, business_id, severity_score, exposure_usd,
                   status, CAST(created_at AS STRING) as created_at
            FROM `akshxnsh-supplychain.supply_chain.agent_alerts`
            WHERE business_id = '{business_id}'
            ORDER BY created_at DESC
            LIMIT 10
        """)
        return {"alerts": rows}
    except Exception as e:
        return {"alerts": [], "error": str(e)}

@app.get("/api/suppliers")
def get_suppliers(business_id: str = Query(default=DEFAULT_BIZ)):
    """Returns the current supplier list for the given business."""
    try:
        rows = run_query(f"""
            SELECT supplier_name, country, product_category, annual_spend_usd
            FROM `akshxnsh-supplychain.supply_chain.business_suppliers`
            WHERE business_id = '{business_id}'
        """)
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
    from datetime import datetime as _dt
    approved_at = _dt.utcnow().isoformat() + "Z"
    print(f"[APPROVAL] {approved_at} | business={business_id} | supplier={req.supplier_name}")
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
