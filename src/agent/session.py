import os

from google.adk.sessions import InMemorySessionService


def create_session_service():
    """Create the configured ADK-native session service."""
    database_url = os.getenv("ADK_SESSION_DB_URL")
    if not database_url:
        return InMemorySessionService()
    if database_url.startswith("sqlite:///"):
        database_url = database_url.replace(
            "sqlite:///",
            "sqlite+aiosqlite:///",
            1,
        )

    try:
        from google.adk.sessions import DatabaseSessionService
    except ImportError as exc:
        raise RuntimeError(
            "ADK_SESSION_DB_URL is set but the ADK database extra is unavailable."
        ) from exc
    return DatabaseSessionService(db_url=database_url)
