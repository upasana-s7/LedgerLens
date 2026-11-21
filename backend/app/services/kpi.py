"""Deterministic dashboard computations.

Everything the Overview screen shows is calculated here from the database with
plain Python and arithmetic. Nothing is hardcoded and no AI is involved -
Gemini only ever re-words these verified numbers (Stage 8).

The one rule to remember: cash = opening_balance + SUM(every transaction
amount), because expenses are already stored as negative numbers.
"""

import calendar
import datetime as dt
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BusinessProfile, Commitment, Invoice, Transaction
from app.schemas.dashboard import (
    AiCfo,
    CashflowPoint,
    DashboardKpis,
    DashboardResponse,
    KpiCard,
    Period,
    RiskItem,
    Workspace,
)
from app.schemas.transaction import TransactionResponse
from app.services.forecast import build_forecast
from app.services.risk import build_risk_response
from app.services.transactions import AS_OF_DATE

TWO_PLACES = Decimal("0.01")


# ---------------------------------------------------------------------------
# Money helpers
# ---------------------------------------------------------------------------

def _money(value) -> Decimal:
    """Round anything numeric to 2 decimal places (paisa)."""
    return Decimal(str(value or 0)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _as_float(value: Decimal) -> float:
    """Convert to float only at the API boundary (JSON has no Decimal)."""
    return float(_money(value))


def _format_inr(value: Decimal) -> str:
    """Format rupees with Indian digit grouping, e.g. ₹2,48,500.

    Indian grouping uses a 3-digit group and then 2-digit groups
    (1,00,000 / 10,00,000). Small amounts like 85,000 look the same as the
    western style, which is why the API contract examples read ₹85,000.
    """
    whole = f"{abs(value):.0f}"
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{'-' if value < 0 else ''}₹{whole}"


# ---------------------------------------------------------------------------
# Data lookups
# ---------------------------------------------------------------------------

def _profile(db: Session) -> BusinessProfile:
    """The single demo business."""
    profile = db.scalar(select(BusinessProfile).order_by(BusinessProfile.id))
    if profile is None:
        raise RuntimeError("No business profile found. Seed the database first.")
    return profile


def _opening_balance(db: Session) -> Decimal:
    """Cash in the bank on the day before the first transaction."""
    return _money(_profile(db).opening_balance)


def _sum_amounts(
    db: Session, on_or_before: dt.date | None = None
) -> Decimal:
    """Sum of signed transaction amounts, optionally up to a date."""
    query = select(func.sum(Transaction.amount))
    if on_or_before is not None:
        query = query.where(Transaction.date <= on_or_before)
    return _money(db.scalar(query))


def _current_balance(db: Session) -> Decimal:
    """Cash today = opening balance + every transaction so far."""
    return _money(_opening_balance(db) + _sum_amounts(db))


def _balance_on(db: Session, when: dt.date) -> Decimal:
    """Cash at the end of a given day."""
    return _money(_opening_balance(db) + _sum_amounts(db, on_or_before=when))


# ---------------------------------------------------------------------------
# The numbers behind the KPI cards
# ---------------------------------------------------------------------------

def _overdue_receivables(db: Session) -> tuple[Decimal, int]:
    """(total, count) of unpaid invoices whose due date has passed.

    "Overdue" is never stored - it is derived from `due_date < AS_OF_DATE`,
    so the answer stays correct as the demo date moves.
    """
    rows = db.scalars(
        select(Invoice).where(
            Invoice.status == "Pending",
            Invoice.due_date < AS_OF_DATE,
        )
    ).all()
    total = sum((_money(invoice.amount) for invoice in rows), Decimal("0.00"))
    return _money(total), len(rows)


def _commitments_due(db: Session, days: int = 30) -> Decimal:
    """Known payments due in the next `days` days (tomorrow .. +30).

    Today is excluded because today's spending is already in the cash balance.
    """
    start = AS_OF_DATE + dt.timedelta(days=1)
    end = AS_OF_DATE + dt.timedelta(days=days)
    total = db.scalar(
        select(func.sum(Commitment.amount)).where(
            Commitment.due_date >= start,
            Commitment.due_date <= end,
        )
    )
    return _money(total)


def _projected_30d(db: Session, days: int = 30) -> Decimal:
    """Closing balance `days` out, taken straight from the forecast engine.

    The Overview card and the Cash Flow screen must never disagree, so this
    does not run its own arithmetic any more: it asks Stage 4's day-by-day
    projection for the same day's balance. With the seeded data that is also
    the lowest point of the month, because December's rent, payroll, EMI and
    vendor payables all land inside the window.
    """
    forecast = build_forecast(db, days=days)
    if not forecast.daily_series:
        # Defensive only: `days` is validated to 30..180 by the router.
        return _current_balance(db)
    return _money(forecast.daily_series[-1].balance)


def _safe_to_spend(db: Session) -> Decimal:
    """What is left after the safety buffer is protected."""
    return _money(_projected_30d(db) - _money(_profile(db).min_cash_buffer))


def _min_cash_buffer(db: Session) -> Decimal:
    """The floor the business never wants to plan below (₹1,50,000)."""
    return _money(_profile(db).min_cash_buffer)


def _safe_to_spend_tone(safe: Decimal, buffer: Decimal) -> str:
    """Colour token for the safe-to-spend card.

    Nothing left at all is coral (act now), less than 30% of the buffer is
    amber (warning), and anything above that is green.
    """
    if safe <= 0:
        return "coral"
    if safe < buffer * Decimal("0.3"):
        return "amber"
    return "green"


def _projected_tone(projected: Decimal, buffer: Decimal) -> str:
    """Colour token for the 30-day projection card.

    The card compares the projection with the safety buffer: below half the
    buffer is coral, below the buffer is amber, up to 1.5x the buffer is sage,
    and comfortably above it is green.
    """
    if projected <= buffer * Decimal("0.5"):
        return "coral"
    if projected < buffer:
        return "amber"
    if projected < buffer * Decimal("1.5"):
        return "sage"
    return "green"


# ---------------------------------------------------------------------------
# Cash-flow chart
# ---------------------------------------------------------------------------

def _month_end(year: int, month: int) -> dt.date:
    """Last calendar day of a month."""
    return dt.date(year, month, calendar.monthrange(year, month)[1])


def _month_end_balance(db: Session, when: dt.date) -> Decimal:
    """Cash at the end of the month containing `when`.

    For the current month the balance is as of AS_OF_DATE, because the month
    is not over yet.
    """
    month_end = _month_end(when.year, when.month)
    return _balance_on(db, min(month_end, AS_OF_DATE))


def _cashflow_series(db: Session) -> list[CashflowPoint]:
    """Nine points: six actual months, then three forecast months.

    History runs Jun-Nov 2026. For those months `actual` and `forecast` are
    the same computed month-end balance. Dec-Feb have no actual (None) and are
    projected by repeating the average of the last three monthly changes.
    """
    actual_months = [(2026, month) for month in range(6, 12)]
    balances = [
        _month_end_balance(db, dt.date(year, month, 1))
        for year, month in actual_months
    ]

    # Month-on-month changes, and the average of the last three.
    deltas = [
        balances[index] - balances[index - 1] for index in range(1, len(balances))
    ]
    recent = deltas[-3:]
    step = _money(sum(recent, Decimal("0.00")) / len(recent))

    points: list[CashflowPoint] = []
    for (year, month), balance in zip(actual_months, balances):
        points.append(
            CashflowPoint(
                month=dt.date(year, month, 1).strftime("%b"),
                month_iso=f"{year}-{month:02d}",
                actual=_as_float(balance),
                # The same computed figure, so the dotted forecast line joins
                # the solid actual line exactly at the last real month.
                forecast=_as_float(balance),
            )
        )

    # Three forward months, compounding the same average step.
    projected = balances[-1]
    for year, month in [(2026, 12), (2027, 1), (2027, 2)]:
        projected = _money(projected + step)
        points.append(
            CashflowPoint(
                month=dt.date(year, month, 1).strftime("%b"),
                month_iso=f"{year}-{month:02d}",
                actual=None,
                forecast=_as_float(projected),
            )
        )

    return points


# ---------------------------------------------------------------------------
# Assembling the response
# ---------------------------------------------------------------------------

def _one_month_before(when: dt.date) -> dt.date:
    """The same day in the previous month (19 Nov -> 19 Oct)."""
    year, month = (when.year, when.month - 1) if when.month > 1 else (when.year - 1, 12)
    day = min(when.day, calendar.monthrange(year, month)[1])
    return dt.date(year, month, day)


def build_dashboard(db: Session) -> DashboardResponse:
    """Build the full Overview payload from the database."""
    profile = _profile(db)

    balance = _current_balance(db)
    month_ago = _balance_on(db, _one_month_before(AS_OF_DATE))
    if month_ago:
        change_pct = (balance - month_ago) / month_ago * 100
        cash_change = f"{change_pct:+.1f}%"
    else:
        cash_change = "n/a"

    overdue_total, overdue_count = _overdue_receivables(db)
    projected = _projected_30d(db)
    commitments = _commitments_due(db, 30)
    safe = _safe_to_spend(db)
    buffer = _min_cash_buffer(db)

    kpis = DashboardKpis(
        available_cash=KpiCard(
            value=_as_float(balance),
            change=cash_change,
            note="vs. last month",
            tone="green" if balance >= month_ago else "coral",
        ),
        projected_30d=KpiCard(
            value=_as_float(projected),
            change="Based on forecast",
            note="estimated closing balance",
            tone=_projected_tone(projected, buffer),
        ),
        overdue_receivables=KpiCard(
            value=_as_float(overdue_total),
            change=f"{overdue_count} invoices",
            note="awaiting payment",
            tone="amber" if overdue_count else "sage",
        ),
        safe_to_spend=KpiCard(
            value=_as_float(safe),
            change="After commitments",
            note="available for decisions",
            tone=_safe_to_spend_tone(safe, buffer),
        ),
    )

    insight = (
        f"Cash is at {_format_inr(balance)}. "
        f"{overdue_count} invoices worth {_format_inr(overdue_total)} are overdue. "
        f"Projected 30-day closing balance: {_format_inr(projected)}."
    )

    ai_cfo = AiCfo(
        tag="CASH FLOW WATCH",
        title="Collections decide December",
        body=(
            f"{_format_inr(overdue_total)} is sitting in {overdue_count} overdue "
            f"invoices, while {_format_inr(commitments)} of commitments fall due "
            f"within 30 days. Your safety buffer is {_format_inr(buffer)}, and the "
            f"30-day projection leaves {_format_inr(safe)} of room above it - "
            f"collecting the oldest overdue invoice first keeps that cushion intact."
        ),
        # Fixed timestamp so the demo is reproducible: 09:00 on the demo date.
        updated_at=f"{AS_OF_DATE.isoformat()}T09:00:00",
        source="rules",
    )

    # The Overview shows the same top alerts the Risk Radar returns, so the two
    # screens can never disagree about what is most urgent (Stage 6).
    risk_items = [
        RiskItem(tone=alert.tone, title=alert.title, detail=alert.subtitle)
        for alert in build_risk_response(db).alerts[:2]
    ]
    while len(risk_items) < 2:
        risk_items.append(
            RiskItem(
                tone="sage",
                title="All clear",
                detail="No risk items detected at this time.",
            )
        )

    recent = db.scalars(
        select(Transaction)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(4)
    ).all()

    return DashboardResponse(
        workspace=Workspace(
            name=profile.name,
            type=profile.business_type,
            city=profile.city,
            is_sample_data=profile.is_synthetic,
        ),
        period=Period(
            label=AS_OF_DATE.strftime("%b %Y"),
            start=AS_OF_DATE.replace(day=1).isoformat(),
            end=_month_end(AS_OF_DATE.year, AS_OF_DATE.month).isoformat(),
        ),
        as_of_date=AS_OF_DATE.isoformat(),
        kpis=kpis,
        cashflow_series=_cashflow_series(db),
        series_range_label="Jun 2026 — Feb 2027",
        insight=insight,
        ai_cfo=ai_cfo,
        risk_items=risk_items,
        recent_transactions=[
            TransactionResponse.model_validate(row) for row in recent
        ],
    )
