"""Turning written text into something a voice can read (build plan §10.2).

Text-to-speech reads what you give it literally. "₹4,600" becomes something
like "rupee four comma six zero zero", and "18.67%" becomes "eighteen point six
seven percent sign". Both are wrong in a way that undermines the whole product:
a customer who cannot follow the number being read to them is exactly the
customer this is for.

So before any line is spoken it passes through here:

* `₹4,600` -> `4,600 रुपये` (mr/hi) or `4,600 rupees` (en);
* `18.67%` -> `18.67 टक्के` / `18.67 प्रतिशत` / `18.67 percent`;
* in Marathi and Hindi, `CIBIL` -> `सिबिल`, `KFS` -> `के एफ एस`, `APR` -> `ए पी आर`.

**Commas inside numbers are kept** above four digits. The engines read
`55,200` as "fifty-five thousand two hundred" and `55200` as a digit string, so
the comma is load-bearing rather than decorative.

This is a *display* transform only. It never changes a figure, so the Number
Guard still sees the same numbers it approved (§10.5).
"""

from __future__ import annotations

import re

from app.journey.states import Lang

# Currency: the symbol moves behind the number, as the languages say it.
_RUPEE_WORD: dict[Lang, str] = {
    "mr-IN": "रुपये",
    "hi-IN": "रुपये",
    "en-IN": "rupees",
}

_PERCENT_WORD: dict[Lang, str] = {
    "mr-IN": "टक्के",
    "hi-IN": "प्रतिशत",
    "en-IN": "percent",
}

# Acronyms a Devanagari voice mispronounces when they are left in Latin script.
# Not applied for English, where the letters are read correctly already.
_ACRONYMS: dict[Lang, dict[str, str]] = {
    "mr-IN": {
        "CIBIL": "सिबिल",
        "KFS": "के एफ एस",
        "APR": "ए पी आर",
        "EMI": "ई एम आय",
        "GST": "जी एस टी",
        "PAN": "पॅन",
        "UPI": "यू पी आय",
        "OTP": "ओ टी पी",
        "NBFC": "एन बी एफ सी",
        "DigiLocker": "डिजिलॉकर",
    },
    "hi-IN": {
        "CIBIL": "सिबिल",
        "KFS": "के एफ एस",
        "APR": "ए पी आर",
        "EMI": "ई एम आई",
        "GST": "जी एस टी",
        "PAN": "पैन",
        "UPI": "यू पी आई",
        "OTP": "ओ टी पी",
        "NBFC": "एन बी एफ सी",
        "DigiLocker": "डिजिलॉकर",
    },
    "en-IN": {},
}

# A grouped or plain number: `4,600`, `1,50,000`, `18.67`, `12`.
#
# It must **not** end on a separator. An earlier `[\d,]+` was greedy enough to
# swallow the comma in "₹4,600, 12 महिने", which produced "4,600, रुपये 12" -
# the unit landing after the next number instead of its own.
_NUMBER = r"\d+(?:,\d{2,3})*(?:\.\d+)?"

# `₹4,600` or `₹ 4600`.
_RUPEE_RE = re.compile(rf"₹\s*({_NUMBER})")

# `18.67%` or `4 %`.
_PERCENT_RE = re.compile(rf"({_NUMBER})\s*%")

# A bare number of five digits or more with no separators. Four digits are left
# alone: engines read "4600" correctly, and "4,600" is what the card shows.
_LONG_NUMBER_RE = re.compile(r"(?<![\d,.])(\d{5,})(?![\d,.])")


def _group_indian(digits: str) -> str:
    """`55200` -> `55,200`; `150000` -> `1,50,000`."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def speakable(text: str, language: Lang) -> str:
    """Rewrite `text` so a text-to-speech voice reads it correctly."""
    if not text:
        return text

    rupee = _RUPEE_WORD.get(language, _RUPEE_WORD["en-IN"])
    percent = _PERCENT_WORD.get(language, _PERCENT_WORD["en-IN"])

    # Currency first, so a "₹4,600" is not caught by the bare-number rule.
    spoken = _RUPEE_RE.sub(lambda match: f"{match.group(1)} {rupee}", text)
    spoken = _PERCENT_RE.sub(lambda match: f"{match.group(1)} {percent}", spoken)

    # Group any remaining long bare number, so it is read as a quantity.
    spoken = _LONG_NUMBER_RE.sub(lambda match: _group_indian(match.group(1)), spoken)

    # Acronyms last: doing them earlier would let a replacement's own letters be
    # re-matched by a later rule.
    for acronym, phonetic in _ACRONYMS.get(language, {}).items():
        spoken = re.sub(rf"\b{re.escape(acronym)}\b", phonetic, spoken)

    # Collapse the double spaces the substitutions can leave behind.
    return re.sub(r"\s{2,}", " ", spoken).strip()
