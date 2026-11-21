"""Deterministic cash-flow forecast (Stage 4).

The model has three moving parts, all computed in plain Python:

1. A **daily baseline** from the last 90 days of real transactions: average
   daily counter-sale inflow and average daily operational outflow.
2. **Scheduled commitments** (rent, payroll, EMIs, vendor payables) dropped on
   their exact due dates, straight from the payment calendar.
3. **Open invoices**, collected with a fixed probability: 60% for ones already
   overdue (assumed 10 days from the demo date), 80% for ones still upcoming
   (assumed on their due date).

No AI, no randomness and no wall-clock date: the demo date is
`settings.AS_OF_DATE`, so running the endpoint twice always returns the same
bytes. Gemini only ever explains these numbers (Stage 8).

To stop a cost being counted twice, a category that appears as a future
commitment is left out of the historical daily average - for example rent is
not averaged in *and* subtracted as a commitment. Stage 5's what-if simulator
reuses the same daily series, so the two screens can never disagree.
"""

import calendar
import datetime as dt
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BusinessProfile, Commitment, Invoice, Transaction
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

# How many days of history the daily averages look back over.
HISTORY_DAYS = 90

# Fixed collection assumptions (no randomness, so the demo is reproducible).
OVERDUE_COLLECTION_DAYS = 10
OVERDUE_COLLECTION_PROB = Decimal("0.6")
UPCOMING_COLLECTION_PROB = Decimal("0.8")

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
# Step 1: what the daily baseline should (and should not) include
# ---------------------------------------------------------------------------

def _covered_categories(db: Session, window_end: dt.date) -> set[str]:
    """Categories that appear as a commitment inside the forecast window.

    Their history is left out of the daily averages, because the commitment
    itself is already subtracted on its due date. Counting both would charge
    rent twice.
    """
    rows = db.scalars(
        select(Commitment.category).where(
            Commitment.due_date > AS_OF_DATE,
            Commitment.due_date <= window_end,
        )
    ).all()
    return set(rows)


def _daily_baselines(
    db: Session, covered: set[str]
) -> tuple[Decimal, Decimal]:
    """(daily counter inflow, daily operational outflow) from the last 90 days.

    The window is inclusive on both ends: AS_OF_DATE - 89 .. AS_OF_DATE.
    Income linked to an invoice is excluded because that money is modelled
    separately through the invoice collection probabilities.
    """
    start = AS_OF_DATE - dt.timedelta(days=HISTORY_DAYS - 1)

    def _window(query):
        return query.where(
            Transaction.date >= start,
            Transaction.date <= AS_OF_DATE,
        )

    inflow_query = _window(
        select(func.sum(Transaction.amount)).where(
            Transaction.type == "income",
            # Counter sales have no invoice behind them.
            Transaction.invoice_id.is_(None),
        )
    )
    outflow_query = _window(
        select(func.sum(Transaction.amount)).where(Transaction.type == "expense")
    )
    # `notin_` is only added when there is something to exclude; an empty
    # Python set would otherwise build a confusing "not in ()" clause.
    if covered:
        inflow_query = inflow_query.where(Transaction.category.notin_(covered))
        outflow_query = outflow_query.where(Transaction.category.notin_(covered))

    inflow_total = Decimal(str(db.scalar(inflow_query) or 0))
    # Expenses are stored negative, so flipping the sign gives a positive
    # "money out per day" number.
    outflow_total = -Decimal(str(db.scalar(outflow_query) or 0))

    return (
        round_rate(inflow_total / HISTORY_DAYS),
        round_rate(outflow_total / HISTORY_DAYS),
    )


# ---------------------------------------------------------------------------
# Step 2: dated events (commitments out, expected collections in)
# ---------------------------------------------------------------------------

def _events(
    db: Session, window_end: dt.date
) -> tuple[dict[dt.date, list[Decimal]], list[Commitment]]:
    """Signed amounts per day, plus the commitments that feed them.

    Commitments are negative (money leaving). Invoice collections are positive
    and weighted by a fixed probability, because not every customer pays.
    """
    events: dict[dt.date, list[Decimal]] = defaultdict(list)

    commitments = list(
        db.scalars(
            select(Commitment)
            .where(
                Commitment.due_date > AS_OF_DATE,
                Commitment.due_date <= window_end,
            )
            .order_by(Commitment.due_date, Commitment.id)
        ).all()
    )
    for commitment in commitments:
        events[commitment.due_date].append(-round_money(commitment.amount))

    for invoice in db.scalars(select(Invoice).where(Invoice.status == "Pending")).all():
        if invoice.due_date < AS_OF_DATE:
            # Already late: assume it lands 10 days from the demo date.
            collection_date = AS_OF_DATE + dt.timedelta(days=OVERDUE_COLLECTION_DAYS)
            probability = OVERDUE_COLLECTION_PROB
        elif invoice.due_date <= window_end:
            # Due inside the window: assume payment on the due date.
            collection_date = invoice.due_date
            probability = UPCOMING_COLLECTION_PROB
        else:
            # Falls due after the horizon - not part of this projection.
            continue

        if collection_date <= window_end:
            events[collection_date].append(
                round_money(round_money(invoice.amount) * probability)
            )

    return events, commitments


# ---------------------------------------------------------------------------
# Step 3: the day-by-day projection
# ---------------------------------------------------------------------------

def _project(
    start_balance: Decimal,
    inflow: Decimal,
    outflow: Decimal,
    events: dict[dt.date, list[Decimal]],
    last_day: dt.date,
) -> list[tuple[dt.date, Decimal]]:
    """Walk forward one day at a time from AS_OF_DATE to `last_day`.

    Every day applies the baseline (inflow minus outflow) and then any dated
    events that fall on it. Returns (date, closing balance) pairs, so callers
    can read either the whole daily series or a single month-end.
    """
    balance = start_balance
    points: list[tuple[dt.date, Decimal]] = []

    day = AS_OF_DATE + dt.timedelta(days=1)
    while day <= last_day:
        balance = balance + inflow - outflow
        for amount in events.get(day, []):
            balance += amount
        points.append((day, round_money(balance)))
        day += dt.timedelta(days=1)

    return points


# ---------------------------------------------------------------------------
# Step 4: assembling the response
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
    """Build the Cash Flow screen payload (see the module docstring for the model).

    `days` is the projection horizon used for `daily_series`, `lowest_balance`
    and `shortfall_date`. `inflows_30d` / `outflows_30d` always describe the
    first 30 days, and the monthly chart always covers Jun 2026 - Feb 2027, so
    the projection is also run out to the end of February to fill those three
    future points from the same model.
    """
    profile = _profile(db)

    opening = round_money(profile.opening_balance)
    buffer = round_money(profile.min_cash_buffer)
    current = _current_balance(db, opening)

    window_end = AS_OF_DATE + dt.timedelta(days=days)

    covered = _covered_categories(db, window_end)
    inflow, outflow = _daily_baselines(db, covered)
    events, commitments = _events(db, window_end)

    # Project to whichever is later: the requested horizon or the end of the
    # chart. The first `days` entries are always the daily series.
    chart_end = month_end(*FUTURE_MONTHS[-1])
    projection_end = max(window_end, chart_end)
    curve = _project(current, inflow, outflow, events, projection_end)
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

    # The 30-day totals come from the same daily model, not from summing the
    # monthly chart, so the three views always agree.
    first_30_days = AS_OF_DATE + dt.timedelta(days=30)
    collected_30d = sum(
        (
            amount
            for day, amounts in events.items()
            if day <= first_30_days
            for amount in amounts
            if amount > 0
        ),
        Decimal("0.00"),
    )
    committed_30d = sum(
        (
            -amount
            for day, amounts in events.items()
            if day <= first_30_days
            for amount in amounts
            if amount < 0
        ),
        Decimal("0.00"),
    )

    inflows_30d = round_money(inflow * 30 + collected_30d)
    outflows_30d = round_money(outflow * 30 + committed_30d)

    assumptions = [
        f"Overdue invoices collected {OVERDUE_COLLECTION_DAYS} days from "
        f"{AS_OF_DATE.isoformat()} at {int(OVERDUE_COLLECTION_PROB * 100)}% probability",
        "Upcoming invoices collected on due date at "
        f"{int(UPCOMING_COLLECTION_PROB * 100)}% probability",
        f"Recurring operational outflows: Rs {outflow:.0f} per day "
        "(last 90 days average, excluding commitment-covered categories)",
        f"Counter sales inflows: Rs {inflow:.0f} per day "
        "(last 90 days average, invoice-linked sales excluded)",
        f"Safety buffer: Rs {buffer:.0f}",
        f"Projection horizon: {days} days",
        "Commitments are taken from the scheduled payment calendar",
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
