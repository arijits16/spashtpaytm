"""Loan arithmetic: EMI, APR and total cost (build plan §7.2).

This module is the only place a loan number is calculated. Everything else -
offers, KFS facts, the teach-back answers, the receipt - reads from here or from
the stored offer row, which is why the Number Guard (§10.5) can state with
confidence that the assistant invented a figure.

**Why APR and not the interest rate.** The whole demo turns on one fact: the
offer with the lowest advertised rate is not the cheapest. Bank B charges 15.99%
against NBFC A's 18.67%, but B takes a 2,500 fee plus GST off the top, so the
money that actually reaches the customer is smaller while the EMIs are nearly
the same. The APR is what exposes that, because it is the rate implied by the
cash flows the customer really experiences: 47,050 in, twelve payments of 4,536
out. That comes to 27.80% - nearly twelve points worse than the headline.

Rounding follows what a lender would actually do, and the order matters:
the EMI is rounded to the rupee *first*, then the total repayment is twelve times
that rounded EMI. Computing the total from the unrounded EMI would differ by a
few rupees from what the customer is charged, and a receipt that disagrees with
the bank statement is worse than useless.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bisection bounds for the monthly IRR. A monthly rate of 100% is far outside
# anything legal in India, so a root outside this range means the cash flows are
# not a loan and refusing is better than returning a meaningless number.
_IRR_LOW = 1e-9
_IRR_HIGH = 1.0
_IRR_TOLERANCE = 1e-12
_IRR_MAX_ITERATIONS = 200


def emi(principal: int, annual_rate_pct: float, tenure_months: int) -> int:
    """Equated monthly instalment on a reducing-balance loan, in whole rupees.

    The standard annuity formula, with the monthly rate being the annual rate
    divided by twelve - which is how Indian lenders quote and compute it, not
    the compounded twelfth root.

    @param principal       Amount borrowed, in rupees.
    @param annual_rate_pct Nominal annual rate, e.g. `18.67`.
    @param tenure_months   Number of instalments.
    @returns The instalment, rounded to the nearest rupee.
    """
    if principal <= 0 or tenure_months <= 0:
        raise ValueError("principal and tenure must be positive")
    if annual_rate_pct < 0:
        raise ValueError("rate cannot be negative")

    if annual_rate_pct == 0:
        return round(principal / tenure_months)

    monthly = annual_rate_pct / 100.0 / 12.0
    growth = (1.0 + monthly) ** tenure_months
    return round(principal * monthly * growth / (growth - 1.0))


def net_disbursed(principal: int, processing_fee: int, gst_on_fee: int) -> int:
    """What actually reaches the customer's account.

    The fee and its GST are deducted up front, so the customer borrows
    `principal` for interest purposes but receives less. This gap is the entire
    reason the APR diverges from the quoted rate.
    """
    return principal - processing_fee - gst_on_fee


def apr_irr(
    principal: int,
    processing_fee: int,
    gst_on_fee: int,
    instalment: int,
    tenure_months: int,
) -> float:
    """Annual percentage rate: twelve times the monthly IRR of the cash flows.

    The cash flows are the net amount received at month zero, followed by
    `tenure_months` equal instalments. Solved by bisection rather than
    Newton-Raphson: the present-value function is monotonically decreasing in
    the rate over the bracket, so bisection cannot diverge or oscillate, and 200
    halvings of a [0, 1] bracket is far more precision than two decimal places
    needs. Reliability beats speed for a number this load-bearing.

    @returns The APR as a percentage, rounded to 2 decimal places.
    """
    received = net_disbursed(principal, processing_fee, gst_on_fee)
    if received <= 0:
        raise ValueError("fees cannot exceed the principal")
    if instalment <= 0 or tenure_months <= 0:
        raise ValueError("instalment and tenure must be positive")

    total_paid = instalment * tenure_months
    if total_paid <= received:
        # A zero-cost or subsidised loan. There is no positive root to find.
        return 0.0

    def present_value(monthly_rate: float) -> float:
        """Net present value of the instalments minus what was received."""
        discounted = sum(
            instalment / (1.0 + monthly_rate) ** month for month in range(1, tenure_months + 1)
        )
        return discounted - received

    low, high = _IRR_LOW, _IRR_HIGH
    if present_value(high) > 0:
        # Even a 100%/month rate does not discount the payments down to the
        # amount received: the inputs are not a loan.
        raise ValueError("no plausible IRR for these cash flows")

    for _ in range(_IRR_MAX_ITERATIONS):
        mid = (low + high) / 2.0
        value = present_value(mid)
        if abs(value) < _IRR_TOLERANCE:
            break
        if value > 0:
            low = mid
        else:
            high = mid

    monthly_rate = (low + high) / 2.0
    return round(monthly_rate * 12.0 * 100.0, 2)


@dataclass(frozen=True, slots=True)
class LoanQuote:
    """Every derived number for one priced offer.

    Frozen because these are the figures that go on a receipt: once quoted, they
    must not be mutated by a later step.
    """

    principal: int
    tenure_months: int
    rate_pa: float
    processing_fee: int
    gst_on_fee: int

    emi: int
    total_repay: int
    total_interest: int
    total_cost: int
    apr: float

    @property
    def net_disbursed(self) -> int:
        return net_disbursed(self.principal, self.processing_fee, self.gst_on_fee)


def quote(
    principal: int,
    annual_rate_pct: float,
    tenure_months: int,
    processing_fee: int = 0,
    gst_on_fee: int = 0,
) -> LoanQuote:
    """Price one offer completely.

    `total_interest` is what the lender earns on the loan; `total_cost` is what
    the *customer* loses, which also includes the fee and its GST. They differ by
    exactly the deduction, and conflating them is how a comparison screen ends up
    recommending the expensive offer.
    """
    instalment = emi(principal, annual_rate_pct, tenure_months)
    total_repay = instalment * tenure_months
    total_interest = total_repay - principal

    return LoanQuote(
        principal=principal,
        tenure_months=tenure_months,
        rate_pa=annual_rate_pct,
        processing_fee=processing_fee,
        gst_on_fee=gst_on_fee,
        emi=instalment,
        total_repay=total_repay,
        total_interest=total_interest,
        total_cost=total_interest + processing_fee + gst_on_fee,
        apr=apr_irr(principal, processing_fee, gst_on_fee, instalment, tenure_months),
    )


def foir(existing_emi: float, new_emi: int, monthly_income: float) -> float:
    """Fixed-obligation-to-income ratio, as a fraction (0.162, not 16.2).

    The suitability gate in §9: a customer whose instalments eat more than half
    their verified income is refused, however much they ask for.
    """
    if monthly_income <= 0:
        raise ValueError("income must be positive")
    return (existing_emi + new_emi) / monthly_income
