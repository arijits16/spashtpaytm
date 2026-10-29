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
        for prefix in TEST_UID_PREFIXES:
            conn.execute(text("DELETE FROM users WHERE firebase_uid LIKE :p"), {"p": f"{prefix}%"})


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
