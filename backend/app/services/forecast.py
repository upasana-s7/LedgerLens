"""Deterministic cash-flow forecast (Stage 4, revised in Stage 4.1).

The model is deliberately simple and fully reproducible:

1. One **net baseline** from the last 90 days of real transactions - every
   rupee in, minus every rupee out, divided by 90. That single number already
   contains the business's typical rent, payroll, EMI, utilities and vendor
   payments, so the projection behaves like normal trading.
2. **Scheduled commitments** are then subtracted as lump sums on their exact
   due dates.

That means near-term outflows are *intentionally overstated*: a recurring cost
counts once inside the 90-day average and again as a scheduled commitment. We
accept the conservative double-count because overstating outflows is the safe
direction for a cash-flow warning, and because averaging only the categories
that are *not* scheduled produced a meaningless "Rs 0 per day" outflow in
Stage 4.0.

No AI, no randomness and no wall-clock date: the demo date is
`settings.AS_OF_DATE`, so two calls always return the same bytes. Pending
invoices are not added as separate expected collections - their past payments
are already inside the 90-day average. Stage 5's what-if simulator reuses the
same daily series, so the two screens can never disagree.
"""

import calendar
import datetime as dt
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BusinessProfile, Commitment, Transaction
from app.schemas.cashflow import (
    CommitmentItem,
    DailyPoint,
    ForecastResponse,
    LowestBalance,
)
from app.schemas.dashboard import CashflowPoint
from app.services.transactions import AS_OF_DATE

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")

# How many days of history the baseline looks back over.
HISTORY_DAYS = 90

# The monthly chart always covers the same nine months as the dashboard.
HISTORY_MONTHS = [(2026, month) for month in range(6, 11)]  # Jun - Oct
CURRENT_MONTH = (2026, 11)
FUTURE_MONTHS = [(2026, 12), (2027, 1), (2027, 2)]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def round_money(value) -> Decimal:
    """Round to 2 decimal places (paisa), half-up like an accountant would."""
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def round_rate(value) -> Decimal:
    """Round a per-day average to 4 places, so x90 days stays accurate."""
    return Decimal(str(value)).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def month_end(year: int, month: int) -> dt.date:
    """Last calendar day of a month (handles 28/30/31 automatically)."""
    return dt.date(year, month, calendar.monthrange(year, month)[1])


def _as_float(value) -> float:
    """Convert to float only at the API boundary (JSON has no Decimal)."""
    return float(round_money(value))


# ---------------------------------------------------------------------------
# Loading the starting point
# ---------------------------------------------------------------------------

def _profile(db: Session) -> BusinessProfile:
    """The single demo business. A missing row is a 400, not a crash."""
    profile = db.scalar(select(BusinessProfile).order_by(BusinessProfile.id))
    if profile is None:
        raise ValueError("No business profile found. Seed the database first.")
    return profile


def _current_balance(db: Session, opening: Decimal) -> Decimal:
    """Cash today = opening balance + every transaction (expenses negative)."""
    total = db.scalar(select(func.sum(Transaction.amount)))
    return round_money(opening + Decimal(str(total or 0)))


def _balance_on(db: Session, opening: Decimal, when: dt.date) -> Decimal:
    """Cash at the end of a given day, from real transactions only."""
    total = db.scalar(
        select(func.sum(Transaction.amount)).where(Transaction.date <= when)
    )
    return round_money(opening + Decimal(str(total or 0)))


# ---------------------------------------------------------------------------
# The routine baseline
# ---------------------------------------------------------------------------

def get_daily_baselines(db: Session) -> tuple[Decimal, Decimal, Decimal]:
    """(routine inflow, routine outflow, net) per day over the last 90 days.

    The window is inclusive on both ends: AS_OF_DATE - 89 .. AS_OF_DATE.
    Every income row counts as inflow and every expense row as outflow - no
    category is filtered out, because the point of the baseline is ordinary
    trading. Net is simply inflow minus outflow, so it is positive in a
    healthy month and negative in a bad one.
    """
    start = AS_OF_DATE - dt.timedelta(days=HISTORY_DAYS - 1)

    def _total(kind: str) -> Decimal:
        total = db.scalar(
            select(func.sum(Transaction.amount)).where(
                Transaction.date >= start,
                Transaction.date <= AS_OF_DATE,
                Transaction.type == kind,
            )
        )
        return Decimal(str(total or 0))

    inflow = round_rate(_total("income") / HISTORY_DAYS)
    # Expenses are stored negative, so flipping the sign gives "money out/day".
    outflow = round_rate(-_total("expense") / HISTORY_DAYS)
    net = round_rate(inflow - outflow)
    return inflow, outflow, net


def _daily_baselines(db: Session) -> tuple[Decimal, Decimal, Decimal]:
    """Backwards-compatible private name for `get_daily_baselines`.

    Other services (the Stage 5 simulator) need the exact net-flow figure the
    projection uses, so the calculation is public. This wrapper keeps the
    original internal calls readable.
    """
    return get_daily_baselines(db)


# ---------------------------------------------------------------------------
# Scheduled commitments
# ---------------------------------------------------------------------------

def _commitments_in_window(db: Session, window_end: dt.date) -> list[Commitment]:
    """Known payments due tomorrow .. `window_end`, sorted by date.

    Today is excluded because today's spending is already in the cash balance.
    """
    return list(
        db.scalars(
            select(Commitment)
            .where(
                Commitment.due_date > AS_OF_DATE,
                Commitment.due_date <= window_end,
            )
            .order_by(Commitment.due_date, Commitment.id)
        ).all()
    )


# ---------------------------------------------------------------------------
# The day-by-day projection
# ---------------------------------------------------------------------------

def _project(
    start_balance: Decimal,
    daily_net: Decimal,
    commitments: list[Commitment],
    last_day: dt.date,
) -> list[tuple[dt.date, Decimal]]:
    """Walk forward one day at a time from AS_OF_DATE to `last_day`.

    Each day first applies the routine net flow, then subtracts any commitment
    falling due that day. Returns (date, closing balance) pairs, so callers can
    read either the whole daily series or a single month-end.
    """
    # Signed amounts keyed by the day they hit the bank.
    lump_sums: dict[dt.date, list[Decimal]] = defaultdict(list)
    for commitment in commitments:
        lump_sums[commitment.due_date].append(-round_money(commitment.amount))

    balance = start_balance
    points: list[tuple[dt.date, Decimal]] = []

    day = AS_OF_DATE + dt.timedelta(days=1)
    while day <= last_day:
        balance += daily_net
        for amount in lump_sums.get(day, []):
            balance += amount
        points.append((day, round_money(balance)))
        day += dt.timedelta(days=1)

    return points


# ---------------------------------------------------------------------------
# Assembling the response
# ---------------------------------------------------------------------------

def _monthly_series(
    db: Session,
    opening: Decimal,
    current: Decimal,
    balances: dict[dt.date, Decimal],
    last_projected: dt.date,
) -> list[CashflowPoint]:
    """The nine-point chart: Jun-Oct actual, Nov as-of, Dec-Feb forecast.

    History comes from real transactions. From December on the points are read
    off the same daily projection as `daily_series`, so the dashed line is the
    model's own output rather than a separate straight-line extrapolation.
    """
    points: list[CashflowPoint] = []

    for year, month in HISTORY_MONTHS:
        balance = _balance_on(db, opening, month_end(year, month))
        points.append(
            CashflowPoint(
                month=dt.date(year, month, 1).strftime("%b"),
                month_iso=f"{year}-{month:02d}",
                actual=_as_float(balance),
                # Identical figure, so the dotted line meets the solid line
                # exactly at the last real month.
                forecast=_as_float(balance),
            )
        )

    # November is not over yet: today's balance is the honest value for both.
    year, month = CURRENT_MONTH
    points.append(
        CashflowPoint(
            month=dt.date(year, month, 1).strftime("%b"),
            month_iso=f"{year}-{month:02d}",
            actual=_as_float(current),
            forecast=_as_float(current),
        )
    )

    for year, month in FUTURE_MONTHS:
        target = month_end(year, month)
        # Inside the projected days use that day; if the month ends after the
        # horizon (e.g. days=30) fall back to the last day we did project.
        balance = balances.get(target, balances.get(last_projected, current))
        points.append(
            CashflowPoint(
                month=dt.date(year, month, 1).strftime("%b"),
                month_iso=f"{year}-{month:02d}",
                actual=None,
                forecast=_as_float(balance),
            )
        )

    return points


def build_forecast(db: Session, days: int = 90) -> ForecastResponse:
    """Build the Cash Flow screen payload.

    The projection starts from today's cash and adds the 90-day average daily
    net flow, then subtracts every scheduled commitment on its due date.
    Because the historical average already includes recurring payments, the
    near-term outflow is knowingly a little too high - the safe direction for
    a cash-flow warning. The same curve fills the monthly chart, so the chart,
    the daily series and the dashboard's 30-day projection cannot drift apart.
    """
    profile = _profile(db)

    opening = round_money(profile.opening_balance)
    buffer = round_money(profile.min_cash_buffer)
    current = _current_balance(db, opening)

    window_end = AS_OF_DATE + dt.timedelta(days=days)

    inflow, outflow, daily_net = _daily_baselines(db)
    commitments = _commitments_in_window(db, window_end)

    # Project to whichever is later: the requested horizon or the end of the
    # chart. The first `days` entries are always the daily series.
    chart_end = month_end(*FUTURE_MONTHS[-1])
    projection_end = max(window_end, chart_end)
    curve = _project(current, daily_net, commitments, projection_end)
    balances = dict(curve)

    daily_series = [
        DailyPoint(date=day.isoformat(), balance=_as_float(balance))
        for day, balance in curve[:days]
    ]

    # Lowest point of the requested horizon (ties go to the earliest date,
    # because we walk forward and only replace on a strict "less than").
    if daily_series:
        lowest = daily_series[0]
        for point in daily_series[1:]:
            if point.balance < lowest.balance:
                lowest = point
        lowest_balance = LowestBalance(value=lowest.balance, date=lowest.date)
        shortfall_date = next(
            (point.date for point in daily_series if point.balance < buffer),
            None,
        )
    else:
        # Only reachable if `days` were 0; keep the response well-formed.
        lowest_balance = LowestBalance(
            value=_as_float(current), date=AS_OF_DATE.isoformat()
        )
        shortfall_date = None

    # The 30-day totals split the same model into its two halves: routine flow
    # for 30 days, plus commitments falling due in those 30 days. Their
    # difference always equals the change in balance over the same window.
    first_30_days = AS_OF_DATE + dt.timedelta(days=30)
    committed_30d = sum(
        (
            round_money(item.amount)
            for item in commitments
            if item.due_date <= first_30_days
        ),
        Decimal("0.00"),
    )

    inflows_30d = round_money(inflow * 30)
    outflows_30d = round_money(outflow * 30 + committed_30d)

    assumptions = [
        f"Baseline daily net flow: Rs {daily_net:,.0f} "
        "(derived from 90-day historical average; already includes typical "
        "rent, payroll, EMI, utilities and vendor payments)",
        "Scheduled commitments are applied as lump-sum outflows on their due "
        "dates (conservative upper bound on near-term outflows)",
        f"Safety buffer: Rs {buffer:,.0f}",
        f"Projection horizon: {days} days",
        "Model intentionally overstates near-term outflows because historical "
        "recurring payments are also averaged in the baseline",
    ]

    return ForecastResponse(
        # "Opening" means the start of the projection, i.e. cash today - the
        # same figure the dashboard shows as available cash.
        opening_balance=_as_float(current),
        inflows_30d=_as_float(inflows_30d),
        outflows_30d=_as_float(outflows_30d),
        series=_monthly_series(
            db, opening, current, balances, curve[-1][0] if curve else AS_OF_DATE
        ),
        daily_series=daily_series,
        range_label="Jun 2026 — Feb 2027",
        commitments=[
            CommitmentItem(
                label=item.label,
                amount=_as_float(item.amount),
                date=item.due_date.isoformat(),
            )
            for item in commitments
        ],
        assumptions=assumptions,
        lowest_balance=lowest_balance,
        shortfall_date=shortfall_date,
        is_sample_data=profile.is_synthetic,
    )
