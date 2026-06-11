import os

def configure_llm_provider() -> None:
    """
    Configure OpenRouter when available.
    Falls back to Gemini automatically.
    """
    if os.getenv("OPENROUTER_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
        os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"