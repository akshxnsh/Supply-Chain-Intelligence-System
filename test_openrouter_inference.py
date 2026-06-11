# test_openrouter_inference.py

import os
import asyncio

from dotenv import load_dotenv

load_dotenv()

from src.agent.model_config import configure_llm_provider
configure_llm_provider()

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

agent = LlmAgent(
    name="TestAgent",
    model="openai/meta-llama/llama-3.3-70b-instruct",
    instruction="Answer briefly."
)

async def main():
    session_service = InMemorySessionService()

    await session_service.create_session(
        app_name="test",
        user_id="user",
        session_id="session"
    )

    runner = Runner(
        agent=agent,
        app_name="test",
        session_service=session_service,
    )

    async for event in runner.run_async(
        user_id="user",
        session_id="session",
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="Say hello in five words")]
        )
    ):
        if event.content:
            print(event.content)

asyncio.run(main())