import os
import sys
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Validate required environment variables
REQUIRED_KEYS = ['GEMINI_API_KEY', 'PHOENIX_API_KEY', 'ARIZE_SPACE_ID']
missing = [k for k in REQUIRED_KEYS if not os.getenv(k)]
if missing:
    print(f"❌ Missing environment variables: {missing}")
    sys.exit(1)

print("✅ Environment variables loaded")

# ── Arize Phoenix Setup ──────────────────────────────────────────────────────
from phoenix.otel import register
from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

tracer_provider = register(
    project_name="supply-chain-agent",
    endpoint="https://app.phoenix.arize.com/s/singhamiya9/v1/traces",
    headers={
        "Authorization": f"Bearer {os.environ['PHOENIX_API_KEY']}",
    },
)

GoogleGenAIInstrumentor().instrument(tracer_provider=tracer_provider)
tracer = tracer_provider.get_tracer("supply-chain-agent")

print("✅ Arize Phoenix connected")

# ── Gemini Setup ─────────────────────────────────────────────────────────────
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = os.getenv("MODEL_NAME", "models/gemini-2.5-flash")

print(f"✅ Gemini client ready — model: {MODEL}")

# ── Test: Fire First Trace to Arize ──────────────────────────────────────────
def test_first_trace():
    with tracer.start_as_current_span("test_first_trace") as span:
        span.set_attribute("test", True)
        span.set_attribute("model", MODEL)
        span.set_attribute("purpose", "hackathon_setup_verification")

        print("\n🔄 Sending test request to Gemini...")

        response = client.models.generate_content(
            model=MODEL,
            contents="You are a supply chain intelligence agent. "
                     "In one sentence, describe what you do."
        )

        result = response.text
        span.set_attribute("response_length", len(result))
        span.set_attribute("success", True)

        print(f"\n✅ Gemini responded:\n{result}")
        print("\n✅ Trace sent to Arize Phoenix")
        print("👉 Check your Arize dashboard — look for project 'supply-chain-agent'")

        return result

if __name__ == "__main__":
    test_first_trace()