"""Spoken-form rewriting (build plan §10.2)."""

from __future__ import annotations

import pytest

from app.ai.speakable import speakable


@pytest.mark.parametrize(
    ("text", "language", "expected"),
    [
        ("₹4,600", "mr-IN", "4,600 रुपये"),
        ("₹4,600", "hi-IN", "4,600 रुपये"),
        ("₹4,600", "en-IN", "4,600 rupees"),
        ("18.67%", "mr-IN", "18.67 टक्के"),
        ("18.67%", "hi-IN", "18.67 प्रतिशत"),
        ("18.67%", "en-IN", "18.67 percent"),
    ],
)
def test_currency_and_percent(text: str, language: str, expected: str) -> None:
    assert speakable(text, language) == expected  # type: ignore[arg-type]


def test_acronyms_are_transliterated_for_devanagari_voices() -> None:
    assert "सिबिल" in speakable("CIBIL स्कोर कमी होईल", "mr-IN")
    assert "के एफ एस" in speakable("KFS वाचा", "mr-IN")
    assert "ए पी आर" in speakable("APR 18.67%", "hi-IN")


def test_acronyms_are_left_alone_in_english() -> None:
    """An English voice already reads the letters correctly."""
    assert speakable("Your CIBIL score", "en-IN") == "Your CIBIL score"


def test_long_bare_numbers_are_grouped() -> None:
    """Engines read a grouped number as a quantity and a bare one as digits."""
    assert speakable("55200", "en-IN") == "55,200"
    assert speakable("150000", "hi-IN") == "1,50,000"


def test_four_digit_numbers_are_untouched() -> None:
    """`4600` is read correctly as it is, and the card shows `4,600` anyway."""
    assert speakable("4600 महिने", "mr-IN") == "4600 महिने"


def test_a_full_template_line_reads_correctly() -> None:
    line = "तुमचा EMI दर महिन्याला ₹4,600, 12 महिने. एकूण परतफेड ₹55,200."
    spoken = speakable(line, "mr-IN")

    assert "₹" not in spoken, "the symbol must become a spoken word"
    assert "4,600 रुपये" in spoken
    assert "55,200 रुपये" in spoken
    assert "ई एम आय" in spoken


def test_figures_are_never_altered() -> None:
    """A display transform only: the Number Guard must still see what it
    approved (§10.5)."""
    for text in ("₹4,600", "18.67%", "₹55,200", "4%"):
        spoken = speakable(text, "mr-IN")
        digits_in = "".join(ch for ch in text if ch.isdigit())
        digits_out = "".join(ch for ch in spoken if ch.isdigit())
        assert digits_in == digits_out


def test_empty_text_is_safe() -> None:
    assert speakable("", "mr-IN") == ""
