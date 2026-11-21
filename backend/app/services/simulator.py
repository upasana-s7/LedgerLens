"""Deterministic What-If simulator (Stage 5).

A scenario is one purchase plus one revenue uplift, evaluated on top of the
same 30-day forecast the Cash Flow screen shows:

* **base** is the forecast engine's day-30 closing balance, so the simulator
  can never disagree with `/api/cashflow/forecast` or the dashboard's
  `projected_30d` card.
* **the uplift** is worth the net-flow baseline (the 90-day average daily net
  cash flow, which already nets costs against income) times the uplift percent
  times 30 days, added on top of that same baseline. The baseline is not
  re-filtered: the forecast's own net number is used verbatim.
* **the verdict** compares the scenario balance with 1.5x the business's
  safety buffer - the cost has to leave a real cushion, not just avoid zero.

No AI, no randomness, no wall-clock date: the same database and the same two
sliders always produce the same bytes.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BusinessProfile
from app.schemas.simulator import SimulatorRequest, SimulatorResponse
from app.services.forecast import build_forecast, get_daily_baselines, round_money

# Used only if the profile row is missing its buffer; the seed always sets it.
DEFAULT_MIN_CASH_BUFFER = Decimal("150000.00")

# The scenario horizon matches the dashboard's 30-day projection.
SCENARIO_DAYS = 30

# A purchase has to leave more than the bare buffer behind. 1.5x is the same
# "sage or better" line the dashboard's projected_30d tone uses.
COMFORT_MULTIPLIER = Decimal("1.5")


def _as_float(value: Decimal) -> float:
    """Convert to float only at the API boundary (JSON has no Decimal)."""
    return float(round_money(value))


def _min_cash_buffer(db: Session) -> Decimal:
    """The business's safety floor, defaulting to Rs 1,50,000."""
    profile = db.scalar(select(BusinessProfile).order_by(BusinessProfile.id))
    if profile is None or profile.min_cash_buffer is None:
        return DEFAULT_MIN_CASH_BUFFER
    return round_money(profile.min_cash_buffer)


def _explanation(
    purchase: Decimal,
    projected: Decimal,
    threshold: Decimal,
    uplift_pct: float,
    additional: Decimal,
    comfortable: bool,
) -> str:
    """The deterministic two-to-three sentence reading of the scenario."""

    if comfortable:
        return (
            f"This Rs {purchase:,.0f} purchase leaves you with an estimated "
            f"30-day balance of Rs {projected:,.0f}, comfortably above the "
            f"Rs {threshold:,.0f} comfort threshold. A {uplift_pct:g}% revenue "
            f"uplift adds about Rs {additional:,.0f} over 30 days, which "
            "offsets most of the cost. You can proceed."
        )

    return (
        f"This Rs {purchase:,.0f} purchase would push your projected 30-day "
        f"balance to Rs {projected:,.0f}, below the Rs {threshold:,.0f} "
        f"comfort threshold. Even with a {uplift_pct:g}% revenue uplift "
        f"contributing about Rs {additional:,.0f}, the buffer would not hold. "
        "Consider a smaller purchase, or wait until overdue invoices are "
        "collected."
    )


def build_simulation(db: Session, payload: SimulatorRequest) -> SimulatorResponse:
    """Evaluate one purchase + uplift scenario against the forecast.

    `base_balance` is the forecast engine's day-30 balance, not a separate
    calculation, so the What-If screen and the Cash Flow chart agree by
    construction. The uplift's contribution is layered on the same net-flow
    baseline the forecast projects with, and the verdict asks whether the
    result still clears 1.5x the safety buffer.

    A negative baseline (a business currently losing money) is left signed:
    a 15% uplift then moves `additional_revenue` toward zero, which is treated
    as a smaller loss and reported honestly rather than clamped.
    """
    forecast = build_forecast(db, days=SCENARIO_DAYS)
    if not forecast.daily_series:
        # `days` is fixed at 30 here, so this is defensive only.
        raise ValueError("Forecast produced no daily points to simulate from.")

    base_balance = round_money(forecast.daily_series[-1].balance)

    buffer = _min_cash_buffer(db)
    threshold = round_money(buffer * COMFORT_MULTIPLIER)

    # Same number the forecast projects with: Rs 1,217.11/day on seed data.
    _inflow, _outflow, net_baseline = get_daily_baselines(db)

    purchase = round_money(payload.purchase_amount)
    uplift_pct = payload.revenue_uplift_pct
    additional_revenue = round_money(
        net_baseline * (Decimal(str(uplift_pct)) / Decimal("100")) * SCENARIO_DAYS
    )

    projected_balance = round_money(
        base_balance - purchase + additional_revenue
    )

    comfortable = projected_balance >= threshold
    verdict = "comfortable" if comfortable else "caution"
    verdict_label = (
        "Comfortably affordable" if comfortable else "Proceed with caution"
    )

    return SimulatorResponse(
        base_balance=_as_float(base_balance),
        scenario_cost=_as_float(purchase),
        additional_revenue=_as_float(additional_revenue),
        projected_balance=_as_float(projected_balance),
        verdict=verdict,
        verdict_label=verdict_label,
        threshold=_as_float(threshold),
        explanation=_explanation(
            purchase,
            projected_balance,
            threshold,
            uplift_pct,
            additional_revenue,
            comfortable,
        ),
        # Stage 8 upgrades this to "gemini" when the key is present.
        explanation_source="rules",
    )
