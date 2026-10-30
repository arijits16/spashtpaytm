"""The admin guard (`current_admin`).

The dashboard API itself lands in phase 8, so these tests mount the real
dependency on a throwaway route rather than inventing production surface. The
guard is what stands between a signed-in customer and the compliance dashboard,
so it is tested now, not when the dashboard arrives.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.deps import CurrentAdmin, CurrentUser
from app.main import create_app
from tests.conftest import make_token

AUTH = {"Authorization": "Bearer good-token"}


def guarded_app(**overrides: object) -> TestClient:
    """An app exposing one admin-only route and one merely-authenticated route."""
    settings = Settings(_env_file=None, **overrides)  # type: ignore[call-arg]
    app: FastAPI = create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    @app.get("/api/_test/admin-only")
    def admin_only(_: CurrentAdmin) -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/_test/any-user")
    def any_user(_: CurrentUser) -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_admin_route_allows_an_allowlisted_user(
    mock_verifier: Callable[..., None],
) -> None:
    mock_verifier(make_token(uid="test:boss", email="boss@example.com"))

    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        assert c.get("/api/_test/admin-only", headers=AUTH).status_code == 200


def test_admin_route_returns_403_for_a_signed_in_non_admin(
    mock_verifier: Callable[..., None],
) -> None:
    """403, not 401: they are authenticated, just not permitted."""
    mock_verifier(make_token(uid="test:alice", email="alice@example.com"))

    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        response = c.get("/api/_test/admin-only", headers=AUTH)

    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "forbidden"
    assert body["message"] == "Admin access required"


def test_admin_route_returns_401_with_no_credentials() -> None:
    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        assert c.get("/api/_test/admin-only").status_code == 401


def test_a_non_admin_still_reaches_ordinary_protected_routes(
    mock_verifier: Callable[..., None],
) -> None:
    """The guard must gate the dashboard, not the customer's own journey."""
    mock_verifier(make_token(uid="test:alice", email="alice@example.com"))

    with guarded_app(dashboard_admin_emails="boss@example.com") as c:
        assert c.get("/api/_test/any-user", headers=AUTH).status_code == 200


def test_a_demo_user_is_never_an_admin() -> None:
    """Demo auth is a convenience for the customer flow, not a way into the dashboard."""
    with guarded_app(demo_auth=True, app_env="dev", dashboard_admin_emails="boss@example.com") as c:
        assert c.get("/api/_test/any-user", headers={"X-Demo-User": "sunita"}).status_code == 200
        assert c.get("/api/_test/admin-only", headers={"X-Demo-User": "sunita"}).status_code == 403
