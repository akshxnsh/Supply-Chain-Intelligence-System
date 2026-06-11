import os
from dotenv import load_dotenv
from google.adk.agents import LlmAgent

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENROUTER_API_KEY")
os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"

agent = LlmAgent(
    name="TestAgent",
    model="openai/meta-llama/llama-3.3-70b-instruct",
    instruction="Answer briefly.",
)

print(agent)