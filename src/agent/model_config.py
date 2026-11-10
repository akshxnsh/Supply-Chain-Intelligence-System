import os

def configure_llm_provider() -> None:
    """
    Configure OpenRouter when available.
    Falls back to Gemini automatically.
    """
    if os.getenv("OPENROUTER_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["OPENROUTER_API_KEY"]
        os.environ["OPENAI_BASE_URL"] = "https://openrouter.ai/api/v1"


def _model(*names: str, default: str) -> str:
    """First non-empty env var among names, else default."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value.removeprefix("models/")
    return default


# Reader: runs many times (batched), so a cheap high-quota model. (gemini-2.5-flash-lite is closed to new users since late 2026.)
READER_MODEL = _model("READER_MODEL", "MODEL_NAME", default="gemini-3.5-flash-lite")
# Judge: runs rarely, so a stronger model (severity + recommended action).
JUDGE_MODEL = _model("JUDGE_MODEL", "MODEL_NAME", default="gemini-2.5-flash")
