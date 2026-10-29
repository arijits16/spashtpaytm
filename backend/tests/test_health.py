"""Health endpoint contract (build plan section 8.1)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import health as health_module


def test_health_returns_the_documented_shape(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"status", "db", "sarvam", "version", "env", "demoMode"}
    assert body["status"] in {"ok", "degraded"}
    assert body["sarvam"] in {"configured", "demo"}
    assert body["version"]


def test_health_reports_degraded_when_the_db_is_down(
    client: TestClient, monkeypatch: object
) -> None:
    """A dead database must still return 200 so the UI can show a precise banner."""
    monkeypatch.setattr(health_module, "check_db", lambda: (False, "OperationalError"))

    body = client.get("/api/health").json()

    assert body["status"] == "degraded"
    assert body["db"] == "error: OperationalError"


def test_health_leaks_no_secrets(client: TestClient) -> None:
    """The payload says whether Sarvam is configured, never the key itself."""
    text = client.get("/api/health").text

    assert "sk-" not in text
    assert "api-subscription-key" not in text
