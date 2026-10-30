"""Rule-based understanding (build plan §7.5).

The golden path should never need an LLM. Every utterance it contains - "हो",
"50 हजार", "समजलं नाही", "पहिला" - is matched here by lexicon and regex, which
is faster than a model call, free, works with the venue Wi-Fi down, and is
reviewable by a native speaker reading one file.

Phase 8 adds `understand_llm.py` as a *fallback* for the cases these rules
return `OTHER` on. The order is deliberate: rules first means the demo's
critical path has no model in it, and the LLM only ever sees the long tail.

**Code-mixing is the normal case, not an edge case.** Someone speaking Marathi
in Mumbai says "mujhe loan chahiye for machine". So the lexicons are checked
together rather than per language, and the match is on a normalised, accent- and
script-tolerant form of the text.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from app.journey.states import Lang

# Devanagari digits, in order, so ०-९ can be translated to ASCII.
_DEVANAGARI_DIGITS = "०१२३४५६७८९"
_DIGIT_MAP = str.maketrans(_DEVANAGARI_DIGITS, "0123456789")


class Intent(StrEnum):
    """What the customer meant. Mirrors the LLM's `intent` enum (§10.3) so the
    rule path and the model path produce the same thing."""

    PROVIDE_NEED = "provide_need"
    YES = "yes"
    NO = "no"
    CHOOSE_OFFER = "choose_offer"
    ANSWER_QUIZ = "answer_quiz"
    DIDNT_UNDERSTAND = "didnt_understand"
    WANT_HUMAN = "want_human"
    SWITCH_LANGUAGE = "switch_language"
    QUESTION_ABOUT_TERMS = "question_about_terms"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Understanding:
    """What we extracted. Everything but `intent` is optional by nature.

    `confident` is False when the rules fell through to `OTHER`: the caller
    uses it to decide whether to ask the LLM (phase 8) or to re-prompt.
    """

    intent: Intent
    amount: int | None = None
    purpose: str | None = None
    offer_hint: str | None = None
    language: Lang | None = None
    raw: str = ""
    confident: bool = True


# --- lexicons (§7.5) ---------------------------------------------------------
#
# Latin transliterations sit alongside the Devanagari because a customer typing
# on a phone keyboard writes "nahi", and an STT engine sometimes returns it too.

YES_WORDS = (
    "हो",
    "होय",
    "हां",
    "हाँ",
    "चालेल",
    "ठीक आहे",
    "ठीक है",
    "बरोबर",
    "सही",
    "जी",
    "ho",
    "hoy",
    "haan",
    "han",
    "ji",
    "yes",
    "yeah",
    "yep",
    "ok",
    "okay",
    "sure",
    "correct",
    "theek",
    "chalel",
)

NO_WORDS = (
    "नाही",
    "नको",
    "नहीं",
    "ना",
    "मत",
    "nahi",
    "nahin",
    "nako",
    "na",
    "no",
    "nope",
    "dont",
    "don't",
    "mat",
)

DIDNT_UNDERSTAND_WORDS = (
    "समजलं नाही",
    "समजले नाही",
    "कळलं नाही",
    "कळले नाही",
    "पुन्हा सांगा",
    "समझ नहीं आया",
    "समझ नहीं",
    "फिर से बताओ",
    "फिर से",
    "दोबारा",
    "samajla nahi",
    "samjhe nahi",
    "samajh nahi",
    "punha sanga",
    "phir se",
    "dobara",
    "didnt understand",
    "did not understand",
    "repeat",
    "again",
    "what",
    "pardon",
    "come again",
)

HUMAN_WORDS = (
    "माणसाशी बोलायचं",
    "माणसाशी",
    "एजंट",
    "इंसान से बात",
    "इंसान",
    "एजेंट",
    "manasashi",
    "agent",
    "human",
    "person",
    "insaan",
    "representative",
    "someone real",
    "talk to a person",
)

# Asking the assistant to switch, e.g. "हिंदी में बोलो".
_LANGUAGE_WORDS: dict[Lang, tuple[str, ...]] = {
    "mr-IN": ("मराठी", "marathi", "marathit"),
    "hi-IN": ("हिंदी", "हिन्दी", "hindi", "hindi me", "hindi mein"),
    "en-IN": ("इंग्रजी", "अंग्रेज़ी", "english", "angrezi", "ingrji"),
}

# A question about the terms rather than an answer to ours. Routed to the KFS
# question-answering path in phase 8; until then it triggers a re-explanation.
_TERMS_QUESTION_WORDS = (
    "किती",
    "कसं",
    "काय होईल",
    "लागेल का",
    "कितना",
    "कैसे",
    "क्या होगा",
    "लगेगा",
    "how much",
    "what if",
    "what happens",
    "will i",
    "charge",
    "fee",
    "fine",
    "दंड",
    "शुल्क",
    "जुर्माना",
    "चार्ज",
    "फी",
    "फीस",
    "व्याज",
    "ब्याज",
    "interest",
)

# "the cheapest one" - the offer choice that is a judgement, not a name (§7.5).
_CHEAPEST_WORDS = (
    "सगळ्यात स्वस्त",
    "सर्वात स्वस्त",
    "स्वस्त",
    "सबसे सस्ता",
    "सस्ता",
    "cheapest",
    "lowest total",
    "best value",
    "sabse sasta",
    "swast",
)

# Ordinal and letter ways of naming an offer, mapped to a position.
_ORDINALS: dict[str, int] = {
    "पहिला": 0,
    "पहिली": 0,
    "पहिले": 0,
    "पहला": 0,
    "पहली": 0,
    "first": 0,
    "pahila": 0,
    "pehla": 0,
    "one": 0,
    "a": 0,
    "दुसरा": 1,
    "दुसरी": 1,
    "दूसरा": 1,
    "दूसरी": 1,
    "second": 1,
    "dusra": 1,
    "two": 1,
    "b": 1,
    "तिसरा": 2,
    "तिसरी": 2,
    "तीसरा": 2,
    "तीसरी": 2,
    "third": 2,
    "tisra": 2,
    "three": 2,
    "c": 2,
}

# Multipliers. The spelling varies by script and by transliteration, and getting
# this wrong turns a 50,000 loan into a 50 one.
_MULTIPLIERS: tuple[tuple[tuple[str, ...], int], ...] = (
    (("लाख", "lakh", "lac", "lakhs"), 100_000),
    (("हजार", "हज़ार", "हजारो", "hazaar", "hajar", "hazar", "thousand", "k"), 1_000),
)

# Spelled-out numbers that matter for amounts. Not a general number parser:
# only the words a loan amount is actually said with.
_NUMBER_WORDS: dict[str, int] = {
    "एक": 1,
    "ek": 1,
    "one": 1,
    "दोन": 2,
    "दो": 2,
    "don": 2,
    "do": 2,
    "two": 2,
    "तीन": 3,
    "teen": 3,
    "three": 3,
    "चार": 4,
    "char": 4,
    "four": 4,
    "पाच": 5,
    "पांच": 5,
    "पाँच": 5,
    "paach": 5,
    "paanch": 5,
    "five": 5,
    "दहा": 10,
    "दस": 10,
    "daha": 10,
    "das": 10,
    "ten": 10,
    "पंधरा": 15,
    "पंद्रह": 15,
    "pandhra": 15,
    "pandrah": 15,
    "fifteen": 15,
    "वीस": 20,
    "बीस": 20,
    "vees": 20,
    "bees": 20,
    "twenty": 20,
    "पंचवीस": 25,
    "पच्चीस": 25,
    "pachvees": 25,
    "pachchis": 25,
    "twentyfive": 25,
    "तीस": 30,
    "tees": 30,
    "thirty": 30,
    "चाळीस": 40,
    "चालीस": 40,
    "chalees": 40,
    "forty": 40,
    "पन्नास": 50,
    "पचास": 50,
    "pannas": 50,
    "pachas": 50,
    "fifty": 50,
    "साठ": 60,
    "saath": 60,
    "sixty": 60,
    "पंच्याहत्तर": 75,
    "पचहत्तर": 75,
    "seventyfive": 75,
    "शंभर": 100,
    "सौ": 100,
    "shambhar": 100,
    "sau": 100,
    "hundred": 100,
}

# What the money is for. Used verbatim as `purpose` and never interpreted
# further - the product does not price by purpose, it just records it.
_PURPOSE_WORDS: dict[str, tuple[str, ...]] = {
    "machine": ("मशीन", "शिलाई मशीन", "शिवणयंत्र", "machine", "sewing", "silai"),
    "shop": ("दुकान", "दुकानासाठी", "shop", "dukan", "business", "व्यवसाय", "धंदा"),
    "education": ("शिक्षण", "फी", "पढाई", "education", "school", "college", "fees"),
    "medical": ("दवाखाना", "इलाज", "औषध", "medical", "hospital", "treatment"),
    "home": ("घर", "घरासाठी", "home", "house", "ghar", "repair", "दुरुस्ती"),
    "wedding": ("लग्न", "शादी", "wedding", "marriage", "lagna", "shaadi"),
}


def normalise(text: str) -> str:
    """Fold a raw utterance into something matchable.

    NFKC first, so visually identical Devanagari written with different code
    points compares equal; then Devanagari digits to ASCII; then commas inside
    numbers away, so "५०,०००" and "50000" are the same token.
    """
    folded = unicodedata.normalize("NFKC", text).strip().lower()
    folded = folded.translate(_DIGIT_MAP)
    folded = re.sub(r"(?<=\d)[,\s](?=\d)", "", folded)
    return re.sub(r"\s+", " ", folded)


def _contains_any(haystack: str, needles: tuple[str, ...]) -> bool:
    """Substring match, which is right for these languages.

    Marathi and Hindi agglutinate postpositions onto the word ("दुकानासाठी" =
    "दुकान" + "साठी"), so a whole-word match would miss most real sentences. The
    risk of a false positive on a short needle is handled by checking the
    specific lexicons before the general ones.
    """
    return any(needle in haystack for needle in needles)


def parse_amount(text: str) -> int | None:
    """Pull a rupee amount out of an utterance, or return None.

    Handles digits with a multiplier ("50 हजार"), bare digits ("50000"), and
    spelled-out numbers ("पन्नास हजार"). A bare small number with no multiplier
    is read as thousands when it is plausibly a loan said in shorthand - "50"
    means fifty thousand, because nobody asks a bank for fifty rupees.
    """
    normalised = normalise(text)

    # digits + multiplier, e.g. "50 हजार", "1.5 lakh", "50k"
    for words, factor in _MULTIPLIERS:
        for word in words:
            match = re.search(rf"(\d+(?:\.\d+)?)\s*{re.escape(word)}", normalised)
            if match:
                return round(float(match.group(1)) * factor)

    # spelled-out number + multiplier, e.g. "पन्नास हजार"
    for words, factor in _MULTIPLIERS:
        for word in words:
            if word not in normalised:
                continue
            before = normalised.split(word, 1)[0].split()
            for token in reversed(before[-3:]):
                if token in _NUMBER_WORDS:
                    return _NUMBER_WORDS[token] * factor

    # bare digits
    digits = re.findall(r"\d+", normalised)
    if digits:
        value = int(max(digits, key=len))
        # Shorthand: "50" for fifty thousand. Bounded so a stray "3" in
        # "3 महिने" cannot become an amount.
        if 10 <= value <= 200:
            return value * 1_000
        if value >= 1_000:
            return value

    return None


def parse_purpose(text: str) -> str | None:
    """Which of the known purposes the utterance mentions."""
    normalised = normalise(text)
    for purpose, words in _PURPOSE_WORDS.items():
        if _contains_any(normalised, words):
            return purpose
    return None


def parse_language_switch(text: str) -> Lang | None:
    """A request to change language, e.g. "हिंदी में बोलो"."""
    normalised = normalise(text)
    for language, words in _LANGUAGE_WORDS.items():
        if _contains_any(normalised, words):
            return language
    return None


def parse_offer_hint(text: str, lender_names: tuple[str, ...] = ()) -> str | None:
    """How the customer named an offer.

    Returns `"cheapest"`, `"index:N"`, or `"lender:<name>"`. The engine resolves
    the hint against the offers actually on screen - this function deliberately
    does not know which those are.
    """
    normalised = normalise(text)

    if _contains_any(normalised, _CHEAPEST_WORDS):
        return "cheapest"

    for name in lender_names:
        if name and normalise(name) in normalised:
            return f"lender:{name}"

    # Whole-token match for ordinals: "a" and "one" are too short to substring
    # match safely ("a" appears in almost every Latin transliteration).
    for token in re.findall(r"\w+", normalised):
        if token in _ORDINALS:
            return f"index:{_ORDINALS[token]}"

    return None


def understand(
    text: str,
    *,
    step_expects_amount: bool = False,
    lender_names: tuple[str, ...] = (),
) -> Understanding:
    """Classify an utterance.

    @param text               What the customer said or typed.
    @param step_expects_amount  True at ASK_NEED, where a bare number is the
                                answer rather than an unrelated digit.
    @param lender_names       Lenders currently on screen, so they can be
                              recognised by name.

    Order matters. The specific intents are tested before the general ones
    because "समजलं नाही" contains "नाही": checking NO first would read "I don't
    understand" as a refusal and end the data-sharing conversation.
    """
    raw = text.strip()
    normalised = normalise(raw)

    if not normalised:
        return Understanding(Intent.OTHER, raw=raw, confident=False)

    if _contains_any(normalised, HUMAN_WORDS):
        return Understanding(Intent.WANT_HUMAN, raw=raw)

    if _contains_any(normalised, DIDNT_UNDERSTAND_WORDS):
        return Understanding(Intent.DIDNT_UNDERSTAND, raw=raw)

    # A language word alone is a switch request; a language word inside a longer
    # sentence usually is too ("hindi me bolo"), so this stays ahead of yes/no.
    switch_to = parse_language_switch(normalised)
    if switch_to is not None and len(normalised.split()) <= 5:
        return Understanding(Intent.SWITCH_LANGUAGE, language=switch_to, raw=raw)

    amount = parse_amount(raw)
    purpose = parse_purpose(raw)
    if step_expects_amount and (amount is not None or purpose is not None):
        return Understanding(Intent.PROVIDE_NEED, amount=amount, purpose=purpose, raw=raw)

    offer_hint = parse_offer_hint(raw, lender_names)
    if offer_hint is not None and not step_expects_amount:
        return Understanding(Intent.CHOOSE_OFFER, offer_hint=offer_hint, raw=raw)

    if _contains_any(normalised, YES_WORDS):
        return Understanding(Intent.YES, raw=raw)

    if _contains_any(normalised, NO_WORDS):
        return Understanding(Intent.NO, raw=raw)

    if _contains_any(normalised, _TERMS_QUESTION_WORDS):
        return Understanding(Intent.QUESTION_ABOUT_TERMS, raw=raw)

    # Nothing matched. `confident=False` is the signal for phase 8's LLM
    # fallback; before that lands, the engine re-prompts.
    return Understanding(
        Intent.PROVIDE_NEED if amount is not None else Intent.OTHER,
        amount=amount,
        purpose=purpose,
        raw=raw,
        confident=amount is not None,
    )
