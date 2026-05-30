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
You are a supply chain disruption agent for Lone Star Roofing Supply.
business_id = 'demo-business-001'

Run these steps IN ORDER, one tool per turn:
1. get_recent_disruptions(hours=24)
2. get_business_suppliers(business_id='demo-business-001')
3. get_pending_orders(business_id='demo-business-001')
4. calculate_exposure with the order values from step 3, delay_days=7
5. search_alternative_suppliers(product_category='roofing_materials', exclude_country='USA')
6. score_suppliers with the candidates from step 5
7. generate_purchase_order for the top scored supplier
8. generate_customer_email for affected customers
9. Return ONLY this JSON, nothing else:
{
  "disruption": {"headline": "...", "location_name": "..."},
  "exposure": <use at_risk_usd value here, NOT estimated_revenue_loss>,
  "top_supplier": {"name": "...", "country": "..."},
  "purchase_order": "...",
  "customer_email": "...",
  "severity_score": <number>
}
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
    """Run one full agent cycle with multi-turn tool calling."""

    with tracer.start_as_current_span("agent_cycle") as span:
        span.set_attribute("business_id", business_id)
        span.set_attribute("model", MODEL)
        span.set_attribute("cycle_start", datetime.utcnow().isoformat())

        print(f"\n{'='*60}")
        print(f"🤖 Agent cycle starting — {datetime.utcnow().strftime('%H:%M:%S')}")
        print(f"{'='*60}")

        messages = [{"role": "user",
                     "parts": [{"text": SYSTEM_PROMPT}]}]

        # Multi-turn tool calling loop
        max_turns = 15
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