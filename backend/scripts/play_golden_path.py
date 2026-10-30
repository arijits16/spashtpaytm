"""Walk the whole journey over HTTP and print each step (build plan phase 3.4).

A quick check of the entire backend with no UI involved. It uses the demo
headers, so it exercises the real auth path, the real engine and the real
receipt append - the same code the iPhone will drive.

    backend/.venv/bin/python backend/scripts/play_golden_path.py
    backend/.venv/bin/python backend/scripts/play_golden_path.py --language hi-IN
    backend/.venv/bin/python backend/scripts/play_golden_path.py --voice   # text turns
    backend/.venv/bin/python backend/scripts/play_golden_path.py --all     # all 3 languages

`--voice` sends the *utterances* a customer would actually speak rather than
taps, which is what proves the understanding rules (§7.5) carry the golden path
without an LLM. Run both ways: they must reach the same receipt.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient  # noqa: E402

from app.config import settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.security.ratelimit import limiter  # noqa: E402

# What a customer says at each step, per language. These are the strings the
# rule-based understanding has to cope with - including the code-mixed one.
UTTERANCES: dict[str, dict[str, str]] = {
    "mr-IN": {
        "need": "मला ५० हजारांचं कर्ज शिलाई मशीनसाठी हवं आहे",
        "consent": "हो, चालेल",
        "confirm": "हो, बरोबर आहे",
        "offer": "सगळ्यात स्वस्त",
        "next": "हो",
        "q_late_fee": "लेट फी लागेल आणि सिबिल स्कोर कमी होईल",
        "q_total_repay": "एकूण ५५,२०० परत करावे लागतील",
        "q_insurance_optional": "नाही, विमा ऐच्छिक आहे, नाही म्हणता येतं",
    },
    "hi-IN": {
        "need": "mujhe 50 hazaar ka loan chahiye for machine",
        "consent": "हाँ, ठीक है",
        "confirm": "हाँ, सही है",
        "offer": "सबसे सस्ता",
        "next": "हाँ",
        "q_late_fee": "लेट फीस लगेगी और सिबिल स्कोर गिर जाएगा",
        "q_total_repay": "कुल 55,200 चुकाना होगा",
        "q_insurance_optional": "नहीं, बीमा ज़रूरी नहीं है, मना कर सकते हैं",
    },
    "en-IN": {
        "need": "I need a loan of fifty thousand for a sewing machine",
        "consent": "yes, that's fine",
        "confirm": "yes, correct",
        "offer": "the cheapest one",
        "next": "yes",
        "q_late_fee": "a late fee, and my credit score can drop",
        "q_total_repay": "I repay 55,200 in total",
        "q_insurance_optional": "no, it is optional, I can say no",
    },
}


class GoldenPath:
    """Drives one journey to a receipt and narrates it."""

    def __init__(self, client: TestClient, language: str, *, voice: bool) -> None:
        self.client = client
        self.language = language
        self.voice = voice
        self.says = UTTERANCES[language]
        self.journey_id: str | None = None
        self.steps: list[str] = []

    # --- plumbing --------------------------------------------------------

    @property
    def headers(self) -> dict[str, str]:
        return {"X-Demo-User": "sunita", "X-Demo-Key": settings.demo_auth_key}

    def _post(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.client.post(path, json=body or {}, headers=self.headers)
        if response.status_code >= 400:
            raise SystemExit(f"{path} -> {response.status_code}: {response.text[:400]}")
        return response.json()

    def _turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        """One turn, with a fresh idempotency id."""
        body = {"clientTurnId": str(uuid.uuid4()), "input": payload}
        return self._post(f"/api/journeys/{self.journey_id}/turn", body)

    def tap(self, action: dict[str, Any]) -> dict[str, Any]:
        return self._turn({"type": "tap", "action": action})

    def say(self, key: str, fallback_action: dict[str, Any]) -> dict[str, Any]:
        """Speak when `--voice`, otherwise tap. Both must reach the same place."""
        if self.voice and key in self.says:
            return self._turn({"type": "text", "text": self.says[key]})
        return self.tap(fallback_action)

    # --- narration -------------------------------------------------------

    def show(self, response: dict[str, Any]) -> dict[str, Any]:
        step = response["step"]
        self.steps.append(step)
        progress = response["progress"]
        card = (response.get("card") or {}).get("type", "-")
        lock = "unlocked" if response["locks"]["acceptEnabled"] else "locked"

        print(f"\n[{step}]  card={card}  {progress['label']} {progress['index'] + 1}/6  {lock}")
        for message in response["messages"]:
            who = "you " if message["role"] == "user" else "spasht"
            print(f"   {who}: {message['text']}")
        self._show_card(response.get("card"))
        return response

    def _show_card(self, card: dict[str, Any] | None) -> None:
        """Print the parts of a card that prove the step did its job."""
        if not card:
            return
        kind, data = card["type"], card["data"]

        if kind == "prefill":
            for row in data["rows"]:
                print(f"      + {row['label']}: {row['value']}  [{row['source']}]")
        elif kind == "offers":
            suitability = data["suitability"]
            print(
                f"      suitability: {suitability['decision']} "
                f"(EMI {suitability['foirPct']}% of income)"
            )
            for reason in suitability["reasons"]:
                print(f"        - {reason}")
            for offer in data["offers"]:
                badges = " ".join(f"[{badge}]" for badge in offer["badges"])
                print(
                    f"      {offer['lender']:18} rate {offer['ratePa']:>5.2f}%  "
                    f"APR {offer['apr']:>5.2f}%  EMI {offer['emi']:>6}  "
                    f"cost {offer['totalCost']:>6}  {badges}"
                )
        elif kind == "kfs":
            for line in data["lines"]:
                print(f"      {'!' if line['redFlag'] else ' '} {line['text']}")
        elif kind == "quiz":
            print(
                f"      Q{data['index']}/{data['total']} (attempt {data['attempt']}): {data['prompt']}"
            )
            for option in data["options"]:
                print(f"        ({option['id']}) {option['text']}")
        elif kind == "consent_lock":
            for term in data["terms"]:
                print(f"      - {term}")
            print(
                f"      insurance: {data['insurance']['premium']}, granted={data['insurance']['granted']}"
            )
        elif kind == "receipt":
            print(f"      receipt {data['receiptNo']}  {data['lender']}")
            print(f"      EMI {data['emi']} x {data['tenureMonths']} = {data['totalRepay']}")
            print(
                f"      understood {data['teachback']['passed']}/{data['teachback']['total']}, "
                f"insurance taken: {data['insuranceTaken']}"
            )
            print(f"      {data['publicUrl']}")
            print(f"      summary: {data['summaryText'][:120]}...")
        elif kind == "handoff":
            print(f"      {data['message']} ({data['window']})")

    # --- the walk --------------------------------------------------------

    def run(self) -> str:
        mode = "voice/text" if self.voice else "taps"
        print(f"\n{'=' * 74}\n  GOLDEN PATH  ·  {self.language}  ·  {mode}\n{'=' * 74}")

        start = self.show(
            self._post("/api/journeys", {"product": "personal_loan", "language": self.language})
        )
        self.journey_id = start["journeyId"]

        if start["step"] == "INTRO":
            self.show(self.tap({"name": "set_language", "language": self.language}))

        self.show(self.say("need", {"name": "amount", "amount": 50_000}))

        self.show(
            self.say(
                "consent",
                {
                    "name": "consents",
                    "grants": {"fetch_digilocker": True, "fetch_account_aggregator": True},
                },
            )
        )

        # PREFILL shows every fetched value with its source; one affirmative
        # moves on to the two fields that need confirming.
        self.show(self._turn({"type": "text", "text": self.says["next"]}))

        offers = self.show(self.say("confirm", {"name": "confirm_details"}))
        if offers["step"] != "OFFERS":
            offers = self.show(self.tap({"name": "repeat"}))

        cheapest = min(offers["card"]["data"]["offers"], key=lambda offer: offer["totalCost"])
        print(f"\n   >>> choosing {cheapest['lender']} (lowest total cost)")
        self.show(self.say("offer", {"name": "select_offer", "offerId": cheapest["offerId"]}))

        # EXPLAIN_KFS speaks explain_1..3 together, then the chip moves on. The
        # chip sends text, so this is a text turn in both modes.
        current = self.show(self._turn({"type": "text", "text": self.says["next"]}))
        if current["step"] == "EXPLAIN_KFS":
            current = self.show(self._turn({"type": "text", "text": self.says["next"]}))

        # TEACHBACK: three questions. The answer is chosen by *id* from the
        # card, never hard-coded, so a reordered option list cannot make this
        # script pass while the product is broken.
        for _ in range(6):
            if current["step"] != "TEACHBACK":
                break
            quiz = current["card"]["data"]
            question_id = quiz["questionId"]
            if self.voice and question_id in self.says:
                current = self.show(self._turn({"type": "text", "text": self.says[question_id]}))
            else:
                correct = self._correct_option_id(question_id, quiz)
                current = self.show(
                    self.tap(
                        {
                            "name": "quiz_answer",
                            "questionId": question_id,
                            "optionId": correct,
                        }
                    )
                )

        if current["step"] == "HUMAN_HANDOFF":
            raise SystemExit("teach-back failed - the golden path should not hand off")

        # TERMS_CONSENT: insurance stays off, then agree.
        self.show(self.tap({"name": "insurance_addon", "granted": False}))
        otp_step = self.show(self.tap({"name": "accept_terms"}))
        if otp_step["step"] != "OTP":
            raise SystemExit(f"expected OTP, got {otp_step['step']}")

        sent = self._post(f"/api/journeys/{self.journey_id}/otp/send")
        code = sent.get("demoCode")
        if not code:
            raise SystemExit("no demoCode: set OTP_DEMO=true and APP_ENV=dev in backend/.env")
        print(f"\n   >>> demo OTP {code} (dev only, never a real SMS)")

        done = self.show(self._post(f"/api/journeys/{self.journey_id}/otp/verify", {"code": code}))
        receipt_no = done["card"]["data"]["receiptNo"]

        self._verify(receipt_no)
        return receipt_no

    def _correct_option_id(self, question_id: str, quiz: dict[str, Any]) -> str:
        """Pick the right option by matching the seeded answer text.

        The card does not say which option is correct - that is the point - so
        this mirrors the seed file's known-correct wording.
        """
        markers = {
            "q_late_fee": ("लेट फी", "लेट फीस", "late fee"),
            "q_total_repay": ("55,200", "५५,२००"),
            "q_insurance_optional": ("ऐच्छिक", "ज़रूरी नहीं", "optional"),
            "q_cooling_off": ("दंडाशिवाय", "बिना जुर्माने", "no penalty"),
        }.get(question_id, ())

        for option in quiz["options"]:
            if any(marker in option["text"] for marker in markers):
                return option["id"]
        return quiz["options"][0]["id"]

    def _verify(self, receipt_no: str) -> None:
        """Verify the receipt, then prove an edited copy fails."""
        result = self.client.get(f"/api/receipts/{receipt_no}/verify").json()
        print(f"\n   receipt {receipt_no}: valid={result['valid']}  seq={result['seq']}")
        for check in result["checks"]:
            print(f"      {'OK ' if check['ok'] else 'BAD'} {check['name']}: {check['detail']}")
        if not result["valid"]:
            raise SystemExit("the receipt we just issued does not verify")

        detail = self.client.get(f"/api/receipts/{receipt_no}", headers=self.headers).json()
        tampered = {**detail["payload"]}
        tampered["terms"] = {**tampered["terms"], "emi": 4_000}

        candidate = self.client.post(
            f"/api/receipts/{receipt_no}/verify-candidate",
            json={"payload": tampered},
            headers=self.headers,
        ).json()
        print(f"\n   tamper demo (EMI -> 4,000): valid={candidate['valid']}")
        for reason in candidate["reasons"]:
            print(f"      ! {reason}")
        if candidate["valid"]:
            raise SystemExit("an edited receipt verified - the trust layer is broken")

        # And the real one is untouched.
        again = self.client.get(f"/api/receipts/{receipt_no}/verify").json()
        if not again["valid"]:
            raise SystemExit("the stored receipt changed during the tamper demo")
        print("   stored receipt is unchanged and still verifies")


def play(language: str, *, voice: bool) -> str:
    # Six journeys in as many seconds is well past the 60-turns-per-minute limit
    # (section 13.5), which is the limit working correctly rather than a bug. The
    # buckets are cleared between runs so `--all` exercises the journey rather
    # than the throttle.
    limiter.reset()

    if not settings.demo_auth_key or not settings.demo_auth:
        raise SystemExit(
            "demo auth is off. Set DEMO_AUTH=true in backend/.env and run `make keys`."
        )

    with TestClient(create_app()) as client:
        path = GoldenPath(client, language, voice=voice)
        receipt_no = path.run()
        print(f"\n   steps: {' -> '.join(path.steps)}")
        return receipt_no


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--language", default="mr-IN", choices=sorted(UTTERANCES))
    parser.add_argument(
        "--voice",
        action="store_true",
        help="send spoken utterances as text turns instead of taps",
    )
    parser.add_argument("--all", action="store_true", help="run every language, taps and voice")
    args = parser.parse_args()

    if args.all:
        for language in UTTERANCES:
            for voice in (False, True):
                play(language, voice=voice)
        print("\n==> all three languages completed by tap and by voice")
        return 0

    play(args.language, voice=args.voice)
    print("\n==> golden path complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
