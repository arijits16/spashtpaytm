"""The engine's guarantees (build plan phase 3, phase 6 acceptance criteria).

These are the behaviours the product's claims rest on, so they are asserted
against the real HTTP API with the real database - not against the engine in
isolation. A journey that only works when called directly is not the journey the
iPhone will drive.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.firebase import VerifiedToken
from app.config import settings
from app.db.models.journey import Consent, Journey, TeachbackAttempt
from app.security.ratelimit import limiter

# Known-correct option markers, mirroring the seed file (§7.3).
CORRECT_MARKERS = {
    "q_late_fee": ("लेट फी", "लेट फीस", "late fee"),
    "q_total_repay": ("55,200", "५५,२००"),
    "q_insurance_optional": ("ऐच्छिक", "ज़रूरी नहीं", "optional"),
}


@pytest.fixture(autouse=True)
def _reset_limits() -> Iterator[None]:
    """Several journeys per test would otherwise trip the 60/min turn limit."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture()
def demo_headers() -> dict[str, str]:
    return {"X-Demo-User": "sunita", "X-Demo-Key": settings.demo_auth_key}


class Walker:
    """Drives a journey over HTTP, so tests read as a sequence of taps."""

    def __init__(self, client: TestClient, headers: dict[str, str]) -> None:
        self.client = client
        self.headers = headers
        self.journey_id: str = ""

    def start(self, language: str = "mr-IN") -> dict[str, Any]:
        response = self.client.post(
            "/api/journeys",
            json={"product": "personal_loan", "language": language},
            headers=self.headers,
        )
        assert response.status_code == 200, response.text
        body = response.json()
        self.journey_id = body["journeyId"]
        return body

    def turn(self, payload: dict[str, Any], *, turn_id: str | None = None) -> Any:
        body = {"clientTurnId": turn_id or str(uuid.uuid4()), "input": payload}
        return self.client.post(
            f"/api/journeys/{self.journey_id}/turn", json=body, headers=self.headers
        )

    def tap(self, action: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        response = self.turn({"type": "tap", "action": action}, **kwargs)
        assert response.status_code == 200, response.text
        return response.json()

    def say(self, utterance: str) -> dict[str, Any]:
        response = self.turn({"type": "text", "text": utterance})
        assert response.status_code == 200, response.text
        return response.json()

    def to_offers(self, language: str = "mr-IN") -> dict[str, Any]:
        """Start and walk as far as the offers screen."""
        self.start(language)
        self.tap({"name": "amount", "amount": 50_000})
        self.tap(
            {
                "name": "consents",
                "grants": {"fetch_digilocker": True, "fetch_account_aggregator": True},
            }
        )
        self.say("हो")
        return self.tap({"name": "confirm_details"})

    def to_teachback(self, language: str = "mr-IN") -> dict[str, Any]:
        offers = self.to_offers(language)
        cheapest = min(offers["card"]["data"]["offers"], key=lambda o: o["totalCost"])
        self.tap({"name": "select_offer", "offerId": cheapest["offerId"]})
        return self.say("हो")

    def answer_correctly(self, current: dict[str, Any]) -> dict[str, Any]:
        """Answer whatever question is on screen, correctly."""
        quiz = current["card"]["data"]
        markers = CORRECT_MARKERS[quiz["questionId"]]
        option = next(o for o in quiz["options"] if any(m in o["text"] for m in markers))
        return self.tap(
            {
                "name": "quiz_answer",
                "questionId": quiz["questionId"],
                "optionId": option["id"],
            }
        )

    def answer_wrongly(self, current: dict[str, Any]) -> dict[str, Any]:
        quiz = current["card"]["data"]
        markers = CORRECT_MARKERS[quiz["questionId"]]
        option = next(o for o in quiz["options"] if not any(m in o["text"] for m in markers))
        return self.tap(
            {
                "name": "quiz_answer",
                "questionId": quiz["questionId"],
                "optionId": option["id"],
            }
        )

    def pass_teachback(self, language: str = "mr-IN") -> dict[str, Any]:
        current = self.to_teachback(language)
        for _ in range(4):
            if current["step"] != "TEACHBACK":
                break
            current = self.answer_correctly(current)
        return current


@pytest.fixture()
def walker(client: TestClient, demo_headers: dict[str, str]) -> Walker:
    return Walker(client, demo_headers)


# --- the journey -------------------------------------------------------------


@pytest.mark.parametrize("language", ["mr-IN", "hi-IN", "en-IN"])
def test_offers_are_sorted_by_apr_and_badged(walker: Walker, language: str) -> None:
    """The demo's central claim, in all three languages (phase 3 acceptance).

    Bank B advertises the lowest rate and is last, because the APR is what the
    customer actually pays.
    """
    offers = walker.to_offers(language)
    assert offers["step"] == "OFFERS"

    rows = offers["card"]["data"]["offers"]
    assert [row["apr"] for row in rows] == sorted(row["apr"] for row in rows)

    by_id = {row["offerId"]: row for row in rows}
    assert "lowest_total_cost" in by_id["offer_a"]["badges"]
    assert "low_rate_high_fee" in by_id["offer_b"]["badges"]
    assert by_id["offer_b"]["ratePa"] < by_id["offer_a"]["ratePa"]
    assert by_id["offer_b"]["totalCost"] > by_id["offer_a"]["totalCost"]


def test_prefill_shows_every_source(walker: Walker) -> None:
    """The customer sees where each value came from (§5.6)."""
    walker.start()
    walker.tap({"name": "amount", "amount": 50_000})
    prefill = walker.tap(
        {
            "name": "consents",
            "grants": {"fetch_digilocker": True, "fetch_account_aggregator": True},
        }
    )

    assert prefill["step"] == "PREFILL"
    sources = {row["source"] for row in prefill["card"]["data"]["rows"]}
    assert sources == {"DigiLocker", "CKYC", "Account Aggregator", "UPI AutoPay"}


def test_declining_consent_reaches_the_manual_form(walker: Walker) -> None:
    """Declining data sharing must never end the journey (§9 CONSENT_DATA)."""
    walker.start()
    walker.tap({"name": "amount", "amount": 50_000})
    declined = walker.tap(
        {
            "name": "consents",
            "grants": {"fetch_digilocker": False, "fetch_account_aggregator": False},
        }
    )

    assert declined["step"] == "MANUAL_FORM"

    offers = walker.tap(
        {
            "name": "manual_form",
            "fields": {
                "fullName": "Test Customer",
                "dob": "1992-04-18",
                "monthlyIncome": 28_400,
                "shopAddress": "Shop 14, Nehru Road, Ghatkopar West",
                "mobile": "9800000210",
            },
        }
    )
    assert offers["step"] == "OFFERS"
    # Self-declared income must be labelled as such, not passed off as verified.
    reasons = " ".join(offers["card"]["data"]["suitability"]["reasons"])
    assert "बँक माहिती घेतली नाही" in reasons


def test_consent_defaults_are_always_off(walker: Walker) -> None:
    """Every consent the customer is offered starts at no (§9 invariant 2)."""
    walker.start()
    consent = walker.tap({"name": "amount", "amount": 50_000})

    assert consent["step"] == "CONSENT_DATA"
    assert all(p["granted"] is False for p in consent["card"]["data"]["purposes"])

    terms = walker.pass_teachback()
    insurance = terms["card"]["data"]["insurance"]
    assert insurance["granted"] is False
    assert insurance["optional"] is True


def test_accept_before_passing_is_409_consent_locked(walker: Walker) -> None:
    """The backend guard, not the disabled button (§9, phase 3 acceptance)."""
    current = walker.to_teachback()
    assert current["locks"]["acceptEnabled"] is False

    response = walker.turn({"type": "tap", "action": {"name": "accept_terms"}})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_locked"


def test_teachback_unlocks_the_agreement(walker: Walker) -> None:
    terms = walker.pass_teachback()
    assert terms["step"] == "TERMS_CONSENT"
    assert terms["locks"]["acceptEnabled"] is True
    assert terms["card"]["data"]["acceptEnabled"] is True


def test_wrong_answer_re_explains_then_hands_off(walker: Walker) -> None:
    """One wrong answer re-explains; three hand off with consent still locked."""
    current = walker.to_teachback()
    question_id = current["card"]["data"]["questionId"]

    after_one = walker.answer_wrongly(current)
    assert after_one["step"] == "TEACHBACK"
    assert after_one["card"]["data"]["questionId"] == question_id
    assert after_one["card"]["data"]["attempt"] == 2
    assert after_one["card"]["data"]["result"]["correct"] is False
    # The re-explanation is spoken, which is the whole point of a wrong answer.
    assert any(m["role"] == "assistant" for m in after_one["messages"])

    after_two = walker.answer_wrongly(after_one)
    assert after_two["card"]["data"]["attempt"] == 3

    after_three = walker.answer_wrongly(after_two)
    assert after_three["step"] == "HUMAN_HANDOFF"
    assert after_three["status"] == "needs_human"
    assert after_three["locks"]["acceptEnabled"] is False
    assert after_three["card"]["type"] == "handoff"


def test_asking_for_a_human_hands_off_from_any_step(walker: Walker) -> None:
    walker.start()
    handoff = walker.say("माणसाशी बोलायचं")
    assert handoff["step"] == "HUMAN_HANDOFF"
    assert handoff["status"] == "needs_human"


def test_two_misunderstood_turns_offer_a_human(walker: Walker) -> None:
    """§13.7: repeated confusion is distress, and distress escalates."""
    walker.start()
    walker.tap({"name": "amount", "amount": 50_000})
    walker.say("qwertyuiop asdfgh")
    second = walker.say("zxcvbnm lkjhgf")
    assert second["step"] == "HUMAN_HANDOFF"


# --- idempotency, ownership, locking ----------------------------------------


def test_repeated_client_turn_id_replays(walker: Walker) -> None:
    """A retry over a flaky tunnel must not advance the journey twice."""
    walker.start()
    turn_id = str(uuid.uuid4())

    first = walker.tap({"name": "amount", "amount": 50_000}, turn_id=turn_id)
    second = walker.tap({"name": "amount", "amount": 50_000}, turn_id=turn_id)

    assert first == second
    assert second["step"] == "CONSENT_DATA"


def test_stale_version_is_a_conflict(walker: Walker) -> None:
    current = walker.start()
    response = walker.client.post(
        f"/api/journeys/{walker.journey_id}/turn",
        json={
            "clientTurnId": str(uuid.uuid4()),
            "expectedVersion": current["version"] - 1,
            "input": {"type": "tap", "action": {"name": "amount", "amount": 50_000}},
        },
        headers=walker.headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "version_conflict"


def test_another_users_journey_is_404(
    walker: Walker,
    client: TestClient,
    mock_verifier: Callable[[VerifiedToken], None],
) -> None:
    """Never 403: that would confirm the journey exists (§13.2)."""
    walker.start()
    mock_verifier(
        VerifiedToken(
            uid="test:intruder",
            email="intruder@example.invalid",
            name="Intruder",
            picture=None,
            email_verified=True,
        )
    )
    response = client.get(
        f"/api/journeys/{walker.journey_id}",
        headers={"Authorization": "Bearer good-token"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_resume_returns_the_same_step(walker: Walker) -> None:
    """Killing the app mid-journey loses nothing (phase 5 acceptance)."""
    current = walker.to_teachback()

    resumed = walker.client.get("/api/journeys/current", headers=walker.headers).json()
    assert resumed["step"] == current["step"]
    assert resumed["card"]["data"]["questionId"] == current["card"]["data"]["questionId"]


def test_starting_twice_returns_the_same_journey(walker: Walker) -> None:
    first = walker.start()
    second = walker.start()
    assert first["journeyId"] == second["journeyId"]


def test_language_switch_mid_journey(walker: Walker) -> None:
    walker.start("mr-IN")
    switched = walker.tap({"name": "set_language", "language": "hi-IN"})
    assert switched["language"] == "hi-IN"
    assert "नमस्ते" in switched["messages"][0]["text"]


# --- evidence ----------------------------------------------------------------


def test_every_consent_decision_is_recorded(walker: Walker, db: Session) -> None:
    """Including the refusals: a declined consent is evidence too (§6)."""
    walker.start()
    walker.tap({"name": "amount", "amount": 50_000})
    walker.tap(
        {
            "name": "consents",
            "grants": {"fetch_digilocker": True, "fetch_account_aggregator": False},
        }
    )

    rows = db.scalars(
        select(Consent).where(Consent.journey_id == uuid.UUID(walker.journey_id))
    ).all()
    grants = {row.purpose: row.granted for row in rows}
    assert grants == {"fetch_digilocker": True, "fetch_account_aggregator": False}
    # `default_value` is what proves the toggle started off.
    assert all(row.default_value is False for row in rows)


def test_wrong_attempts_are_kept(walker: Walker, db: Session) -> None:
    """The first-attempt pass rate the dashboard charts depends on this."""
    current = walker.to_teachback()
    question_id = current["card"]["data"]["questionId"]
    after = walker.answer_wrongly(current)
    walker.answer_correctly(after)

    rows = db.scalars(
        select(TeachbackAttempt)
        .where(TeachbackAttempt.journey_id == uuid.UUID(walker.journey_id))
        .where(TeachbackAttempt.question_id == question_id)
        .order_by(TeachbackAttempt.attempt_no)
    ).all()
    assert [row.is_correct for row in rows] == [False, True]


def test_audit_trail_covers_the_journey(walker: Walker, db: Session) -> None:
    walker.pass_teachback()
    events = (
        db.execute(
            text("SELECT DISTINCT event_type FROM audit_log WHERE journey_id = :j"),
            {"j": walker.journey_id},
        )
        .scalars()
        .all()
    )

    assert {
        "journey.started",
        "step.entered",
        "consent.recorded",
        "prefill.completed",
        "offer.selected",
        "suitability.decided",
        "teachback.answered",
        "teachback.passed",
    } <= set(events)


def test_journey_rows_are_scoped_to_their_user(walker: Walker, db: Session) -> None:
    walker.start()
    journey = db.get(Journey, uuid.UUID(walker.journey_id))
    assert journey is not None
    assert journey.persona_id == "sunita"
    assert journey.status == "active"
