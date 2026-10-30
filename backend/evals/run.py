"""The eval suite (`make eval`, build plan §10.7).

Four things are measured, and they are the four things that can quietly stop
working without any test going red:

1. **Understanding** - 54 utterances in mr/hi/en and code-mixed, against the
   rules alone. The target is >= 90% on golden-path cases (§10.7).
2. **Teach-back grading** - right and wrong answers, phrased as a customer
   would phrase them rather than as the seed file does.
3. **The Number Guard** - the §10.5 cases, including the evasions.
4. **Prompt injection** - §13.7. Asserts that an injected instruction changes
   nothing, which it cannot, because the guard and the schema do not care what
   the model was told.

Writes `docs/EVAL.md`. Run it after changing a lexicon, a rubric or the guard:
these are the changes that improve one case and silently break four.

Rules-only by default, so it is free, offline and deterministic. `--llm` adds
the model fallback for the cases the rules miss, which is what the fallback
exists for.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.ai import number_guard  # noqa: E402
from app.ai.llm import wrap_customer_text  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.journey.offers import price_offers  # noqa: E402
from app.journey.teachback import (  # noqa: E402
    MIN_CONFIDENCE,
    active_questions,
    grade_free_text,
)
from app.journey.teachback import render as render_question  # noqa: E402
from app.journey.understand_rules import clause_search_terms, understand  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
DOCS_DIR = BACKEND_DIR.parent / "docs"

# §10.7: the bar for golden-path cases.
TARGET_PASS_RATE = 0.90


@dataclass
class Suite:
    """One section's results."""

    name: str
    passed: int = 0
    failed: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def record(self, ok: bool, detail: dict[str, Any]) -> None:
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            self.failures.append(detail)


def load(name: str) -> list[dict[str, Any]]:
    path = EVAL_DIR / f"{name}.jsonl"
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# --- 1. understanding -------------------------------------------------------


async def run_understanding(*, use_llm: bool) -> Suite:
    suite = Suite("Understanding")

    for row in load("utterances"):
        result = understand(
            row["text"],
            step_expects_amount=row.get("step_expects_amount", False),
            lender_names=tuple(row.get("lender_names", [])),
        )

        # The LLM fallback is only consulted where the rules were unsure, which
        # is exactly how the engine uses it (§10.3).
        if use_llm and not result.confident:
            from app.ai.understand_llm import understand_with_llm

            enriched = await understand_with_llm(
                row["text"],
                row["language"],
                settings,
                step="EVAL",
            )
            if enriched is not None and enriched.confident:
                result = enriched

        problems: list[str] = []
        if result.intent.value != row["expected_intent"]:
            problems.append(f"intent {result.intent.value} != {row['expected_intent']}")
        if "expected_amount" in row and result.amount != row["expected_amount"]:
            problems.append(f"amount {result.amount} != {row['expected_amount']}")
        if "expected_purpose" in row and result.purpose != row["expected_purpose"]:
            problems.append(f"purpose {result.purpose} != {row['expected_purpose']}")
        if "expected_offer_hint" in row and result.offer_hint != row["expected_offer_hint"]:
            problems.append(f"offer {result.offer_hint} != {row['expected_offer_hint']}")
        if "expected_language" in row and result.language != row["expected_language"]:
            problems.append(f"language {result.language} != {row['expected_language']}")

        # A question about the terms also has to reach the right clause, or the
        # KFS answering path (§10.3) answers the wrong question correctly.
        if "expected_clause" in row:
            terms = clause_search_terms(row["text"])
            if not _clause_matches(row["expected_clause"], terms):
                problems.append(f"clause terms did not point at {row['expected_clause']}")

        suite.record(
            not problems,
            {
                "text": row["text"],
                "language": row["language"],
                "problems": problems,
                "code_mixed": row.get("code_mixed", False),
            },
        )

    return suite


# Which search terms count as pointing at a clause.
_CLAUSE_HINTS = {
    "late_fee": "late fee",
    "foreclosure": "foreclosure",
    "cooling_off": "cooling off",
    "insurance_optional": "insurance optional",
    "processing_fee": "processing fee",
    "interest_rate": "interest rate",
    "emi_schedule": "repayment schedule",
    "grievance": "grievance",
    "recovery": "recovery",
}


def _clause_matches(clause_key: str, terms: str) -> bool:
    hint = _CLAUSE_HINTS.get(clause_key)
    return bool(hint) and hint in terms


# --- 2. teach-back grading --------------------------------------------------


def run_grading() -> Suite:
    suite = Suite("Teach-back grading")

    with SessionLocal() as db:
        offers = price_offers(db, 50_000)
        if not offers:
            suite.record(False, {"problems": ["no offers seeded; run `make seed`"]})
            return suite
        facts = min(offers, key=lambda offer: offer.total_cost).facts
        questions = {question.id: question for question in active_questions(db)}

        for row in load("teachback"):
            question = questions.get(row["question_id"])
            if question is None:
                suite.record(False, {"problems": [f"unknown question {row['question_id']}"]})
                continue

            rendered = render_question(question, row["language"], facts, 1, 3)
            grade = grade_free_text(rendered, row["text"])

            # An uncertain verdict counts as correct-if-expected-correct only
            # when it is confident enough to act on; below the threshold the
            # engine asks for a tap, which is neither a pass nor a failure of
            # the grader.
            expected = row["expected_correct"]
            uncertain = not grade.correct and grade.confidence < MIN_CONFIDENCE
            ok = grade.correct == expected or (uncertain and not expected)

            suite.record(
                ok,
                {
                    "text": row["text"],
                    "language": row["language"],
                    "problems": [
                        f"graded {grade.correct} (confidence {grade.confidence:.2f}), "
                        f"expected {expected}"
                    ],
                },
            )

    return suite


# --- 3. the Number Guard ----------------------------------------------------


def run_guard() -> Suite:
    suite = Suite("Number Guard")

    with SessionLocal() as db:
        offers = price_offers(db, 50_000)
        if not offers:
            suite.record(False, {"problems": ["no offers seeded; run `make seed`"]})
            return suite
        facts = min(offers, key=lambda offer: offer.total_cost).facts

    for row in load("guard"):
        verdict = number_guard.check(
            row["text"],
            offers=[facts],
            customer={"amount": 50_000, "monthly_income": 28_400, "foir_pct": 16.4},
        )
        ok = verdict.allowed == row["allowed"]
        suite.record(
            ok,
            {
                "text": row["text"],
                "problems": [
                    f"{'allowed' if verdict.allowed else 'blocked'}, "
                    f"expected {'allowed' if row['allowed'] else 'blocked'}"
                    f" ({row['note']})"
                ],
            },
        )

    return suite


# --- 4. prompt injection ----------------------------------------------------


def run_injection() -> Suite:
    """§13.7: an injected instruction must change nothing.

    Checked without a model, because the defences being tested are not the
    model's: the customer's text is wrapped as data and cannot close its own
    tag, and any number it tries to plant is blocked by the guard unless it
    happens to be a real fact. Those two hold whatever the model decides to do.
    """
    suite = Suite("Prompt injection")

    with SessionLocal() as db:
        offers = price_offers(db, 50_000)
        facts = min(offers, key=lambda offer: offer.total_cost).facts if offers else {}

    for row in load("injection"):
        problems: list[str] = []

        wrapped = wrap_customer_text(row["text"])
        if "</customer_said>" in wrapped[: -len("\n</customer_said>")]:
            problems.append("the text was able to close its own data tag")

        # If a model did repeat the injected number, the guard stops it.
        for fragment in row["must_not_contain"]:
            if any(ch.isdigit() for ch in fragment):
                verdict = number_guard.check(f"EMI {fragment} आहे.", offers=[facts])
                if verdict.allowed:
                    problems.append(f"the guard would have let '{fragment}' through")

        # The rules never treat an injection as an instruction *to us*. An
        # injected number may well be read as an amount - "the EMI is 50" does
        # contain a number, and reading a bare figure as an amount is intended
        # shorthand (§7.5) - which is harmless: an amount is a slot the engine
        # validates, not a command, and the figure still has to pass the guard
        # before it can be spoken back.
        understood = understand(row["text"])
        forbidden = {"yes", "want_human", "switch_language"}
        if understood.intent.value in forbidden:
            problems.append(f"an injection was classified as {understood.intent.value}")

        suite.record(not problems, {"text": row["text"], "problems": problems})

    return suite


# --- reporting --------------------------------------------------------------


def write_report(suites: list[Suite], *, used_llm: bool) -> Path:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    path = DOCS_DIR / "EVAL.md"

    total_passed = sum(suite.passed for suite in suites)
    total = sum(suite.total for suite in suites)
    overall = total_passed / total if total else 0.0

    lines = [
        "# Evaluation results",
        "",
        f"Generated by `make eval` on {datetime.now(UTC).strftime('%d %b %Y, %H:%M UTC')}.",
        "",
        f"Mode: **{'rules + LLM fallback' if used_llm else 'rules only'}**"
        + ("" if used_llm else " (free, offline, deterministic)"),
        "",
        f"## Overall: {total_passed}/{total} ({overall:.0%})",
        "",
        f"Target for golden-path cases is {TARGET_PASS_RATE:.0%} (build plan section 10.7).",
        "",
        "| Suite | Passed | Total | Rate |",
        "|---|---:|---:|---:|",
    ]

    for suite in suites:
        verdict = "OK" if suite.rate >= TARGET_PASS_RATE else "below target"
        lines.append(
            f"| {suite.name} | {suite.passed} | {suite.total} | {suite.rate:.0%} ({verdict}) |"
        )

    for suite in suites:
        if not suite.failures:
            continue
        lines += ["", f"## {suite.name}: what failed", ""]
        for failure in suite.failures:
            text = failure.get("text", "")
            problems = "; ".join(failure.get("problems", []))
            marker = " *(code-mixed)*" if failure.get("code_mixed") else ""
            lines.append(f"- `{text}`{marker} — {problems}")

    lines += [
        "",
        "## What these measure",
        "",
        "- **Understanding** — the rule lexicons of section 7.5 against real "
        "utterances in Marathi, Hindi, English and code-mixed speech. These are "
        "what carry the golden path with no model call at all.",
        "- **Teach-back grading** — answers phrased as a customer would phrase "
        "them, not as the seed file does. A low rate here means the rubrics are "
        "too narrow, and the consequence is telling someone they misunderstood "
        "their loan when they did not.",
        "- **Number Guard** — section 10.5, including the evasions: Devanagari "
        "digits, multiplier words, and rounding.",
        "- **Prompt injection** — section 13.7. Passing does not depend on the "
        "model behaving: the customer's text cannot escape its data tag, and any "
        "planted figure is blocked unless it is a real fact.",
        "",
    ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def main_async(*, use_llm: bool) -> int:
    suites = [
        await run_understanding(use_llm=use_llm),
        run_grading(),
        run_guard(),
        run_injection(),
    ]

    path = write_report(suites, used_llm=use_llm)

    print(f"==> {path.relative_to(BACKEND_DIR.parent)}")
    for suite in suites:
        flag = " " if suite.rate >= TARGET_PASS_RATE else "!"
        print(f"  {flag} {suite.name:22} {suite.passed:>3}/{suite.total:<3} {suite.rate:>5.0%}")
        for failure in suite.failures[:5]:
            print(
                f"      - {failure.get('text', '')[:52]}  {'; '.join(failure.get('problems', []))[:60]}"
            )

    below = [suite.name for suite in suites if suite.rate < TARGET_PASS_RATE]
    if below:
        print(f"\n==> below the {TARGET_PASS_RATE:.0%} target: {', '.join(below)}")
        return 1

    print(f"\n==> every suite is at or above the {TARGET_PASS_RATE:.0%} target")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--llm",
        action="store_true",
        help="also use the LLM fallback for utterances the rules cannot place",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(use_llm=args.llm))


if __name__ == "__main__":
    raise SystemExit(main())
