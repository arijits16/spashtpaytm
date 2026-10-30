"""Contract fixtures shared with the iPhone app and the website (section 8.5).

Two modes, one body of code:

* ``SPASHT_WRITE_CONTRACTS=1`` (what ``make contracts`` sets) regenerates
  ``contracts/fixtures/*.json`` from the live FastAPI app.
* any other run **verifies** that each committed fixture still has exactly the
  field structure the backend produces today.

The verification is what earns the folder its keep. Three codebases decode these
shapes; renaming a field in Pydantic and forgetting the Swift model is the
easiest way to break the demo, and it fails here instead.

Only the *structure* is compared, not the values: ids and timestamps change every
run, and a fixture that re-diffed on every regeneration would train everyone to
ignore it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.firebase import VerifiedToken

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"

WRITE_MODE = os.environ.get("SPASHT_WRITE_CONTRACTS") == "1"

# Fields whose value is different on every request. Replaced with a placeholder
# so the committed fixture is stable and reviewable.
_PLACEHOLDERS: dict[str, Any] = {
    "requestId": "00000000000000ff",
}


def _stabilise(value: Any) -> Any:
    """Recursively replace per-request values with fixed placeholders."""
    if isinstance(value, dict):
        return {
            key: _PLACEHOLDERS[key] if key in _PLACEHOLDERS else _stabilise(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_stabilise(item) for item in value]
    return value


def _shape(value: Any, path: str = "") -> dict[str, str]:
    """Flatten a JSON value into `path -> type name` pairs.

    Comparing this instead of the raw JSON means a fixture fails on a renamed,
    added, removed or retyped field, and passes when only a value moved.
    """
    if isinstance(value, dict):
        shape: dict[str, str] = {}
        for key, item in value.items():
            shape.update(_shape(item, f"{path}.{key}" if path else key))
        return shape
    if isinstance(value, list):
        # Element 0 only: the API never returns heterogeneous arrays, and
        # indexing every element would make the shape depend on list length.
        return _shape(value[0], f"{path}[]") if value else {f"{path}[]": "empty"}
    return {path: type(value).__name__}


def _check(name: str, payload: dict[str, Any]) -> None:
    """Write or verify one fixture."""
    stable = _stabilise(payload)
    path = FIXTURE_DIR / f"{name}.json"

    if WRITE_MODE:
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(stable, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return

    if not path.is_file():
        pytest.fail(f"contracts/fixtures/{name}.json is missing. Run `make contracts`.")

    committed = json.loads(path.read_text(encoding="utf-8"))
    expected, actual = _shape(committed), _shape(stable)

    if expected != actual:
        added = sorted(set(actual) - set(expected))
        removed = sorted(set(expected) - set(actual))
        retyped = sorted(
            f"{key}: {expected[key]} -> {actual[key]}"
            for key in set(expected) & set(actual)
            if expected[key] != actual[key]
        )
        pytest.fail(
            f"contracts/fixtures/{name}.json is out of date.\n"
            f"  added:   {added}\n"
            f"  removed: {removed}\n"
            f"  retyped: {retyped}\n"
            "Run `make contracts`, then update the iOS Codable models "
            "(ios/SpashtPaytm/Core/Networking/Models) and the website types "
            "(frontend/src/lib/types.ts) in the same commit."
        )


# --- the fixtures ------------------------------------------------------------


def test_contract_health(client: TestClient) -> None:
    """`GET /api/health` - what the app's first screen decodes."""
    response = client.get("/api/health")

    assert response.status_code == 200
    _check("health", response.json())


def test_contract_me(client: TestClient, mock_verifier: Callable[[VerifiedToken], None]) -> None:
    """`GET /api/me` - the signed-in profile both clients render."""
    mock_verifier(
        VerifiedToken(
            uid="test:contract",
            email="contract@example.invalid",
            name="Contract Example",
            picture="https://example.invalid/photo.jpg",
            email_verified=True,
        )
    )

    response = client.get("/api/me", headers={"Authorization": "Bearer good-token"})

    assert response.status_code == 200
    _check("me", response.json())


def test_contract_error_not_found(client: TestClient) -> None:
    """The standard error envelope (section 8.1), as every client must parse it."""
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    _check("error_not_found", response.json())


def test_contract_error_unauthorized(client: TestClient) -> None:
    """401 is the error both clients must handle specially: sign out and retry."""
    response = client.get("/api/me")

    assert response.status_code == 401
    _check("error_unauthorized", response.json())
