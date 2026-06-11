# test_openrouter_call.py

import asyncio
from dotenv import load_dotenv

load_dotenv()

from src.agent.model_config import configure_llm_provider
configure_llm_provider()

from google.adk.agents import LlmAgent

agent = LlmAgent(
    name="TestAgent",
    model="openai/meta-llama/llama-3.3-70b-instruct",
    instruction="Answer in one short sentence."
)

print("Agent created successfully")