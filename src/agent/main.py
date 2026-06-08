import asyncio
import json
import os
import sys

from dotenv import load_dotenv

from src.agent.runtime import run_agent_cycle_async


load_dotenv()


def validate_environment() -> None:
    required = ["GEMINI_API_KEY"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise RuntimeError(f"Missing environment variables: {missing}")


async def test_first_trace() -> dict:
    """Run a real ADK invocation so Phoenix receives agent and tool spans."""
    validate_environment()
    result = await run_agent_cycle_async()
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    try:
        asyncio.run(test_first_trace())
    except Exception as exc:
        print(f"ADK smoke test failed: {exc}")
        sys.exit(1)
