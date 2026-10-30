"""The journey engine (build plan §9).

```
INTRO -> ASK_NEED -> CONSENT_DATA -> PREFILL -> CONFIRM_DETAILS -> OFFERS
      -> EXPLAIN_KFS -> TEACHBACK -> TERMS_CONSENT -> OTP -> RECEIPT -> DONE
            \\ (declined) MANUAL_FORM /       any step -> HUMAN_HANDOFF
```

**The core principle.** `transition(state, understood_input) -> (new_state,
response)` is deterministic Python. The LLM, when phase 8 adds it, only fills in
`understood_input` and paraphrases text; it never decides a transition, never
unlocks a consent and never chooses an offer. That is what lets this system be
both conversational and auditable: a regulator can read this file and know what
the product will do.

**Three invariants the rest of the code depends on.**

1. *The server decides everything.* The client sends a tap or an utterance and
   renders what comes back. `acceptEnabled` is re-checked here when
   `accept_terms` arrives, so a patched client gains nothing (§9).
2. *Consent defaults to off, always.* Every consent card ships `granted: false`
   and the customer's answer travels in an action. There is no code path that
   turns a consent on without one.
3. *Every transition is audited.* The append-only trail is written in the same
   transaction as the state change, so history cannot disagree with state.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models.catalog import KfsDocument
from app.db.models.journey import Consent, Journey, TeachbackAttempt
from app.db.models.persona import Persona
from app.events.bus import publish_journey_updated
from app.journey import events, otp
from app.journey.cards import (
    AmountCard,
    AmountCardData,
    Card,
    ConfirmCard,
    ConfirmCardData,
    ConfirmField,
    ConsentCard,
    ConsentCardData,
    ConsentLockCard,
    ConsentLockCardData,
    ConsentPurpose,
    HandoffCard,
    HandoffCardData,
    InsuranceChoice,
    KfsCard,
    KfsCardData,
    KfsLine,
    LanguageCard,
    LanguageCardData,
    LanguageOption,
    ManualFormCard,
    ManualFormCardData,
    ManualFormField,
    OffersCard,
    OffersCardData,
    OfferSummary,
    OtpCard,
    OtpCardData,
    PrefillCard,
    PrefillCardData,
    PrefillRow,
    QuizCard,
    QuizCardData,
    QuizOption,
    QuizResult,
    Suitability,
)
from app.journey.context import JourneyContext, PrefillData, QuizProgress
from app.journey.offers import PricedOffer, lender_names, price_offers, resolve_hint
from app.journey.responses import (
    AcceptTermsAction,
    Action,
    AmountAction,
    ConfirmDetailsAction,
    ConsentsAction,
    DidntUnderstandAction,
    InsuranceAddonAction,
    Locks,
    ManualFormAction,
    Message,
    Progress,
    QuickReply,
    QuickReplySend,
    QuizAnswerAction,
    RepeatAction,
    RequestHumanAction,
    SelectOfferAction,
    SetLanguageAction,
    TapInput,
    TextInput,
    TurnInput,
    TurnResponse,
)
from app.journey.states import (
    AMOUNT_MAX_DEFAULT,
    AMOUNT_MIN_DEFAULT,
    Lang,
    Status,
    Step,
    progress_for,
)
from app.journey.suitability import assess
from app.journey.teachback import (
    MAX_ATTEMPTS,
    MIN_CONFIDENCE,
    Grade,
    RenderedQuestion,
    active_questions,
    grade_free_text,
    grade_option,
    kfs_lines,
)
from app.journey.teachback import render as render_question
from app.journey.templates import honorific, render, render_with_facts
from app.journey.understand_rules import (
    Intent,
    Understanding,
    clause_search_terms,
    understand,
)

log = logging.getLogger(__name__)

# Suggested amounts (§9 ASK_NEED).
AMOUNT_CHIPS = (25_000, 50_000, 100_000)

# §9: ask for the amount again at most once, then show the chips.
MAX_AMOUNT_ASKS = 1

# §13.7: two consecutive misunderstandings offer a human.
CONFUSION_LIMIT = 2

# The window the handoff card promises. Matches `CONTACT_WINDOW` in config.
HANDOFF_WINDOW = "9 am - 6 pm"


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """A request for better-phrased text, which the route may fulfil.

    @param kind            'reexplain' | 'kfs_answer'.
    @param message_index   Which of `assistant_messages` to replace on success.
    @param seeded          The already-correct text, and the guard's fallback.

    Modelled as data rather than as a callback so the engine stays free of any
    knowledge of the AI layer: it states what *could* be improved and the route
    decides whether that is possible right now.
    """

    kind: str
    message_index: int
    seeded: str
    facts: dict[str, Any]
    question_prompt: str = ""
    customer_question: str = ""
    search_terms: str = ""


@dataclass
class EngineResult:
    """What one turn produced.

    The engine mutates the `Journey` row and returns the response to send. It
    does not commit: the route owns the transaction, so the audit trail, the
    state change and the idempotency record land together or not at all.
    """

    response: TurnResponse
    assistant_messages: list[str]
    user_message: str | None = None

    #: Set when the step reached is RECEIPT, so the route knows to append the
    #: receipt (phase 6) before serialising the response.
    needs_receipt: bool = False

    #: A prose improvement the route may await after the engine has finished
    #: (phase 8). The engine has already produced a correct, seeded message;
    #: this only asks for a better-phrased version of it. If the LLM is down or
    #: the Number Guard rejects the result, the seeded text stands and nothing
    #: about the journey changes.
    generation: GenerationRequest | None = None


class Engine:
    """One turn's worth of work on one journey.

    Constructed per request. Holding the session, settings and journey as
    instance state keeps the step handlers readable - they are the interesting
    part, and threading four parameters through each would bury them.
    """

    def __init__(self, db: Session, journey: Journey, settings: Settings, *, actor: str) -> None:
        self.db = db
        self.journey = journey
        self.settings = settings
        self.actor = actor
        self.context = JourneyContext.of(journey.context)
        self.messages: list[str] = []
        self._generation: GenerationRequest | None = None
        self._card: Card | None = None
        self._quick_replies: list[QuickReply] = []
        self._needs_receipt = False

    # --- public entry points -------------------------------------------------

    def start(self) -> EngineResult:
        """Produce the opening turn of a new journey."""
        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.JOURNEY_STARTED,
            step=self.journey.step,
            data={"language": self.journey.language, "product": self.journey.product},
        )
        # A client that already knows the language (the app asks on its intro
        # screen) skips the language card entirely - asking twice is friction.
        self._enter(Step.ASK_NEED if self._language_known() else Step.INTRO)
        return self.finish()

    def resume(self) -> EngineResult:
        """Re-render the current step without advancing it.

        Used by `GET /journeys/current` and `GET /journeys/{id}`, and after a
        rescue call. The card is rebuilt from `step` + `context`, which is why
        killing the app mid-journey loses nothing.
        """
        self._render_current_step()
        return self.finish(record_turn=False)

    def complete(self) -> EngineResult:
        """OTP verified: move to RECEIPT so the route can append the receipt.

        A public entry point because OTP verification has its own route (§8.2) -
        the code is not a conversational turn - but the transition into RECEIPT
        still has to go through `_enter`, so that it is audited and so that
        `needs_receipt` is set for the route to act on.
        """
        self.context.otp_verified = True
        self._enter(Step.RECEIPT)
        return self.finish()

    def render_current_step_publicly(self) -> None:
        """Rebuild the current card without advancing or speaking.

        Used by the voice route when a recording was unclear: the
        `didnt_catch` line has already been added, and the customer should see
        the same step again rather than a blank screen.
        """
        self._render_current_step(speak=False)

    def note_detected_language(self, detected: Lang | None) -> None:
        """Track a language mismatch on a voice turn (§10.1).

        Two consecutive turns detected in a different language than the journey
        is being conducted in means the customer has switched and we have not.
        Offering to follow them is better than continuing to answer in a
        language they have stopped using.
        """
        if detected is None:
            return
        self.context.detected_language = detected
        if detected == self._language:
            self.context.language_mismatch_streak = 0
            return

        self.context.language_mismatch_streak += 1
        if self.context.language_mismatch_streak >= 2:
            # Follow the customer rather than asking: they have now said two
            # things in this language, which is a clearer signal than a prompt
            # they would have to answer in the language they are struggling in.
            self._switch_language(detected)
            self.context.language_mismatch_streak = 0

    def handle(
        self, turn_input: TurnInput, understanding: Understanding | None = None
    ) -> EngineResult:
        """Advance the journey by one customer turn.

        @param understanding  A pre-resolved classification for a text turn
                              (`journey/understand.resolve`). Passed in rather
                              than computed here because resolving it may
                              involve an LLM call, and keeping `await` out of
                              the state machine is what lets every transition
                              be read as a plain function.
        """
        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.TURN_RECEIVED,
            step=self.journey.step,
            data={"kind": turn_input.type},
        )

        if isinstance(turn_input, TapInput):
            self._handle_action(turn_input.action)
        else:
            self._handle_text(turn_input.text, understanding)

        return self.finish(user_message=self._echo_of(turn_input))

    # --- text and taps -------------------------------------------------------

    def _echo_of(self, turn_input: TurnInput) -> str | None:
        """What to show in the customer's own bubble.

        Typed and spoken text is echoed verbatim. A tap is not: the card already
        showed what was tapped, and "confirm_details" in a chat bubble is noise.
        """
        return turn_input.text if isinstance(turn_input, TextInput) else None

    def _handle_text(self, text: str, understanding: Understanding | None = None) -> None:
        """Route free text through the same handlers a tap reaches.

        Falls back to the rules alone when no classification was supplied,
        which keeps the engine usable on its own - in a test, or from the
        golden-path script - without a model or a network.
        """
        if understanding is None:
            offers = self._current_offers()
            understanding = understand(
                text,
                step_expects_amount=self._step is Step.ASK_NEED,
                lender_names=lender_names(offers),
            )
        self._route_understanding(understanding)

    def _route_understanding(self, result: Understanding) -> None:
        """Map an intent onto the same handlers a tap would reach.

        Voice and tap converge here deliberately: one code path means the
        journey cannot behave differently depending on how the customer
        answered, which is the plan's "every voice action has a tap
        alternative" promise read from the other direction.
        """
        step = self._step

        if result.intent is Intent.WANT_HUMAN:
            self._to_handoff("customer asked for a person")
            return

        if result.intent is Intent.SWITCH_LANGUAGE and result.language:
            self._switch_language(result.language)
            return

        if result.intent in (Intent.DIDNT_UNDERSTAND, Intent.OTHER):
            self._on_not_understood(repeat=result.intent is Intent.DIDNT_UNDERSTAND)
            return

        if step is Step.INTRO:
            # Any understood utterance at INTRO means she is talking already;
            # the language card has served its purpose.
            self._enter(Step.ASK_NEED)
            if result.amount or result.purpose:
                self._apply_need(result.amount, result.purpose)
            return

        if step is Step.ASK_NEED and result.intent is Intent.PROVIDE_NEED:
            self._apply_need(result.amount, result.purpose)
            return

        if step is Step.CONSENT_DATA:
            if result.intent is Intent.YES:
                self._apply_consents(True, True, method="voice")
            elif result.intent is Intent.NO:
                self._apply_consents(False, False, method="voice")
            else:
                self._on_not_understood()
            return

        if step is Step.PREFILL and result.intent in (Intent.YES, Intent.CHOOSE_OFFER):
            self._enter(Step.CONFIRM_DETAILS)
            return

        if step is Step.CONFIRM_DETAILS and result.intent is Intent.YES:
            self._apply_confirm(None)
            return

        if step is Step.OFFERS and result.intent is Intent.CHOOSE_OFFER:
            chosen = resolve_hint(self._current_offers(), result.offer_hint)
            if chosen is None:
                self._on_not_understood()
            else:
                self._apply_offer(chosen.offer_id)
            return

        if step is Step.EXPLAIN_KFS and result.intent is Intent.YES:
            self._advance_explanation()
            return

        if step is Step.TEACHBACK:
            self._apply_spoken_answer(result.raw)
            return

        if step is Step.TERMS_CONSENT and result.intent is Intent.YES:
            # A spoken "हो" is consent to continue, not consent to the loan:
            # §5.6 requires the agreement itself to be an explicit tap, so this
            # only re-renders the card with the lock state.
            self._render_current_step()
            return

        if result.intent is Intent.QUESTION_ABOUT_TERMS:
            self._on_question_about_terms(result.raw)
            return

        self._on_not_understood()

    def _handle_action(self, action: Action) -> None:
        """Dispatch a validated tap.

        Exhaustive by construction: `Action` is a closed discriminated union, so
        a new button cannot reach here without a branch being added.
        """
        match action:
            case SetLanguageAction():
                self._switch_language(action.language)
            case AmountAction():
                self._apply_need(action.amount, self.context.purpose)
            case ConsentsAction():
                self._apply_consents(
                    action.grants.fetch_digilocker,
                    action.grants.fetch_account_aggregator,
                    method="tap",
                )
            case ManualFormAction():
                self._apply_manual_form(action)
            case ConfirmDetailsAction():
                self._apply_confirm(action)
            case SelectOfferAction():
                self._apply_offer(action.offerId)
            case QuizAnswerAction():
                self._apply_quiz_answer(action)
            case InsuranceAddonAction():
                self._apply_insurance(action.granted)
            case AcceptTermsAction():
                self._apply_accept_terms()
            case RepeatAction():
                self._render_current_step()
            case DidntUnderstandAction():
                self._on_not_understood(repeat=True)
            case RequestHumanAction():
                self._to_handoff("customer tapped 'talk to a person'")

    # --- step handlers -------------------------------------------------------

    def _apply_need(self, amount: int | None, purpose: str | None) -> None:
        """ASK_NEED: record the amount and purpose, or ask once more."""
        if purpose:
            self.context.purpose = purpose

        if amount is None:
            # Nothing to work with. One more ask, then the chips - a third
            # question in a language the customer is struggling with does not
            # produce an answer, it produces an abandoned application.
            self.context.amount_asks += 1
            self._enter(Step.ASK_NEED)
            return

        if not (AMOUNT_MIN_DEFAULT <= amount <= AMOUNT_MAX_DEFAULT):
            self.messages.append(
                render(
                    "amount_out_of_range",
                    self._language,
                    MIN=f"{AMOUNT_MIN_DEFAULT:,}",
                    MAX=f"{AMOUNT_MAX_DEFAULT:,}",
                )
            )
            self._enter(Step.ASK_NEED, speak=False)
            return

        self.context.amount = amount
        self._enter(Step.CONSENT_DATA)

    def _apply_consents(self, digilocker: bool, aggregator: bool, *, method: str) -> None:
        """CONSENT_DATA: store each purpose, then prefill or fall back to the form.

        Both purposes are recorded whatever the answer, including the refusals.
        A declined consent is evidence too - it is what proves the toggle
        started off and the customer chose.
        """
        self.context.consent_asked = True
        self.context.consent_digilocker = digilocker
        self.context.consent_account_aggregator = aggregator

        terms = render("ask_consent", self._language)
        for purpose, granted in (
            ("fetch_digilocker", digilocker),
            ("fetch_account_aggregator", aggregator),
        ):
            self.db.add(
                Consent(
                    journey_id=self.journey.id,
                    purpose=purpose,
                    granted=granted,
                    default_value=False,
                    method=method,
                    evidence={"step": str(self._step), "shown": terms},
                )
            )
            events.record(
                self.db,
                journey_id=self.journey.id,
                actor=self.actor,
                event_type=events.CONSENT_RECORDED,
                step=str(self._step),
                data={"purpose": purpose, "granted": granted, "method": method},
            )
        self.db.flush()

        if not digilocker and not aggregator:
            # Never a dead end (§9): declining data sharing costs the customer
            # time, not the loan.
            self.messages.append(render("consent_declined", self._language))
            self._enter(Step.MANUAL_FORM, speak=False)
            return

        self._enter(Step.PREFILL)

    def offers_for_understanding(self) -> list[dict[str, Any]]:
        """The offers on screen, as plain dicts for the understanding layer.

        Empty before an amount is known, the full list at OFFERS, and just the
        selected one afterwards - which is also exactly the Number Guard's
        allow-list, because what is quotable and what is referrable are the
        same set (§10.5).
        """
        selected = self._selected_offer()
        offers = [selected] if selected is not None else self._current_offers()
        return [{"offer_id": offer.offer_id, **offer.facts} for offer in offers]

    def quiz_options_for_understanding(self) -> list[tuple[str, str]]:
        """`(id, text)` for the question on screen, if there is one."""
        if self._step is not Step.TEACHBACK:
            return []
        question = self._current_question()
        if question is None:
            return []
        return [(option.id, option.text) for option in question.options]

    def needs_prefill(self) -> bool:
        """True when PREFILL has been entered but the adapters have not run.

        The route asks this rather than inferring it from the step, so a
        resumed journey sitting on PREFILL with its rows already fetched does
        not fetch them a second time.
        """
        return self._step is Step.PREFILL and not self._get_meta("prefill_rows", [])

    async def run_prefill(self) -> None:
        """PREFILL: fetch from the consented sources and show what came back.

        The one `async` method on an otherwise synchronous state machine, and
        the only non-database I/O in the whole journey. Awaited by the route
        rather than reached from `_enter`, so every transition stays a plain
        function call that a reviewer can follow without tracing a coroutine.

        The journey **stays** on PREFILL afterwards. The customer is shown each
        value with the source it came from, which is the screen that turns "we
        filled your form" into "here is where each of these came from, and you
        can see it is right" - the reassurance is the step's whole purpose, so
        it does not get skipped past in the same turn.
        """
        from app.adapters import run_prefill as fetch_all

        persona_id = self.journey.persona_id
        if not persona_id:
            self._enter(Step.MANUAL_FORM)
            return

        results = await fetch_all(
            self.db,
            persona_id,
            include_identity=self.context.consent_digilocker,
            include_financial=self.context.consent_account_aggregator,
        )

        prefill = self.context.prefill
        rows: list[dict[str, str]] = []
        for result in results:
            for row in result.rows:
                rows.append({"label": row.label, "value": row.value, "source": row.source})
            for key, value in result.data.items():
                if hasattr(prefill, key) and value is not None:
                    setattr(prefill, key, value)
            prefill.sources[result.source] = f"{result.latency_ms}ms"

        self.context.prefill = prefill
        # Stored so the card can be rebuilt on resume without re-running the
        # adapters - a resumed journey must not look like it fetched twice.
        self._set_meta("prefill_rows", rows)

        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.PREFILL_COMPLETED,
            step=str(Step.PREFILL),
            data={"sources": prefill.sources, "row_count": len(rows)},
        )

        self.messages.append(render("prefilled", self._language))
        self._render_current_step(speak=False)

    def _apply_manual_form(self, action: ManualFormAction) -> None:
        """MANUAL_FORM: take the customer's own details.

        `self_declared` is set so the suitability reasons, and later the
        receipt, say the income was declared rather than verified. A receipt
        that implies bank verification that never happened would be a lie.
        """
        fields = action.fields
        self.context.prefill = PrefillData(
            full_name=fields.fullName,
            dob=fields.dob,
            monthly_income=fields.monthlyIncome,
            shop_address=fields.shopAddress,
            mobile=fields.mobile,
            existing_emi=0,
            self_declared=True,
            sources={"Self declared": "manual"},
        )
        self.context.details_confirmed = True
        self.messages.append(render("manual_saved", self._language))
        self._enter(Step.OFFERS, speak=False)

    def _apply_confirm(self, action: ConfirmDetailsAction | None) -> None:
        """CONFIRM_DETAILS: accept, or apply the two editable fields."""
        if action is not None and action.edits is not None:
            if action.edits.shopAddress:
                self.context.prefill.shop_address = action.edits.shopAddress
            if action.edits.mobile:
                self.context.prefill.mobile = action.edits.mobile

        self.context.details_confirmed = True
        self.messages.append(render("confirm_saved", self._language))
        self._enter(Step.OFFERS, speak=False)

    def _apply_offer(self, offer_id: str) -> None:
        """OFFERS: select one and move to the explanation."""
        offers = self._current_offers()
        chosen = next((o for o in offers if o.offer_id == offer_id), None)
        if chosen is None:
            self._on_not_understood()
            return

        self.journey.selected_offer_id = chosen.offer_id
        document = self._kfs_document(chosen)
        self.journey.kfs_document_id = document.id if document else None

        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.OFFER_SELECTED,
            step=str(self._step),
            data={
                "offerId": chosen.offer_id,
                "lender": chosen.lender,
                "apr": chosen.apr,
                "badges": list(chosen.badges),
            },
        )

        self.context.explained = []
        self._enter(Step.EXPLAIN_KFS)

    #: The three explanation lines, spoken together on entering EXPLAIN_KFS.
    EXPLANATION_KEYS = ("explain_1", "explain_2", "explain_3")

    def _speak_explanation(self) -> None:
        """Speak explain_1..3 (§9 EXPLAIN_KFS).

        All three in one turn rather than one per tap. They are two sentences
        each and the KFS card beside them carries the detail, so splitting them
        would cost the customer three taps to hear one paragraph - and a
        customer tapping "next" three times is not listening by the third.
        """
        offer = self._selected_offer()
        if offer is None:
            return
        for key in self.EXPLANATION_KEYS:
            self.messages.append(render_with_facts(key, self._language, offer.facts))
        self.context.explained = list(self.EXPLANATION_KEYS)

    def _advance_explanation(self) -> None:
        """Leave EXPLAIN_KFS for the quiz, re-explaining first if we have not yet."""
        if not self.context.explained:
            self._speak_explanation()
            self._render_current_step(speak=False)
            return
        self._enter(Step.TEACHBACK)

    def _apply_quiz_answer(self, action: QuizAnswerAction) -> None:
        """TEACHBACK: grade a tapped option."""
        question = self._current_question()
        if question is None or question.id != action.questionId:
            self._render_current_step()
            return
        self._record_answer(
            question, action.optionId, "option", grade_option(question, action.optionId)
        )

    def _apply_spoken_answer(self, text: str) -> None:
        """TEACHBACK: grade a spoken or typed answer against the rubric."""
        question = self._current_question()
        if question is None:
            self._render_current_step()
            return

        grade = grade_free_text(question, text)
        if not grade.correct and grade.confidence < MIN_CONFIDENCE:
            # Too close to call. Asking her to tap is more respectful than
            # telling her she is wrong when she may well be right - and it does
            # not burn one of her three attempts.
            self.messages.append(render("didnt_catch", self._language))
            self._render_current_step(speak=False)
            return

        self._record_answer(question, text[:500], "text", grade)

    def _record_answer(
        self, question: RenderedQuestion, answer: str, answer_type: str, grade: Grade
    ) -> None:
        """Append the attempt, update progress, and decide what comes next."""
        progress = self.context.quiz_for(question.id)
        if progress is None:
            progress = QuizProgress(question_id=question.id)
            self.context.quiz.append(progress)

        progress.attempts += 1
        first_attempt = progress.attempts == 1

        self.db.add(
            TeachbackAttempt(
                journey_id=self.journey.id,
                question_id=question.id,
                attempt_no=progress.attempts,
                answer_type=answer_type,
                answer_value=answer,
                is_correct=grade.correct,
                grader=grade.grader,
                confidence=grade.confidence,
            )
        )
        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.TEACHBACK_ANSWERED,
            step=str(Step.TEACHBACK),
            data={
                "questionId": question.id,
                "attempt": progress.attempts,
                "correct": grade.correct,
                "grader": grade.grader,
                "firstAttempt": first_attempt,
            },
        )
        self.db.flush()

        if grade.correct:
            progress.passed = True
            progress.first_attempt_correct = first_attempt
            self.messages.append(render("correct", self._language))
            self._next_question_or_unlock(result=QuizResult(correct=True))
            return

        if progress.attempts >= MAX_ATTEMPTS:
            # Three tries and still not understood. Consent stays locked: the
            # whole point is that nobody signs what they do not understand.
            self._to_handoff(
                f"teach-back not passed after {MAX_ATTEMPTS} attempts on {question.id}",
                event_type=events.TEACHBACK_FAILED,
            )
            return

        self.messages.append(render("wrong", self._language))
        self.messages.append(question.reexplain)
        self._render_current_step(
            speak=False, quiz_result=QuizResult(correct=False, explanation=question.reexplain)
        )

    def _next_question_or_unlock(self, *, result: QuizResult | None = None) -> None:
        """Move to the next question, or unlock the agreement."""
        self.context.quiz_index += 1
        if self.context.quiz_index < len(self._questions()):
            self._render_current_step(speak=False, quiz_result=result)
            return

        self.context.teachback_passed = all(q.passed for q in self.context.quiz)
        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.TEACHBACK_PASSED,
            step=str(Step.TEACHBACK),
            data={
                "passed": self.context.quiz_passed_count,
                "total": len(self.context.quiz),
                "firstAttemptAll": all(q.first_attempt_correct for q in self.context.quiz),
            },
        )
        self._enter(Step.TERMS_CONSENT)

    def _apply_insurance(self, granted: bool) -> None:
        """TERMS_CONSENT: the separate, optional insurance choice.

        Recorded as its own consent row with `default_value=false`, which is the
        evidence that it was never pre-selected (§7.2). Insurance opt-in rate is
        a dashboard KPI precisely because a high one means someone is bundling.
        """
        self.context.insurance_granted = granted
        self.db.add(
            Consent(
                journey_id=self.journey.id,
                purpose="insurance_addon",
                granted=granted,
                default_value=False,
                method="tap",
                evidence={"step": str(self._step), "optional": True},
            )
        )
        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.CONSENT_RECORDED,
            step=str(self._step),
            data={"purpose": "insurance_addon", "granted": granted},
        )
        self.db.flush()

        self.messages.append(
            render_with_facts(
                "insurance_on" if granted else "insurance_off",
                self._language,
                self._selected_offer().facts if self._selected_offer() else {},
            )
        )
        self._render_current_step(speak=False)

    def _apply_accept_terms(self) -> None:
        """TERMS_CONSENT -> OTP, but only if teach-back actually passed.

        This is the backend guard of §9. The client disables the button, and
        this re-checks it: the disabled button is a courtesy, this is the
        control. A refusal is audited, because an `accept_terms` arriving while
        locked means either a bug or someone probing.
        """
        if not self._accept_enabled():
            events.record(
                self.db,
                journey_id=self.journey.id,
                actor=self.actor,
                event_type=events.CONSENT_LOCK_REFUSED,
                step=str(self._step),
                data={"reason": "teachback_not_passed"},
            )
            raise ConsentLocked(self._lock_reason() or "Teach-back not passed")

        self.context.terms_accepted = True
        self.db.add(
            Consent(
                journey_id=self.journey.id,
                purpose="loan_terms",
                granted=True,
                default_value=False,
                # 'tap+otp': the tap happens here and the OTP confirms it, which
                # is what the receipt records as the method.
                method="tap+otp",
                evidence={
                    "step": str(self._step),
                    "terms": self.context.terms_shown,
                    "offerId": self.journey.selected_offer_id,
                    "teachbackPassed": self.context.quiz_passed_count,
                },
            )
        )
        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.TERMS_ACCEPTED,
            step=str(self._step),
            data={"offerId": self.journey.selected_offer_id},
        )
        self.db.flush()
        self._enter(Step.OTP)

    # --- cross-cutting -------------------------------------------------------

    def _switch_language(self, language: Lang) -> None:
        """Change the journey's language and re-render in it."""
        if language == self.journey.language:
            self._render_current_step()
            return

        previous = self.journey.language
        self.journey.language = language
        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.LANGUAGE_SWITCHED,
            step=str(self._step),
            data={"from": previous, "to": language},
        )

        # At INTRO the language *was* the question, so answering it moves on.
        self._enter(Step.ASK_NEED if self._step is Step.INTRO else self._step)

    def _on_not_understood(self, *, repeat: bool = False) -> None:
        """Re-explain, and offer a human after two consecutive failures.

        `repeat=True` means the customer asked ("पुन्हा सांगा") rather than the
        rules failing, which is not confusion and does not count toward the
        streak.
        """
        if repeat:
            self._render_current_step()
            return

        self.context.confusion_streak += 1
        if self.context.confusion_streak >= CONFUSION_LIMIT:
            self._to_handoff("two consecutive turns not understood")
            return

        self.messages.append(render("didnt_catch", self._language))
        self._render_current_step(speak=False)

    def _on_question_about_terms(self, question: str = "") -> None:
        """A question about the loan rather than an answer to ours.

        A seeded explanation goes out immediately, and the route is told it may
        replace it with an answer drawn from the actual KFS clauses (§10.3). So
        the customer always gets something true, and gets something *targeted*
        when the model and the clauses can supply it.
        """
        offer = self._selected_offer()
        if offer is None:
            self._on_not_understood()
            return

        seeded = render_with_facts("explain_2", self._language, offer.facts)
        self.messages.append(seeded)
        self._generation = GenerationRequest(
            kind="kfs_answer",
            message_index=len(self.messages) - 1,
            seeded=seeded,
            facts=offer.facts,
            customer_question=question,
            search_terms=clause_search_terms(question) if question else "",
        )
        self._render_current_step(speak=False)

    def _to_handoff(self, reason: str, *, event_type: str = events.HANDOFF) -> None:
        """Any step -> HUMAN_HANDOFF.

        `needs_human`, not `abandoned`: somebody has to call this customer
        back, and the dashboard separates the two for exactly that reason.
        """
        self.journey.status = Status.NEEDS_HUMAN
        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=event_type,
            step=str(self._step),
            data={"reason": reason},
        )
        self._enter(Step.HUMAN_HANDOFF)

    # --- step entry and rendering -------------------------------------------

    def _enter(self, step: Step, *, speak: bool = True) -> None:
        """Move to a step, audit it, and build its card.

        Entering a *different* step clears the confusion streak. That is the
        only thing that clears it, and it has to be: an earlier version reset
        the streak whenever an intent was recognised, which meant a turn that
        was classified and then still went nowhere - "I have a question" at
        CONSENT_DATA, say - reset the counter it had just incremented. The
        streak could never reach two and the §13.7 escalation never fired.
        Measuring progress by the step actually changing cannot drift like that.
        """
        if str(step) != self.journey.step:
            self.context.confusion_streak = 0
        self.journey.step = str(step)
        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.STEP_ENTERED,
            step=str(step),
            data={},
        )

        # The dashboard's live table updates from this (§12). Published rather
        # than polled so finishing on the phone shows on the laptop within two
        # seconds; it never blocks and never raises, so a dashboard nobody has
        # open costs nothing.
        publish_journey_updated(
            self.journey.id,
            step=str(step),
            status=self.journey.status,
            persona_id=self.journey.persona_id,
            language=self._language,
        )

        self._render_current_step(speak=speak)

    def _render_current_step(
        self, *, speak: bool = True, quiz_result: QuizResult | None = None
    ) -> None:
        """Build the card and the spoken line for whatever step we are on.

        Rendering is a pure function of `step` + `context`, which is what makes
        resume, rescue and a mid-journey backend restart all work without any
        special handling.
        """
        step = self._step

        match step:
            case Step.INTRO:
                self._card = self._language_card()
                if speak:
                    self.messages.append(render("greet", self._language))
            case Step.ASK_NEED:
                self._card = self._amount_card()
                if speak:
                    key = "ask_amount_again" if self.context.amount_asks else "greet"
                    self.messages.append(render(key, self._language))
            case Step.CONSENT_DATA:
                self._card = self._consent_card()
                if speak:
                    self.messages.append(render("ask_consent", self._language))
            case Step.MANUAL_FORM:
                self._card = self._manual_form_card()
            case Step.PREFILL:
                self._card = self._prefill_card()
            case Step.CONFIRM_DETAILS:
                self._card = self._confirm_card()
                if speak:
                    self.messages.append(render("prefilled", self._language))
            case Step.OFFERS:
                self._render_offers(speak=speak)
            case Step.EXPLAIN_KFS:
                self._card = self._kfs_card()
                if speak and not self.context.explained:
                    self._speak_explanation()
            case Step.TEACHBACK:
                self._render_teachback(speak=speak, result=quiz_result)
            case Step.TERMS_CONSENT:
                self._card = self._consent_lock_card()
                if speak:
                    self.messages.append(render("unlocked", self._language))
            case Step.OTP:
                self._render_otp(speak=speak)
            case Step.RECEIPT | Step.DONE:
                # The receipt card is built by the route after the receipt has
                # been appended (phase 6), because its number and hash do not
                # exist until then.
                self._needs_receipt = True
                if speak:
                    self.messages.append(render("done", self._language))
            case Step.HUMAN_HANDOFF:
                self._card = HandoffCard(
                    data=HandoffCardData(
                        message=render("handoff", self._language),
                        window=HANDOFF_WINDOW,
                    )
                )
                if speak:
                    self.messages.append(render("handoff", self._language))

        self._quick_replies = self._quick_replies_for(step)

    def _render_offers(self, *, speak: bool) -> None:
        """OFFERS: assess suitability, then show the ranked list or hand off."""
        amount = self.context.amount or AMOUNT_CHIPS[1]
        offers = price_offers(self.db, amount)
        persona = self._persona()
        prefill = self.context.prefill

        decision = assess(
            amount=amount,
            tenure_months=offers[0].tenure_months if offers else 12,
            # The worst rate on offer, so affordability is tested against the
            # expensive case rather than the flattering one.
            reference_rate_pct=max((o.rate_pa for o in offers), default=21.0),
            monthly_income=prefill.monthly_income,
            existing_emi=prefill.existing_emi,
            age=persona.age if persona else None,
            language=self._language,
            income_verified=not prefill.self_declared,
        )

        self.context.foir = decision.foir
        self.context.suitable = decision.suitable
        self.context.suitability_reasons = decision.reasons
        self.context.offer_ids = [o.offer_id for o in offers]

        events.record(
            self.db,
            journey_id=self.journey.id,
            actor=self.actor,
            event_type=events.SUITABILITY_DECIDED,
            step=str(Step.OFFERS),
            data={
                "foir": decision.foir,
                "decision": decision.decision,
                "amount": amount,
            },
        )

        if not decision.suitable:
            self.messages.append(render("not_suitable", self._language))
            self._to_handoff(f"not suitable: FOIR {decision.foir_pct}%")
            return

        best = min(offers, key=lambda o: (o.total_cost, o.apr))
        self._card = OffersCard(
            data=OffersCardData(
                suitability=Suitability(
                    foirPct=decision.foir_pct,
                    decision=decision.decision,  # type: ignore[arg-type]
                    reasons=decision.reasons,
                ),
                offers=[self._offer_summary(o) for o in offers],
            )
        )
        if speak:
            self.messages.append(
                render_with_facts(
                    "offers",
                    self._language,
                    best.facts,
                    OFFER_COUNT=len(offers),
                    BEST_LENDER=best.lender,
                )
            )

    def _render_teachback(self, *, speak: bool, result: QuizResult | None) -> None:
        """TEACHBACK: the current question, with the attempt count."""
        question = self._current_question()
        if question is None:
            self.context.teachback_passed = all(q.passed for q in self.context.quiz)
            self._enter(Step.TERMS_CONSENT)
            return

        progress = self.context.quiz_for(question.id)
        self._card = QuizCard(
            data=QuizCardData(
                questionId=question.id,
                index=question.index,
                total=question.total,
                prompt=question.prompt,
                options=[QuizOption(id=o.id, text=o.text) for o in question.options],
                attempt=(progress.attempts if progress else 0) + 1,
                maxAttempts=MAX_ATTEMPTS,
                result=result,
            )
        )
        if speak and question.index == 1 and not self.context.quiz:
            self.messages.append(render("quiz_intro", self._language))

    def _render_otp(self, *, speak: bool) -> None:
        """OTP: show the sheet. The code itself is issued by the send route."""
        challenge = otp.current(self.db, self.journey.id)
        self._card = OtpCard(
            data=OtpCardData(
                expiresInSec=otp.TTL_SECONDS,
                attemptsLeft=otp.attempts_left(challenge),
            )
        )
        if speak:
            self.messages.append(render("otp", self._language))

    # --- cards ---------------------------------------------------------------

    def _language_card(self) -> Card:
        return LanguageCard(
            data=LanguageCardData(
                options=[
                    LanguageOption(language="mr-IN", label="मराठी"),
                    LanguageOption(language="hi-IN", label="हिंदी"),
                    LanguageOption(language="en-IN", label="English"),
                ]
            )
        )

    def _amount_card(self) -> Card:
        return AmountCard(
            data=AmountCardData(
                chips=list(AMOUNT_CHIPS),
                min=AMOUNT_MIN_DEFAULT,
                max=AMOUNT_MAX_DEFAULT,
            )
        )

    def _consent_card(self) -> Card:
        """Both purposes, `granted: false`, with a plain-language "why".

        The detail text names the source and what it is for. "We need your data"
        is not consent; "DigiLocker, so you do not have to type your Aadhaar" is
        something a person can actually agree or refuse.
        """
        labels: dict[Lang, dict[str, str]] = {
            "mr-IN": {
                "dl_title": "DigiLocker मधून ओळखपत्रं",
                "dl_detail": "आधार, PAN आणि पत्ता — टाइप करायची गरज नाही",
                "aa_title": "बँकेची माहिती",
                "aa_detail": "६ महिन्यांचं स्टेटमेंट, तुमची मिळकत तपासण्यासाठी",
                "why": "ही माहिती फक्त हा अर्ज भरण्यासाठी वापरली जाईल. नाही म्हटलं तरी कर्ज मिळू शकतं.",
            },
            "hi-IN": {
                "dl_title": "DigiLocker से पहचान पत्र",
                "dl_detail": "आधार, PAN और पता — टाइप करने की ज़रूरत नहीं",
                "aa_title": "बैंक की जानकारी",
                "aa_detail": "6 महीने का स्टेटमेंट, आपकी आय जाँचने के लिए",
                "why": "यह जानकारी सिर्फ़ इस आवेदन के लिए इस्तेमाल होगी। मना करने पर भी लोन मिल सकता है।",
            },
            "en-IN": {
                "dl_title": "Identity documents from DigiLocker",
                "dl_detail": "Aadhaar, PAN and address — so you need not type them",
                "aa_title": "Bank statement data",
                "aa_detail": "6 months, to verify your income",
                "why": "Used only for this application. You can still get a loan if you say no.",
            },
        }
        text = labels.get(self._language, labels["en-IN"])
        return ConsentCard(
            data=ConsentCardData(
                purposes=[
                    ConsentPurpose(
                        id="fetch_digilocker",
                        title=text["dl_title"],
                        detail=text["dl_detail"],
                    ),
                    ConsentPurpose(
                        id="fetch_account_aggregator",
                        title=text["aa_title"],
                        detail=text["aa_detail"],
                    ),
                ],
                why=text["why"],
            )
        )

    def _manual_form_card(self) -> Card:
        labels: dict[Lang, dict[str, str]] = {
            "mr-IN": {
                "fullName": "पूर्ण नाव",
                "dob": "जन्मतारीख",
                "monthlyIncome": "महिन्याची मिळकत (₹)",
                "shopAddress": "दुकानाचा पत्ता",
                "mobile": "मोबाईल नंबर",
            },
            "hi-IN": {
                "fullName": "पूरा नाम",
                "dob": "जन्म तारीख",
                "monthlyIncome": "महीने की आय (₹)",
                "shopAddress": "दुकान का पता",
                "mobile": "मोबाइल नंबर",
            },
            "en-IN": {
                "fullName": "Full name",
                "dob": "Date of birth",
                "monthlyIncome": "Monthly income (₹)",
                "shopAddress": "Shop address",
                "mobile": "Mobile number",
            },
        }
        text = labels.get(self._language, labels["en-IN"])
        kinds: dict[str, str] = {
            "fullName": "text",
            "dob": "date",
            "monthlyIncome": "number",
            "shopAddress": "text",
            "mobile": "phone",
        }
        return ManualFormCard(
            data=ManualFormCardData(
                fields=[
                    ManualFormField(
                        id=field,  # type: ignore[arg-type]
                        label=text[field],
                        kind=kinds[field],  # type: ignore[arg-type]
                        required=True,
                    )
                    for field in ("fullName", "dob", "monthlyIncome", "shopAddress", "mobile")
                ]
            )
        )

    def _prefill_card(self) -> Card:
        rows = self._get_meta("prefill_rows", [])
        return PrefillCard(
            data=PrefillCardData(
                rows=[
                    PrefillRow(
                        label=row["label"],
                        value=row["value"],
                        source=row["source"],  # type: ignore[arg-type]
                    )
                    for row in rows
                ]
            )
        )

    def _confirm_card(self) -> Card:
        labels: dict[Lang, tuple[str, str]] = {
            "mr-IN": ("दुकानाचा पत्ता", "मोबाईल नंबर"),
            "hi-IN": ("दुकान का पता", "मोबाइल नंबर"),
            "en-IN": ("Shop address", "Mobile number"),
        }
        address_label, mobile_label = labels.get(self._language, labels["en-IN"])
        prefill = self.context.prefill
        return ConfirmCard(
            data=ConfirmCardData(
                fields=[
                    ConfirmField(
                        id="shopAddress", label=address_label, value=prefill.shop_address or ""
                    ),
                    ConfirmField(id="mobile", label=mobile_label, value=prefill.mobile or ""),
                ]
            )
        )

    def _offer_summary(self, offer: PricedOffer) -> OfferSummary:
        return OfferSummary(
            offerId=offer.offer_id,
            lender=offer.lender,
            lenderType=offer.lender_type,  # type: ignore[arg-type]
            principal=offer.principal,
            tenureMonths=offer.tenure_months,
            ratePa=offer.rate_pa,
            processingFee=offer.processing_fee,
            gst=offer.gst,
            apr=offer.apr,
            emi=offer.emi,
            totalRepay=offer.total_repay,
            totalCost=offer.total_cost,
            badges=list(offer.badges),  # type: ignore[arg-type]
            kfsUrl=f"/api/kfs/{offer.kfs_document_id}/file" if offer.kfs_document_id else "",
        )

    def _kfs_card(self) -> Card | None:
        offer = self._selected_offer()
        if offer is None:
            return None
        return KfsCard(
            data=KfsCardData(
                offerId=offer.offer_id,
                lender=offer.lender,
                version=offer.kfs_version,
                lines=[KfsLine(**line) for line in kfs_lines(offer.facts, self._language)],
                pdfUrl=(f"/api/kfs/{offer.kfs_document_id}/file" if offer.kfs_document_id else ""),
            )
        )

    def _consent_lock_card(self) -> Card:
        offer = self._selected_offer()
        terms = self._terms_text(offer)
        self.context.terms_shown = terms
        return ConsentLockCard(
            data=ConsentLockCardData(
                acceptEnabled=self._accept_enabled(),
                reason=self._lock_reason(),
                terms=terms,
                insurance=InsuranceChoice(
                    premium=offer.insurance_premium if offer else 750,
                    granted=self.context.insurance_granted,
                ),
            )
        )

    def _terms_text(self, offer: PricedOffer | None) -> list[str]:
        """Exactly what the customer is agreeing to, one line per thing (§5.6).

        Stored in `consents.evidence` verbatim, so the receipt can show the
        words that were on screen rather than a later version of them.
        """
        if offer is None:
            return []
        from app.journey.templates import format_rupees

        facts = offer.facts
        per_language: dict[Lang, list[str]] = {
            "mr-IN": [
                f"{offer.lender} कडून ₹{format_rupees(facts['principal'])} कर्ज घेत आहे",
                f"दर महिन्याला ₹{format_rupees(facts['emi'])} EMI, {facts['tenure_months']} महिने",
                f"एकूण ₹{format_rupees(facts['total_repay'])} परत करणार",
                f"उशीर झाला तर ₹{format_rupees(facts['late_fee'])} दंड लागेल हे मला माहीत आहे",
                "विमा ऐच्छिक आहे आणि तो वेगळा पर्याय आहे",
            ],
            "hi-IN": [
                f"{offer.lender} से ₹{format_rupees(facts['principal'])} का लोन ले रही/रहा हूँ",
                f"हर महीने ₹{format_rupees(facts['emi'])} EMI, {facts['tenure_months']} महीने",
                f"कुल ₹{format_rupees(facts['total_repay'])} चुकाऊँगी/चुकाऊँगा",
                f"देर होने पर ₹{format_rupees(facts['late_fee'])} लेट फीस लगेगी, यह मुझे पता है",
                "बीमा वैकल्पिक है और वह अलग विकल्प है",
            ],
            "en-IN": [
                f"I am borrowing ₹{format_rupees(facts['principal'])} from {offer.lender}",
                f"I will pay ₹{format_rupees(facts['emi'])} a month for {facts['tenure_months']} months",
                f"I will repay ₹{format_rupees(facts['total_repay'])} in total",
                f"I understand a late EMI costs ₹{format_rupees(facts['late_fee'])}",
                "Insurance is optional and is a separate choice",
            ],
        }
        return per_language.get(self._language, per_language["en-IN"])

    # --- quick replies -------------------------------------------------------

    def _quick_replies_for(self, step: Step) -> list[QuickReply]:
        """The chips under the mic (§5.6).

        Always sent by the backend, never composed by the client, so the words
        the customer can tap are always in the journey's language and always
        map to an action this step accepts.
        """
        language = self._language
        chips: list[QuickReply] = []

        def tap(label: str, action: Action) -> QuickReply:
            return QuickReply(label=label, send=QuickReplySend(type="tap", action=action))

        yes_label = {"mr-IN": "हो", "hi-IN": "हाँ", "en-IN": "Yes"}[language]
        no_label = {"mr-IN": "नको", "hi-IN": "नहीं", "en-IN": "No"}[language]
        repeat_label = {
            "mr-IN": "पुन्हा सांगा",
            "hi-IN": "फिर से बताएँ",
            "en-IN": "Say that again",
        }[language]
        confused_label = {
            "mr-IN": "समजलं नाही",
            "hi-IN": "समझ नहीं आया",
            "en-IN": "I didn't understand",
        }[language]
        human_label = {
            "mr-IN": "माणसाशी बोलायचं",
            "hi-IN": "इंसान से बात",
            "en-IN": "Talk to a person",
        }[language]

        match step:
            case Step.CONSENT_DATA:
                chips.append(
                    tap(
                        yes_label,
                        ConsentsAction(
                            name="consents",
                            grants={  # type: ignore[arg-type]
                                "fetch_digilocker": True,
                                "fetch_account_aggregator": True,
                            },
                        ),
                    )
                )
                chips.append(
                    tap(
                        no_label,
                        ConsentsAction(
                            name="consents",
                            grants={  # type: ignore[arg-type]
                                "fetch_digilocker": False,
                                "fetch_account_aggregator": False,
                            },
                        ),
                    )
                )
            case Step.PREFILL:
                # Text, so it routes through the same YES handler a spoken
                # "हो" reaches - one path for tap and voice.
                chips.append(
                    QuickReply(
                        label={"mr-IN": "बरोबर आहे", "hi-IN": "सही है", "en-IN": "That's right"}[
                            language
                        ],
                        send=QuickReplySend(type="text", text=yes_label),
                    )
                )
            case Step.CONFIRM_DETAILS:
                chips.append(tap(yes_label, ConfirmDetailsAction(name="confirm_details")))
            case Step.EXPLAIN_KFS:
                # Sent as text, not as `repeat`: "I have understood, go on" is
                # an affirmative, and routing it through the same YES handler
                # the spoken word uses keeps one code path for both.
                next_label = {"mr-IN": "समजलं, पुढे", "hi-IN": "समझ गया, आगे", "en-IN": "Got it, next"}[
                    language
                ]
                chips.append(
                    QuickReply(
                        label=next_label,
                        send=QuickReplySend(type="text", text=yes_label),
                    )
                )

        if step not in (Step.DONE, Step.RECEIPT, Step.HUMAN_HANDOFF):
            chips.append(tap(repeat_label, RepeatAction(name="repeat")))
            chips.append(tap(confused_label, DidntUnderstandAction(name="didnt_understand")))
            chips.append(tap(human_label, RequestHumanAction(name="request_human")))

        return chips

    # --- helpers -------------------------------------------------------------

    @property
    def _step(self) -> Step:
        return Step(self.journey.step)

    @property
    def _language(self) -> Lang:
        return self.journey.language  # type: ignore[return-value]

    def _language_known(self) -> bool:
        """True when the client told us the language when starting."""
        return bool(self._get_meta("language_provided", False))

    def _persona(self) -> Persona | None:
        if not self.journey.persona_id:
            return None
        return self.db.get(Persona, self.journey.persona_id)

    def _current_offers(self) -> list[PricedOffer]:
        """The offers for this journey's amount. Re-priced, never cached in the
        context: the amount can change and a stale EMI is a wrong EMI."""
        amount = self.context.amount
        if amount is None:
            return []
        return price_offers(self.db, amount)

    def _selected_offer(self) -> PricedOffer | None:
        if not self.journey.selected_offer_id:
            return None
        return next(
            (o for o in self._current_offers() if o.offer_id == self.journey.selected_offer_id),
            None,
        )

    def _kfs_document(self, offer: PricedOffer) -> KfsDocument | None:
        if not offer.kfs_document_id:
            return None
        return self.db.get(KfsDocument, uuid.UUID(offer.kfs_document_id))

    def _questions(self) -> list[RenderedQuestion]:
        """The three questions, rendered with the selected offer's facts."""
        offer = self._selected_offer()
        facts = offer.facts if offer else {}
        rows = active_questions(self.db)
        return [
            render_question(question, self._language, facts, index + 1, len(rows))
            for index, question in enumerate(rows)
        ]

    def _current_question(self) -> RenderedQuestion | None:
        questions = self._questions()
        index = self.context.quiz_index
        return questions[index] if 0 <= index < len(questions) else None

    def _accept_enabled(self) -> bool:
        """The consent lock (§9): every question passed, and nothing else."""
        questions = self._questions()
        if not questions:
            return False
        return all(
            (progress := self.context.quiz_for(q.id)) is not None and progress.passed
            for q in questions
        )

    def _lock_reason(self) -> str | None:
        if self._accept_enabled():
            return None
        return render("locked", self._language)

    def _get_meta(self, key: str, default: Any) -> Any:
        """Read engine bookkeeping stored outside the typed context.

        `JourneyContext` is `extra="forbid"` by design, so render-only data
        (the prefill rows, the language flag) lives in a sibling `_meta` key of
        the same JSONB column rather than widening the typed model with fields
        no transition reads.
        """
        meta = (self.journey.context or {}).get("_meta") or {}
        return meta.get(key, default)

    def _set_meta(self, key: str, value: Any) -> None:
        stored = dict(self.journey.context or {})
        meta = dict(stored.get("_meta") or {})
        meta[key] = value
        stored["_meta"] = meta
        self.journey.context = stored

    def finish(self, *, user_message: str | None = None, record_turn: bool = True) -> EngineResult:
        """Persist the context and build the response.

        Public because two routes legitimately re-render after doing work the
        engine cannot: `PREFILL` runs the async adapters, and OTP verification
        happens on its own route. Both then need the response rebuilt from the
        state they just changed.
        """
        stored = dict(self.journey.context or {})
        stored.update(self.context.model_dump(mode="json"))
        self.journey.context = stored

        if record_turn:
            self.context.turn_no += 1
            stored["turn_no"] = self.context.turn_no
            self.journey.context = stored
            self.journey.last_activity_at = datetime.now(UTC)

        if self._step is Step.HUMAN_HANDOFF:
            self.journey.status = Status.NEEDS_HUMAN

        self.db.flush()

        response = TurnResponse(
            journeyId=self.journey.id,
            version=self.journey.version,
            step=str(self.journey.step),
            status=self._wire_status(),
            progress=self._progress(),
            language=self._language,
            messages=self._wire_messages(user_message),
            card=self._card,
            quickReplies=self._quick_replies,
            locks=Locks(acceptEnabled=self._accept_enabled(), reason=self._lock_reason()),
            demoMode=not self.settings.sarvam_configured,
        )
        return EngineResult(
            response=response,
            assistant_messages=list(self.messages),
            user_message=user_message,
            needs_receipt=self._needs_receipt,
            generation=self._generation,
        )

    def _wire_status(self) -> str:
        """`abandoned` is internal: a client that is talking to us is not gone.

        The rescue scheduler sets it while nobody is looking, and if that
        customer comes back the journey is active again - so the wire only ever
        carries the three states a client can act on.
        """
        status = self.journey.status
        if status == Status.ABANDONED:
            return "active"
        return status

    def _progress(self) -> Progress:
        progress = progress_for(self._step, self._language)
        return Progress(index=progress.index, label=progress.label, etaSeconds=progress.etaSeconds)

    def _wire_messages(self, user_message: str | None) -> list[Message]:
        """The bubbles for this turn: the customer's, then the assistant's.

        `audioUrl` is filled in by phase 7; the ids are deterministic per turn
        so a client can key a list on them without re-animating on resume.
        """
        messages: list[Message] = []
        turn = self.context.turn_no
        if user_message:
            messages.append(
                Message(id=f"{self.journey.id}:{turn}:u", role="user", text=user_message)
            )
        for index, text in enumerate(self.messages):
            if text:
                messages.append(
                    Message(
                        id=f"{self.journey.id}:{turn}:a{index}",
                        role="assistant",
                        text=text,
                    )
                )
        return messages

    def name_honorific(self) -> str:
        """`{NAME_HONORIFIC}` for this journey's persona, used by the rescue call."""
        persona = self._persona()
        if persona is None:
            return ""
        return honorific(persona.name_local or {}, self._language)


class ConsentLocked(Exception):
    """`accept_terms` or OTP reached the engine before teach-back passed.

    Raised rather than returned so the route can answer 409 `consent_locked`
    (§8.1) without every call site having to check for it.
    """
