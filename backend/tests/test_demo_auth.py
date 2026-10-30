"""Hardened demo authentication (build plan section 13.2, phase 1).

The demo path is what keeps the pitch alive when venue Wi-Fi dies, and during a
demo the API is reachable from the internet through the ngrok tunnel. So it is
tested as carefully as real auth: it works in dev with the right key, and is
refused in every other combination.

Four conditions must all hold. Each one gets a test that breaks exactly that
condition and nothing else.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models.user import User
from app.main import create_app
from app.security.demo_auth import DEMO_ADMIN, DemoAuthError, demo_token, verify_demo_key
from app.security.ratelimit import limiter

DEMO_KEY = "test-demo-key-0123456789abcdef"

CUSTOMER = {"X-Demo-User": "sunita", "X-Demo-Key": DEMO_KEY}
ADMIN = {"X-Demo-User": DEMO_ADMIN, "X-Demo-Key": DEMO_KEY}


def app_with_settings(**overrides: object) -> TestClient:
    """TestClient whose `get_settings` returns explicit values."""
    settings = Settings(_env_file=None, **overrides)  # type: ignore[call-arg]
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def demo_enabled(**overrides: object) -> TestClient:
    """An app with demo auth fully switched on."""
    return app_with_settings(demo_auth=True, app_env="dev", demo_auth_key=DEMO_KEY, **overrides)


@pytest.fixture(autouse=True)
def _reset_limiter() -> Iterator[None]:
    """Rate-limit buckets are process-wide; a leftover bucket fails later tests."""
    limiter.reset()
    yield
    limiter.reset()


# --- the happy path ----------------------------------------------------------


def test_demo_headers_sign_in_when_everything_is_right(db: Session) -> None:
    with demo_enabled() as c:
        response = c.get("/api/me", headers=CUSTOMER)

    assert response.status_code == 200
    body = response.json()
    assert body["displayName"] == "Sunita J."
    assert body["preferredLanguage"] == "mr-IN"
    assert body["session"] == "demo"
    assert body["persona"]["id"] == "sunita"
    assert db.scalar(select(User).where(User.firebase_uid == "demo:sunita")) is not None


def test_demo_admin_is_an_admin_and_has_no_persona() -> None:
    """`demo-admin` operates the dashboard, so it has no customer journey."""
    with demo_enabled(dashboard_admin_emails="demo-admin@spasht.invalid") as c:
        body = c.get("/api/me", headers=ADMIN).json()

    assert body["isAdmin"] is True
    assert body["persona"] is None


def test_demo_login_needs_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing in the demo path may call out to Firebase or Google."""
    import app.deps as deps_module

    def explode(*_: object, **__: object) -> None:
        raise AssertionError("the demo path must not verify a token")

    monkeypatch.setattr(deps_module, "verify_id_token", explode)

    with demo_enabled() as c:
        assert c.get("/api/me", headers=CUSTOMER).status_code == 200


def test_each_demo_identity_gets_its_own_user(db: Session) -> None:
    with demo_enabled() as c:
        for identity in ("sunita", "ramesh", "priya"):
            response = c.get("/api/me", headers={"X-Demo-User": identity, "X-Demo-Key": DEMO_KEY})
            assert response.status_code == 200

    uids = {f"demo:{identity}" for identity in ("sunita", "ramesh", "priya")}
    found = set(db.scalars(select(User.firebase_uid).where(User.firebase_uid.in_(uids))))
    assert found == uids


def test_an_unknown_identity_falls_back_to_the_default() -> None:
    with demo_enabled() as c:
        body = c.get("/api/me", headers={"X-Demo-User": "nobody", "X-Demo-Key": DEMO_KEY}).json()

    assert body["displayName"] == "Sunita J."


# --- each condition, broken on its own ---------------------------------------


def test_refused_without_the_key() -> None:
    """The header alone was enough in v1. It must not be now."""
    with demo_enabled() as c:
        response = c.get("/api/me", headers={"X-Demo-User": "sunita"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_refused_with_the_wrong_key() -> None:
    with demo_enabled() as c:
        response = c.get("/api/me", headers={"X-Demo-User": "sunita", "X-Demo-Key": "not-the-key"})

    assert response.status_code == 401


def test_refused_when_demo_auth_is_off() -> None:
    with app_with_settings(demo_auth=False, app_env="dev", demo_auth_key=DEMO_KEY) as c:
        assert c.get("/api/me", headers=CUSTOMER).status_code == 401


def test_refused_in_production() -> None:
    """Even with the right key and the switch on, prod must never honour it."""
    with app_with_settings(demo_auth=True, app_env="prod", demo_auth_key=DEMO_KEY) as c:
        assert c.get("/api/me", headers=CUSTOMER).status_code == 401


def test_refused_when_no_key_is_configured() -> None:
    """An empty configured key must not match an empty supplied key."""
    with app_with_settings(demo_auth=True, app_env="dev", demo_auth_key="") as c:
        response = c.get("/api/me", headers={"X-Demo-User": "sunita", "X-Demo-Key": ""})

    assert response.status_code == 401


# --- the refusal must not describe itself ------------------------------------


def test_every_refusal_gives_the_same_message() -> None:
    """Which condition failed is exactly what an attacker wants to learn."""
    messages = set()

    with demo_enabled() as c:
        messages.add(c.get("/api/me", headers={"X-Demo-User": "sunita"}).json()["error"]["message"])
        messages.add(
            c.get("/api/me", headers={"X-Demo-User": "sunita", "X-Demo-Key": "wrong"}).json()[
                "error"
            ]["message"]
        )
        messages.add(c.get("/api/me").json()["error"]["message"])

    with app_with_settings(demo_auth=True, app_env="prod", demo_auth_key=DEMO_KEY) as c:
        messages.add(c.get("/api/me", headers=CUSTOMER).json()["error"]["message"])

    assert len(messages) == 1


# --- rate limiting -----------------------------------------------------------


def test_demo_auth_is_rate_limited() -> None:
    """Guessing the key through the tunnel must not be fast."""
    bad = {"X-Demo-User": "sunita", "X-Demo-Key": "wrong"}

    with demo_enabled() as c:
        statuses = [c.get("/api/me", headers=bad).status_code for _ in range(80)]

    assert 429 in statuses, "the demo path should start refusing after ~60 attempts"


def test_the_rate_limit_response_says_when_to_retry() -> None:
    bad = {"X-Demo-User": "sunita", "X-Demo-Key": "wrong"}
    response = None

    with demo_enabled() as c:
        for _ in range(80):
            response = c.get("/api/me", headers=bad)
            if response.status_code == 429:
                break

    assert response is not None
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["Retry-After"]) >= 1


# --- the key comparison itself -----------------------------------------------


def test_verify_demo_key_accepts_the_configured_key() -> None:
    settings = Settings(_env_file=None, demo_auth=True, app_env="dev", demo_auth_key=DEMO_KEY)  # type: ignore[call-arg]
    verify_demo_key(DEMO_KEY, settings)  # must not raise


@pytest.mark.parametrize(
    ("supplied", "overrides"),
    [
        (None, {}),
        ("", {}),
        ("wrong", {}),
        (DEMO_KEY, {"demo_auth": False}),
        (DEMO_KEY, {"app_env": "prod"}),
        (DEMO_KEY, {"demo_auth_key": ""}),
    ],
)
def test_verify_demo_key_rejects_everything_else(
    supplied: str | None, overrides: dict[str, object]
) -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        **{"demo_auth": True, "app_env": "dev", "demo_auth_key": DEMO_KEY, **overrides},
    )
    with pytest.raises(DemoAuthError):
        verify_demo_key(supplied, settings)


def test_demo_uids_are_namespaced() -> None:
    """So a demo row can never collide with a real Firebase uid (D-015)."""
    assert demo_token("sunita").uid == "demo:sunita"
    assert demo_token(DEMO_ADMIN).uid == f"demo:{DEMO_ADMIN}"


def test_demo_emails_are_unroutable() -> None:
    """`.invalid` is reserved by RFC 2606, so these can never reach a person."""
    for identity in ("sunita", "ramesh", "priya", DEMO_ADMIN):
        email = demo_token(identity).email
        assert email is not None
        assert email.endswith(".invalid")
