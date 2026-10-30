"""Pre-generate the voice for every template line (`make tts-cache`, plan §10.2).

What this buys: on the golden path every line the assistant says is a template
(§7.4), so after this has run the whole journey speaks from disk. No Sarvam call
on the critical path, no network dependency during the demo, and each line plays
instantly instead of costing a second of the 4-second budget (§10.4).

It is also the thing that makes demo mode worth having. With the key removed or
the venue Wi-Fi down, `demo_mode_active` is true and nothing is synthesised -
but the cached files are still served, so the journey still *talks* (§10.6).

Run it for the golden persona in all three languages:

    make tts-cache

Costs money and API quota, so it skips anything already cached unless you pass
`--force`.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.ai.tts import CACHE_DIR, cache_key, is_cached, synthesise  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.journey.offers import price_offers  # noqa: E402
from app.journey.states import LANGUAGES, Lang  # noqa: E402
from app.journey.teachback import active_questions  # noqa: E402
from app.journey.teachback import render as render_question  # noqa: E402
from app.journey.templates import load, render_with_facts  # noqa: E402

# Lines that take `{PLACEHOLDER}`s needing figures from an offer. The rest are
# static and render with no substitution.
_NEEDS_FACTS = {
    "explain_1",
    "explain_2",
    "explain_3",
    "offers",
    "insurance_on",
    "amount_out_of_range",
}

# `{NAME_HONORIFIC}` is per-persona; the rescue line is cached with the golden
# persona's honorific, which is the one the demo uses.
_NEEDS_NAME = {"rescue_call"}


def lines_for(language: Lang, facts: dict, honorific: str) -> list[tuple[str, str]]:
    """Every (key, text) worth caching in one language.

    The teach-back prompts, options and re-explanations are included as well as
    the templates: a customer who taps "read this to me" on a question needs
    audio, and a re-explanation is exactly the moment someone is struggling to
    read.
    """
    templates = load(language)
    items: list[tuple[str, str]] = []

    for key in sorted(templates):
        extra: dict[str, object] = {}
        if key in _NEEDS_FACTS:
            extra = {
                "OFFER_COUNT": 3,
                "BEST_LENDER": facts.get("lender", ""),
                "MIN": "10,000",
                "MAX": "2,00,000",
            }
        if key in _NEEDS_NAME:
            extra = {"NAME_HONORIFIC": honorific}

        text = render_with_facts(key, language, facts, **extra)
        if text:
            items.append((key, text))

    with SessionLocal() as db:
        for index, question in enumerate(active_questions(db), start=1):
            rendered = render_question(question, language, facts, index, 3)
            items.append((f"{question.id}.prompt", rendered.prompt))
            items.append((f"{question.id}.reexplain", rendered.reexplain))
            for option in rendered.options:
                items.append((f"{question.id}.{option.id}", option.text))

    return [(key, text) for key, text in items if text.strip()]


async def warm(languages: list[Lang], *, force: bool) -> int:
    """Synthesise everything. Returns the number of failures."""
    from app.journey.templates import honorific as build_honorific

    with SessionLocal() as db:
        from app.db.models.persona import Persona

        persona = db.get(Persona, "sunita")
        offers = price_offers(db, 50_000)

    if not offers:
        print("no offers in the database. Run `make migrate && make seed` first.")
        return 1

    # The cheapest offer, which is the one the golden path selects.
    best = min(offers, key=lambda offer: (offer.total_cost, offer.apr))
    facts = dict(best.facts)

    print(f"==> cache: {CACHE_DIR}")
    print(f"    offer: {best.lender} (EMI {best.emi}, APR {best.apr})")
    if not settings.sarvam_api_key:
        print("    SARVAM_API_KEY is not set - nothing can be synthesised.")
        print("    The journey still works: lines show as text only (section 10.6).")
        return 1

    failures = 0
    for language in languages:
        name = build_honorific(
            (persona.name_local if persona else {}) or {}, language
        )
        items = lines_for(language, facts, name)
        print(f"\n==> {language}: {len(items)} line(s)")

        for key, text in items:
            cached = is_cached(cache_key(text, language, settings))
            if cached and not force:
                print(f"    = {key}")
                continue

            url = await synthesise(text, language, settings, force=force)
            if url:
                print(f"    + {key}")
            else:
                print(f"    ! {key}  (no audio)")
                failures += 1

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--language",
        action="append",
        choices=list(LANGUAGES),
        help="only this language (repeatable). Default: all three.",
    )
    parser.add_argument(
        "--force", action="store_true", help="re-synthesise even on a cache hit"
    )
    args = parser.parse_args()

    languages: list[Lang] = args.language or list(LANGUAGES)
    failures = asyncio.run(warm(languages, force=args.force))

    if failures:
        print(f"\n==> finished with {failures} line(s) missing audio")
        print("    Those lines will show as text only, which is a working fallback.")
        return 1

    print("\n==> every template line is cached. The golden path speaks offline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
