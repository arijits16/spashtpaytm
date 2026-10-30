"""The §7.2 offer table, asserted to the rupee.

These three rows are the demo's whole argument, so they are pinned here rather
than trusted to the seed file: if the arithmetic drifts, this fails before a
judge spots it on screen.
"""

from __future__ import annotations

import pytest

from app.journey.loan_math import apr_irr, emi, foir, quote

PRINCIPAL = 50_000
TENURE = 12


def test_offer_a_no_fee() -> None:
    """Partner NBFC A: 18.67%, no fee. The APR equals the rate because nothing
    is deducted up front - the baseline the other two are judged against."""
    result = quote(PRINCIPAL, 18.67, TENURE)
    assert result.emi == 4_600
    assert result.total_repay == 55_200
    assert result.total_cost == 5_200
    assert result.apr == pytest.approx(18.67, abs=0.05)


def test_offer_b_low_rate_high_fee() -> None:
    """Partner Bank B: the cheapest-looking and most expensive offer.

    15.99% against A's 18.67%, yet the 2,950 deducted up front pushes the APR to
    27.80% and the true cost to 7,382 - over 2,000 worse than A.
    """
    result = quote(PRINCIPAL, 15.99, TENURE, processing_fee=2_500, gst_on_fee=450)
    assert result.emi == 4_536
    assert result.total_repay == 54_432
    assert result.total_cost == 7_382
    assert result.apr == pytest.approx(27.80, abs=0.05)
    assert result.net_disbursed == 47_050

    # The point of the whole screen, stated as an assertion.
    cheaper_looking = quote(PRINCIPAL, 18.67, TENURE)
    assert result.rate_pa < cheaper_looking.rate_pa
    assert result.total_cost > cheaper_looking.total_cost
    assert result.apr > cheaper_looking.apr


def test_offer_c_no_fee() -> None:
    """Partner NBFC C: 21.00%, no fee."""
    result = quote(PRINCIPAL, 21.00, TENURE)
    assert result.emi == 4_656
    assert result.total_repay == 55_872
    assert result.total_cost == 5_872
    assert result.apr == pytest.approx(21.01, abs=0.05)


def test_zero_rate_splits_principal_evenly() -> None:
    assert emi(12_000, 0.0, 12) == 1_000


def test_rejects_impossible_inputs() -> None:
    with pytest.raises(ValueError):
        emi(0, 18.0, 12)
    with pytest.raises(ValueError):
        emi(50_000, -1.0, 12)
    with pytest.raises(ValueError):
        # Fees larger than the loan: nothing is disbursed, so there is no rate.
        apr_irr(5_000, 5_000, 900, 500, 12)


def test_foir_is_a_fraction() -> None:
    """Sunita's numbers: a 4,600 EMI against 28,400 verified income."""
    assert foir(0, 4_600, 28_400) == pytest.approx(0.162, abs=0.001)
    assert foir(3_000, 4_600, 22_000) == pytest.approx(0.345, abs=0.001)
