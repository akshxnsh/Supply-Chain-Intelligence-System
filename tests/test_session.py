from google.adk.sessions import InMemorySessionService

from src.agent.session import create_session_service


def test_session_service_defaults_to_adk_in_memory(monkeypatch):
    monkeypatch.delenv("ADK_SESSION_DB_URL", raising=False)

    assert isinstance(create_session_service(), InMemorySessionService)


def test_sqlite_session_url_is_normalized_to_async_driver(monkeypatch):
    captured = {}

    class FakeDatabaseSessionService:
        def __init__(self, db_url):
            captured["db_url"] = db_url

    monkeypatch.setenv("ADK_SESSION_DB_URL", "sqlite:///./sessions.db")
    monkeypatch.setattr(
        "google.adk.sessions.DatabaseSessionService",
        FakeDatabaseSessionService,
    )

    create_session_service()

    assert captured["db_url"] == "sqlite+aiosqlite:///./sessions.db"
