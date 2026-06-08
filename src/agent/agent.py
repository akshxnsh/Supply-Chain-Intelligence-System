"""ADK discovery module used by `adk web`, `adk run`, and deployments."""

from src.agent.agents import create_root_agent


root_agent = create_root_agent()
