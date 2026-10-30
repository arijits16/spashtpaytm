"""Speech templates and placeholder filling (build plan §7.4, §10.5).

Every line the assistant says on the golden path comes from
`journey/templates/<lang>.json` with `{PLACEHOLDER}`s filled from the selected
offer's KFS facts. Nothing is concatenated from numbers at the call site.

That is not a style preference. The Number Guard (§10.5) can only certify that a
figure was never invented if there is exactly one route from a fact to spoken
text, and this is it. A template line is *pre-approved*: the guard checks
LLM-generated text, not these.

Numbers are formatted for Indian reading - ₹55,200 with the lakh grouping -
because that is how the figure will be said aloud and how it appears on the card.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

from app.journey.states import DEFAULT_LANGUAGE, LANGUAGES, Lang

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_PLACEHOLDER_RE = re.compile(r"\{([A-Z_]+)\}")


def format_rupees(value: int | float) -> str:
    """Indian digit grouping without the symbol: `55200` -> `55,200`.

    The ₹ lives in the template so a line can say "₹{EMI}" or "{EMI} रुपये"
    depending on what reads naturally in that language.
    """
    whole = round(value)
    text = str(abs(whole))
    if len(text) > 3:
        head, tail = text[:-3], text[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        text = ",".join(groups) + "," + tail
    return ("-" if whole < 0 else "") + text


@functools.lru_cache(maxsize=4)
def load(language: str) -> dict[str, str]:
    """Load one language's templates, cached for the process lifetime.

    An unknown language falls back to Marathi, the default journey language,
    rather than raising: a missing line must degrade to the wrong language, not
    to a 500 in the middle of a demo.
    """
    code = language if language in LANGUAGES else DEFAULT_LANGUAGE
    path = TEMPLATE_DIR / f"{code}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def placeholders_from_facts(facts: dict[str, Any]) -> dict[str, str]:
    """Build the substitution map from an offer's fact dict.

    Money is grouped, rates keep two decimals, and the foreclosure percentage
    drops its decimal because "4%" is what the KFS says and what a person says.
    """
    values: dict[str, str] = {}

    for key in (
        "principal",
        "emi",
        "total_repay",
        "total_interest",
        "total_cost",
        "processing_fee",
        "gst",
        "net_disbursed",
        "late_fee",
        "insurance_premium",
    ):
        if facts.get(key) is not None:
            values[key.upper()] = format_rupees(facts[key])

    if facts.get("tenure_months") is not None:
        values["TENURE"] = str(facts["tenure_months"])
    if facts.get("cooling_off_days") is not None:
        values["COOLING_OFF_DAYS"] = str(facts["cooling_off_days"])
    if facts.get("rate_pa") is not None:
        values["RATE_PA"] = f"{float(facts['rate_pa']):.2f}"
    if facts.get("apr") is not None:
        values["APR"] = f"{float(facts['apr']):.2f}"
    if facts.get("foreclosure_pct") is not None:
        values["FORECLOSURE_PCT"] = f"{float(facts['foreclosure_pct']):g}"
    if facts.get("lender"):
        values["LENDER"] = str(facts["lender"])

    return values


def render(key: str, language: Lang, **extra: object) -> str:
    """Render one template line.

    @param key    A key from `journey/templates/<lang>.json`.
    @param extra  Placeholder values, as `EMI="4,600"` or a fact dict spread in.

    An unfilled placeholder is dropped rather than left as `{EMI}`: showing a
    customer literal braces is worse than showing a slightly shorter sentence,
    and the tests assert that golden-path lines are fully filled.
    """
    line = load(language).get(key)
    if line is None:
        return ""

    for name, value in extra.items():
        line = line.replace("{" + name.upper() + "}", str(value))

    return _PLACEHOLDER_RE.sub("", line).replace("  ", " ").strip()


def render_with_facts(key: str, language: Lang, facts: dict[str, Any], **extra: object) -> str:
    """Render a line from an offer's facts, with optional overrides."""
    values = placeholders_from_facts(facts)
    values.update({name.upper(): str(value) for name, value in extra.items()})
    return render(key, language, **values)


def honorific(name_local: dict[str, Any], language: Lang) -> str:
    """Build `{NAME_HONORIFIC}` from a persona's local name (§7.4).

    mr: "सुनीता ताई" / "रमेश दादा", hi: "सुनीता जी", en: the plain first name.
    Composed by code rather than seeded because the suffix depends on both the
    language and the persona's gender, and getting it wrong is the kind of small
    rudeness that undoes everything else the product is trying to do.
    """
    short = "mr" if language == "mr-IN" else "hi" if language == "hi-IN" else "en"
    if short == "en":
        return str(name_local.get("en") or name_local.get("hi") or "")

    base = str(name_local.get(short) or "")
    suffix = (name_local.get("honorific") or {}).get(short, "")
    return f"{base} {suffix}".strip() if base else ""


def fill_question(template: dict[str, Any], language: Lang, facts: dict[str, Any]) -> str:
    """Fill a teach-back prompt / option / re-explanation in one language."""
    text = template.get(language) or template.get("en-IN") or ""
    values = placeholders_from_facts(facts)
    for name, value in values.items():
        text = text.replace("{" + name + "}", value)
    return _PLACEHOLDER_RE.sub("", text).strip()
