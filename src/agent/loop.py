import os, json, time, uuid
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from phoenix.otel import register
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor
from src.agent.tools import TOOL_DEFINITIONS, TOOL_HANDLERS
from src.ingestion.bq_client import save_alert

load_dotenv()

# ── Arize Phoenix Setup ───────────────────────────────────────────────────────
tracer_provider = register(
    project_name="supply-chain-agent",
    endpoint="https://app.phoenix.arize.com/s/singhamiya9/v1/traces",
    headers={"Authorization": f"Bearer {os.environ['PHOENIX_API_KEY']}"},
)
GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
tracer = tracer_provider.get_tracer("supply-chain-agent")

# ── Gemini Setup ──────────────────────────────────────────────────────────────
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL  = os.getenv("MODEL_NAME", "models/gemini-2.5-flash")

SYSTEM_PROMPT = """
You are an AI supply chain disruption detection and mitigation agent for Lone Star Roofing Supply.
business_id = 'demo-business-001'

Your role: Synthesize multiple signal sources to detect supply chain disruptions BEFORE they impact the business.

CRITICAL: Multi-Signal Detection Algorithm
────────────────────────────────────────────
1. DETECT DISRUPTIONS using all signal layers:
   • Call detect_disruptions() to get all affected suppliers
   • This tool cross-references disruption_events + weather_alerts + port_activity + tariff_updates
   
2. CALCULATE ACTUAL IMPACT on pending orders:
   • Extract affected_supplier_ids from Step 1
   • Call calculate_impact(business_id, affected_supplier_ids, disruption_date)
   • Only orders with eta_date within 30 days count as at-risk
   • Output: exposure_usd, affected_orders count, expected_loss_usd
   
3. GET CALIBRATION BASELINE (historical accuracy):
   • Call query_calibration_baseline(event_type, region)
   • Returns: weighted_baseline_severity, confidence_score (180-day half-life)
   • This makes your severity scores shift measurably as real outcomes accumulate
   
4. DETECT BLACK SWAN ANOMALIES:
   • Gather all signals: disruption_events, weather_alerts, port_activity
   • Call detect_black_swan() to compute z-scores
   • If 2+ signals exceed 2.5σ → ANOMALY DETECTED
   • Anomalies bypass normal thresholds, require mandatory human review
   
5. DECIDE: FIRE ALERT & CALCULATE SEVERITY?
   • IF ANY shipment is affected (affected_orders > 0) → ALWAYS FIRE ALERT, irrespective of the exposure amount.
   • IF NO shipment is affected AND NO financial impact → skip alert.
   • STATE EXPECTED LOSS: Call out the predicted financial loss if an alternate supplier is not chosen.
   • CALCULATE SEVERITY SCORE based on inventory and predicted loss:
     - CRITICAL (8.0 - 10.0): User does NOT have inventory to fulfill pending orders, shipment is delayed, and expected loss is high. The user MUST choose another supplier to fulfill the orders.
     - MODERATE (4.0 - 7.9): Pending orders are covered by existing inventory. Shipment is delayed but no immediate stockout. Severity reflects minor delay costs or tariff hits.
   
6. IF ALERT FIRES, RECOMMEND MITIGATION:
   • Call search_alternative_suppliers(product_category, exclude_country)
   • Call score_suppliers() with ALL candidates (not just top 1). Get top 3.
   • For EACH of the 3 ranked alternatives, compute the following tradeoffs vs the primary supplier:
       - unit_price_difference_usd: alt.unit_price_usd - primary_unit_price_usd (from pending_orders.primary_unit_price_usd)
       - total_cost_premium_usd: unit_price_difference_usd × total disrupted quantity
       - lead_time_days: from alternative supplier record
       - dynamic_reliability_score: as returned by score_suppliers()
       - on_time_rate: as returned by score_suppliers()
       - avg_review_rating: as returned by score_suppliers()
       - completed_orders_count: how many historical orders with this supplier
   • Build suggested_alternatives array with all 3 ranked suppliers and their tradeoffs
   • Default PO: Call generate_purchase_order() for the TOP-ranked supplier only
     - quantity: max(ceil(inventory_deficit / unit_price), supplier_moq)
     - unit_price: alt supplier's unit_price_usd
   • Call generate_owner_email() with full disruption context + list of all 3 alternatives
   
7. RETURN FINAL SUMMARY with keys:
   - alert_fired (boolean)
   - disruption (event summary)
   - signals_detected (which signals triggered)
   - exposure_usd (calculated impact)
   - expected_loss_usd (predicted loss if alternate supplier is not chosen)
   - affected_suppliers (list)
   - severity_score (calibration-adjusted, factoring inventory & predicted loss)
   - calibration_confidence (how confident are we?)
   - black_swan_detected (yes/no)
   - suggested_alternatives: array of up to 3 objects, each containing:
       {
         "rank": 1/2/3,
         "supplier_id": "...",
         "name": "...",
         "country": "...",
         "unit_price_usd": <alt price>,
         "unit_price_difference_usd": <alt - primary, positive means more expensive>,
         "total_cost_premium_usd": <unit_price_difference * total disrupted qty>,
         "lead_time_days": <int>,
         "dynamic_reliability_score": <0-10>,
         "on_time_rate": <0.0-1.0 or null>,
         "avg_review_rating": <1-5 or null>,
         "completed_orders_count": <int>,
         "total_score": <weighted composite 0-10>,
         "tradeoff_summary": "e.g. $0.01/unit cheaper than primary but 3 days longer lead time. 100% on-time delivery across 2 historical orders."
       }
   - top_supplier (name of rank-1 recommended supplier)
   - purchase_order (drafted for top_supplier, based on MOQ and deficit)
   - owner_email (includes full suggested_alternatives list)

CALIBRATION NOTE:
────────────────
Before making severity judgments, query calibration_baseline to see how this event type typically manifests.
If actual_delay_days from past events differ significantly from severity_scored, adjust your current assessment.
Deviation > 0.2 from baseline requires explanation in your reasoning.

BLACK SWAN MODE (If Anomaly Detected):
──────────────────────────────────────
• Suspend normal calibration weighting (too many unknowns)
• Set approval threshold to zero (escalate to human)
• Flag all outputs as requiring mandatory review
• Disable automated PO generation (human must approve)

Never skip steps. Always synthesize all available signals. Prioritize impact-based decisions over event-based reactions.
"""


def handle_tool_call(tool_name: str, tool_args: dict) -> str:
    """Execute a tool call and return the result as a string."""
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        return handler(**tool_args)
    except Exception as e:
        return json.dumps({"error": str(e)})

def run_agent_cycle(business_id: str = "demo-business-001") -> dict | None:
    """Run one full agent cycle with multi-signal disruption detection."""

    with tracer.start_as_current_span("agent_cycle") as span:
        span.set_attribute("business_id", business_id)
        span.set_attribute("model", MODEL)
        span.set_attribute("cycle_start", datetime.utcnow().isoformat())

        print(f"\n{'='*60}")
        print(f"🤖 Agent cycle starting (Multi-Signal Detection) — {datetime.utcnow().strftime('%H:%M:%S')}")
        print(f"{'='*60}")

        messages = [{"role": "user",
                     "parts": [{"text": SYSTEM_PROMPT}]}]

        # Multi-turn tool calling loop
        max_turns = 20  # Increased from 15 for additional signal processing
        turn = 0
        final_result = None

        while turn < max_turns:
            turn += 1
            print(f"\n🔄 Turn {turn}...")

            response = client.models.generate_content(
                model=MODEL,
                contents=messages,
                config=types.GenerateContentConfig(
                    tools=[TOOL_DEFINITIONS],
                    temperature=0.1,
                )
            )

            # Guard against empty responses
            if not response.candidates:
                print("  ⚠️ Empty candidates — retrying turn")
                continue

            candidate = response.candidates[0]
            content   = candidate.content

            if content is None or not hasattr(content, 'parts') or not content.parts:
                print("  ⚠️ Empty content — agent finished early")
                # Try to extract any text from the last response
                final_result = {"raw_response": "Agent completed pipeline"}
                break

            # Add assistant response to message history
            messages.append({
                "role": "model",
                "parts": [part.__dict__ for part in content.parts]
            })

            # Check for tool calls
            tool_calls = []
            for p in content.parts:
                try:
                    if hasattr(p, 'function_call') and p.function_call is not None:
                        if hasattr(p.function_call, 'name') and p.function_call.name:
                            tool_calls.append(p)
                except Exception:
                    pass

            if tool_calls:
                tool_results = []
                for part in tool_calls:
                    fc   = part.function_call
                    name = fc.name
                    args = dict(fc.args) if fc.args else {}

                    print(f"  🔧 Tool call: {name}({args})")

                    with tracer.start_as_current_span(f"tool_{name}") as tool_span:
                        tool_span.set_attribute("tool.name", name)
                        tool_span.set_attribute("tool.args", json.dumps(args))
                        result = handle_tool_call(name, args)
                        tool_span.set_attribute("tool.result_length", len(result))

                    print(f"  ✅ {name} returned {len(result)} chars")
                    tool_results.append({
                        "function_response": {
                            "name": name,
                            "response": {"result": result}
                        }
                    })

                messages.append({"role": "user", "parts": tool_results})

            else:
                # No tool calls — agent finished
                text_parts = [p.text for p in content.parts
                              if hasattr(p, 'text') and p.text]
                final_text = " ".join(text_parts)
                print(f"\n📋 Agent final response ({len(final_text)} chars)")

                try:
                    start = final_text.find("{")
                    end   = final_text.rfind("}") + 1
                    if start >= 0 and end > start:
                        final_result = json.loads(final_text[start:end])
                    else:
                        final_result = {"raw_response": final_text}
                except Exception:
                    final_result = {"raw_response": final_text}

                span.set_attribute("turns_taken", turn)
                span.set_attribute("success", True)
                break

        return final_result

def run_loop():
    """Continuous 15-minute agent loop."""
    print("🚀 Supply Chain Agent starting...")
    while True:
        try:
            result = run_agent_cycle()
            if result:
                print(f"\n✅ Cycle complete. Result: {json.dumps(result, indent=2)}")
        except Exception as e:
            print(f"❌ Cycle error: {e}")
        print(f"\n⏳ Next cycle in 15 minutes...")
        time.sleep(900)

if __name__ == "__main__":
    # Run once for testing
    result = run_agent_cycle()
    if result:
        print(f"\n🎯 FINAL RESULT:\n{json.dumps(result, indent=2)}")