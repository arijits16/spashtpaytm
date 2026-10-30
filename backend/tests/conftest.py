"""Shared pytest fixtures.

Auth tests mock the **token verifier** (`app.deps.verify_id_token`) rather than
the `current_user` dependency, so the real chain still runs: verify -> upsert ->
commit -> route. That is what the phase-1 acceptance criterion asks for.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import deps
from app.auth.firebase import TokenError, VerifiedToken
from app.config import Settings, get_settings
from app.db.session import SessionLocal, engine
from app.main import create_app

# Any test user gets a `test:` or `demo:` uid prefix so cleanup is unambiguous.
TEST_UID_PREFIXES = ("test:", "demo:")

# Cleanup has to get past the append-only triggers (migration 0004), which is
# the whole point of them: not even a fixture may delete evidence row by row.
# `session_replication_role = replica` suspends user triggers for this session
# only, which is the standard Postgres escape hatch and is exactly how a
# restore works. It is scoped to the test connection and to dev databases.
APPEND_ONLY_TABLES = ("receipts", "consents", "audit_log", "teachback_attempts")


def purge_test_rows(conn: object) -> None:
    """Delete everything created by tests, triggers temporarily suspended."""
    conn.execute(text("SET session_replication_role = replica"))
    try:
        for prefix in TEST_UID_PREFIXES:
            conn.execute(text("DELETE FROM users WHERE firebase_uid LIKE :p"), {"p": f"{prefix}%"})
    finally:
        conn.execute(text("SET session_replication_role = DEFAULT"))


def make_token(
    uid: str = "test:alice",
    email: str | None = "alice@example.com",
    name: str | None = "Alice A.",
    picture: str | None = "https://example.invalid/a.jpg",
    email_verified: bool = True,
) -> VerifiedToken:
    """Build a VerifiedToken as if Firebase had already validated it."""
    return VerifiedToken(
        uid=uid, email=email, name=name, picture=picture, email_verified=email_verified
    )


@pytest.fixture()
def client() -> Iterator[TestClient]:
    """A TestClient over a fresh app (runs lifespan startup/shutdown)."""
    with TestClient(create_app()) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_users() -> Iterator[None]:
    """Delete rows created by tests, so they cannot leak into one another."""
    yield
    with engine.begin() as conn:
        purge_test_rows(conn)


@pytest.fixture(autouse=True)
def _no_live_ai(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the test suite off the network.

    A developer with `SARVAM_API_KEY` set would otherwise have the journey
    tests making real LLM calls: slow, non-deterministic, and billed. Worse,
    the suite would pass or fail depending on what a model happened to say, so
    it would stop being evidence about *our* code.

    Forcing demo mode means the rules-and-templates path is what gets tested,
    which is also the path the golden path uses (§10.6). Tests that want the AI
    layer exercise it directly with a fake client.
    """
    monkeypatch.setattr("app.ai.sarvam_client.demo_mode_active", lambda _settings: True)
    monkeypatch.setattr("app.journey.understand.demo_mode_active", lambda _settings: True)
    monkeypatch.setattr("app.journey.polish.demo_mode_active", lambda _settings: True)
    monkeypatch.setattr("app.voice.turns.demo_mode_active", lambda _settings: True)
    monkeypatch.setattr("app.api.rescue.demo_mode_active", lambda _settings: True)
    yield


@pytest.fixture(autouse=True)
def _no_rescue_loop(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep the rescue agent's background loop out of the suite.

    `create_app`'s lifespan starts it, and a loop ticking against the same
    database would raise tasks underneath assertions that counted them - and
    mark test journeys abandoned while a test was still using them.
    """
    import app.main as main_module

    monkeypatch.setattr(
        main_module,
        "settings",
        main_module.settings.model_copy(update={"rescue_agent_enabled": False}),
    )
    yield


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Stop the cached settings singleton leaking between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def db() -> Iterator[Session]:
    """A plain session for asserting what actually landed in the database."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def mock_verifier(monkeypatch: pytest.MonkeyPatch) -> Callable[[VerifiedToken], None]:
    """Install a fake token verifier.

    Returns a function the test calls with the token that `Bearer good-token`
    should resolve to. Any other bearer value raises `TokenError`, so the
    rejection path is exercised too.
    """

    def _install(token: VerifiedToken) -> None:
        def _fake(raw: str, settings: Settings) -> VerifiedToken:
            if raw == "good-token":
                return token
            raise TokenError("invalid id token")

        monkeypatch.setattr(deps, "verify_id_token", _fake)

    return _install


@pytest.fixture()
def settings_factory() -> Callable[..., Settings]:
    """Build Settings from explicit values, ignoring any local .env."""

    def _make(**overrides: object) -> Settings:
        return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]

    return _make
