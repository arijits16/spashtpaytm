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
from app.config import settings
from app.security.ratelimit import limiter

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


# --- the journey: one fixture per golden-path step (§8.5) --------------------
#
# Generated by walking the real journey, so a fixture can never describe a
# screen the engine does not actually produce. The iOS and website tests decode
# every one of these, which is what keeps three codebases in step.


def test_contract_journey_steps(client: TestClient) -> None:
    """Walk the golden path, writing a fixture at each step."""
    from tests.test_journey import CORRECT_MARKERS, Walker

    limiter.reset()
    headers = {"X-Demo-User": "sunita", "X-Demo-Key": settings.demo_auth_key}
    walker = Walker(client, headers)

    _check("turn_intro", walker.start("mr-IN"))
    _check("turn_consent", walker.tap({"name": "amount", "amount": 50_000}))
    _check(
        "turn_prefill",
        walker.tap(
            {
                "name": "consents",
                "grants": {"fetch_digilocker": True, "fetch_account_aggregator": True},
            }
        ),
    )
    _check("turn_confirm", walker.say("हो"))

    offers = walker.tap({"name": "confirm_details"})
    _check("turn_offers", offers)

    cheapest = min(offers["card"]["data"]["offers"], key=lambda offer: offer["totalCost"])
    _check("turn_kfs", walker.tap({"name": "select_offer", "offerId": cheapest["offerId"]}))

    current = walker.say("हो")
    _check("turn_quiz", current)

    # A wrong answer, so the `result` field of the quiz card is in a fixture
    # too: clients have to render the incorrect state, not just the happy one.
    quiz = current["card"]["data"]
    markers = CORRECT_MARKERS[quiz["questionId"]]
    wrong = next(o for o in quiz["options"] if not any(m in o["text"] for m in markers))
    _check(
        "turn_quiz_wrong",
        walker.tap(
            {
                "name": "quiz_answer",
                "questionId": quiz["questionId"],
                "optionId": wrong["id"],
            }
        ),
    )

    for _ in range(5):
        if current["step"] != "TEACHBACK":
            break
        current = walker.answer_correctly(current)

    _check("turn_terms_consent", current)
    _check("turn_otp", walker.tap({"name": "accept_terms"}))

    sent = client.post(f"/api/journeys/{walker.journey_id}/otp/send", headers=headers).json()
    _check("otp_send", sent)

    done = client.post(
        f"/api/journeys/{walker.journey_id}/otp/verify",
        json={"code": sent["demoCode"]},
        headers=headers,
    ).json()
    _check("turn_receipt", done)

    receipt_no = done["card"]["data"]["receiptNo"]
    _check("receipt_verify", client.get(f"/api/receipts/{receipt_no}/verify").json())
    _check(
        "receipt_detail",
        client.get(f"/api/receipts/{receipt_no}", headers=headers).json(),
    )

    detail = client.get(f"/api/receipts/{receipt_no}", headers=headers).json()
    tampered = {**detail["payload"]}
    tampered["terms"] = {**tampered["terms"], "emi": 4_000}
    _check(
        "receipt_verify_candidate",
        client.post(
            f"/api/receipts/{receipt_no}/verify-candidate",
            json={"payload": tampered},
            headers=headers,
        ).json(),
    )


def test_contract_handoff(client: TestClient) -> None:
    """The handoff card, which a client must render as well as the happy path."""
    from tests.test_journey import Walker

    limiter.reset()
    headers = {"X-Demo-User": "sunita", "X-Demo-Key": settings.demo_auth_key}
    walker = Walker(client, headers)
    walker.start("mr-IN")
    _check("turn_handoff", walker.say("माणसाशी बोलायचं"))


def test_contract_manual_form(client: TestClient) -> None:
    """The declined-consent branch (§9 CONSENT_DATA)."""
    from tests.test_journey import Walker

    limiter.reset()
    headers = {"X-Demo-User": "sunita", "X-Demo-Key": settings.demo_auth_key}
    walker = Walker(client, headers)
    walker.start("mr-IN")
    walker.tap({"name": "amount", "amount": 50_000})
    _check(
        "turn_manual_form",
        walker.tap(
            {
                "name": "consents",
                "grants": {
                    "fetch_digilocker": False,
                    "fetch_account_aggregator": False,
                },
            }
        ),
    )


def test_contract_error_consent_locked(client: TestClient) -> None:
    """409 `consent_locked` - the error the app must explain, not just show."""
    from tests.test_journey import Walker

    limiter.reset()
    headers = {"X-Demo-User": "sunita", "X-Demo-Key": settings.demo_auth_key}
    walker = Walker(client, headers)
    walker.to_teachback()

    response = walker.turn({"type": "tap", "action": {"name": "accept_terms"}})
    assert response.status_code == 409
    _check("error_consent_locked", response.json())
