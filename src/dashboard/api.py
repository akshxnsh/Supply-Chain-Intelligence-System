from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from src.agent.loop import run_agent_cycle
from src.agent.tools import generate_purchase_order
from src.ingestion.bq_client import run_query

app = FastAPI(title="Supply Chain Intelligence Agent API")

# Allow React frontend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    return {
        "status": "running",
        "business": "Lone Star Roofing Supply",
        "business_id": "demo-business-001"
    }

@app.post("/api/simulate")
async def simulate_disruption():
    try:
        result = run_agent_cycle(business_id="demo-business-001")

        if not result:
            return {
                "success": False,
                "error": "Agent did not complete. This is usually a Gemini quota issue. Wait 1 minute and try again."
            }

        return {
            "success": True,
            "disruption": result.get("disruption", {}),
            "exposure": result.get("exposure", 0),
            "severity_score": result.get("severity_score", 0),
            "top_supplier": result.get("top_supplier", {}),
            "purchase_order": result.get("purchase_order", ""),
            "customer_email": result.get("customer_email", ""),
            "raw": result,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"{str(e)}"
        }

@app.get("/api/alerts")
def get_alerts():
    """Returns past agent alerts from BigQuery."""
    try:
        rows = run_query("""
            SELECT id, business_id, severity_score, exposure_usd,
                   status, CAST(created_at AS STRING) as created_at
            FROM `akshxnsh-supplychain.supply_chain.agent_alerts`
            ORDER BY created_at DESC
            LIMIT 10
        """)
        return {"alerts": rows}
    except Exception as e:
        return {"alerts": [], "error": str(e)}

@app.get("/api/suppliers")
def get_suppliers():
    """Returns the business's current supplier list."""
    try:
        rows = run_query("""
            SELECT supplier_name, country, product_category, annual_spend_usd
            FROM `akshxnsh-supplychain.supply_chain.business_suppliers`
            WHERE business_id = 'demo-business-001'
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
        import json
        return {"success": True, **json.loads(result)}
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.dashboard.api:app", host="0.0.0.0",
                port=8000, reload=True)