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
You are an autonomous supply chain disruption intelligence agent for
Lone Star Roofing Supply (business_id: demo-business-001).

Every cycle you MUST follow these exact steps in order:
1. Call get_recent_disruptions to fetch events from the last 24 hours.
2. Call get_business_suppliers for business_id='demo-business-001'.
3. Check if any supplier's country or port is affected by the disruptions.
4. If a match is found, call get_pending_orders for 'demo-business-001'.
5. Call calculate_exposure with the at-risk order values and delay estimate.
6. If exposure > 5000, call search_alternative_suppliers for the affected
   product category, excluding the disrupted country.
7. Call score_suppliers on the results to rank the top 3.
8. Call generate_purchase_order for the top-ranked supplier.
9. Call generate_customer_email for affected customers.
10. Return a JSON summary with keys: disruption, exposure, top_supplier,
    purchase_order, customer_email, severity_score.

Never skip steps. Always complete the full pipeline.
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

            candidate = response.candidates[0]
            content   = candidate.content

            # Add assistant response to message history
            messages.append({
                "role": "model",
                "parts": [part.__dict__ for part in content.parts]
            })

            # Check for tool calls
            tool_calls = [p for p in content.parts if hasattr(p, 'function_call')
                         and p.function_call is not None]

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
                # No tool calls — agent has finished reasoning
                text_parts = [p.text for p in content.parts
                              if hasattr(p, 'text') and p.text]
                final_text = " ".join(text_parts)
                print(f"\n📋 Agent final response received ({len(final_text)} chars)")

                # Try to parse JSON from response
                try:
                    start = final_text.find("{")
                    end   = final_text.rfind("}") + 1
                    if start >= 0 and end > start:
                        final_result = json.loads(final_text[start:end])
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