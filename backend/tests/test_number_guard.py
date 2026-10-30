"""The Number Guard (build plan §10.5).

The plan names three cases explicitly; the rest are the ways a guard like this
usually gets defeated.
"""

from __future__ import annotations

from app.ai.number_guard import check, extract_numbers, guard, normalise

# The golden path's offer: NBFC A at ₹50,000 over 12 months.
FACTS = {
    "principal": 50_000,
    "tenure_months": 12,
    "rate_pa": 18.67,
    "processing_fee": 0,
    "gst": 0,
    "net_disbursed": 50_000,
    "emi": 4_600,
    "total_repay": 55_200,
    "total_interest": 5_200,
    "total_cost": 5_200,
    "apr": 18.67,
    "late_fee": 500,
    "foreclosure_pct": 4.0,
    "cooling_off_days": 3,
    "insurance_premium": 750,
}

CUSTOMER = {"amount": 50_000, "monthly_income": 28_400, "foir_pct": 16.4}


def verdict(text: str):
    return check(text, offers=[FACTS], customer=CUSTOMER)


def values(text: str) -> list[float]:
    """Just the numbers, dropping the money flag."""
    return [value for value, _ in extract_numbers(text)]


# --- the three cases the plan names -----------------------------------------


def test_an_invented_emi_is_blocked() -> None:
    """§10.5: "an invented ₹4,000 EMI is blocked"."""
    result = verdict("तुमचा EMI ₹4,000 आहे.")
    assert result.allowed is False
    assert 4_000.0 in result.blocked_numbers


def test_devanagari_digits_pass() -> None:
    """§10.5: "४,६०० passes". A guard defeated by changing script is useless."""
    assert verdict("तुमचा EMI ₹४,६०० आहे.").allowed is True


def test_a_wrong_rate_is_blocked() -> None:
    """§10.5: "18.5% is blocked" - the real rate is 18.67%."""
    result = verdict("व्याजदर 18.5% आहे.")
    assert result.allowed is False
    assert 18.5 in result.blocked_numbers


# --- the approved facts -----------------------------------------------------


def test_every_approved_fact_passes() -> None:
    line = (
        "₹50,000 कर्ज, 12 महिने, EMI ₹4,600, एकूण ₹55,200, "
        "व्याज ₹5,200, दर 18.67%, लेट फी ₹500, फोरक्लोजर 4%, "
        "कूलिंग-ऑफ 3 दिवस, विमा ₹750."
    )
    assert verdict(line).allowed is True


def test_the_customers_own_figures_pass() -> None:
    assert verdict("तुमची मिळकत ₹28,400 आहे आणि EMI 16.4% होतो.").allowed is True


def test_small_counts_pass() -> None:
    """"3 questions", "question 2" - unavoidable and not financial."""
    assert verdict("आता 3 प्रश्न. हा प्रश्न 2 आहे.").allowed is True


def test_text_with_no_numbers_passes() -> None:
    assert verdict("विमा ऐच्छिक आहे, तुम्ही नाही म्हणू शकता.").allowed is True


# --- the ways a guard gets defeated -----------------------------------------


def test_a_multiplier_cannot_smuggle_a_number_past() -> None:
    """"4.6 हजार" is 4600 and must be compared as such, not as 4.6."""
    assert values("4.6 हजार") == [4_600.0]
    assert verdict("EMI 4.6 हजार आहे.").allowed is True

    # And a wrong one written the same way is still caught.
    result = verdict("EMI 4 हजार आहे.")
    assert result.allowed is False
    assert 4_000.0 in result.blocked_numbers


def test_lakh_is_expanded() -> None:
    assert values("1.5 lakh") == [150_000.0]
    assert values("2 लाख") == [200_000.0]


def test_separators_do_not_change_a_number() -> None:
    assert normalise("55,200") == "55200"
    assert values("₹55,200") == [55_200.0]
    assert values("55200") == [55_200.0]


def test_money_markers_are_recognised() -> None:
    """A figure wearing a currency symbol or a percent sign is money, so the
    safe-small-count allowance must not cover it."""
    assert extract_numbers("₹1") == [(1.0, True)]
    assert extract_numbers("3 प्रश्न") == [(3.0, False)]
    assert extract_numbers("4%") == [(4.0, True)]


def test_a_small_count_cannot_be_used_as_money() -> None:
    """Without this, "EMI is ₹1" passes because 1 is a permitted count - which
    is exactly the kind of invented figure the guard exists to block."""
    assert verdict("आता 3 प्रश्न.").allowed is True
    assert verdict("तुमचा EMI ₹1 आहे.").allowed is False
    assert verdict("तुमचा EMI ₹3 आहे.").allowed is False


def test_rounding_is_not_permitted() -> None:
    """A rounded EMI is exactly the failure this exists to prevent.

    Permitting it for a rate would mean permitting it for money - there is no
    way to allow one and not the other - and the templates always say the exact
    figure, so nothing legitimate needs rounding.
    """
    assert verdict("EMI जवळपास ₹4,500 आहे.").allowed is False
    assert verdict("दर 19% आहे.").allowed is False


def test_a_number_from_another_offer_is_blocked_after_selection() -> None:
    """At OFFERS all three offers' numbers are allowed; after selection only
    the chosen one's are, because the others are no longer facts about this
    customer's loan."""
    bank_b = {**FACTS, "emi": 4_536, "apr": 27.80, "processing_fee": 2_500}

    at_offers = check("EMI ₹4,536 किंवा ₹4,600.", offers=[FACTS, bank_b])
    assert at_offers.allowed is True

    after_selection = check("EMI ₹4,536 आहे.", offers=[FACTS])
    assert after_selection.allowed is False


# --- the fallback behaviour -------------------------------------------------


def test_guard_substitutes_the_template_on_a_violation() -> None:
    """A stiff sentence that is true beats a fluent one that is not."""
    generated = "तुमचा EMI फक्त ₹4,000 आहे, काळजी करू नका."
    seeded = "तुमचा EMI दर महिन्याला ₹4,600, 12 महिने."

    text, result = guard(generated, seeded, offers=[FACTS], customer=CUSTOMER)

    assert text == seeded
    assert result.allowed is False
    assert result.reason is not None
    assert "4000" in result.reason


def test_guard_passes_good_text_through_unchanged() -> None:
    generated = "दर महिन्याला ₹4,600 भरायचे आहेत, एकूण ₹55,200."
    text, result = guard(generated, "fallback", offers=[FACTS], customer=CUSTOMER)

    assert text == generated
    assert result.allowed is True


def test_on_block_is_notified_for_the_audit_event() -> None:
    """The dashboard counts these (§12), so the hook has to fire."""
    seen: list[object] = []
    guard(
        "EMI ₹1,23,456 आहे.",
        "fallback",
        offers=[FACTS],
        on_block=seen.append,
    )
    assert len(seen) == 1


def test_an_empty_allow_list_blocks_every_number_but_the_small_counts() -> None:
    """With no offer on screen, there are no approved figures to quote."""
    assert check("₹4,600").allowed is False
    assert check("3 प्रश्न").allowed is True
