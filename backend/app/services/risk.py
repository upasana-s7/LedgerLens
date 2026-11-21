"""Deterministic Risk Radar (Stage 6).

Six fixed rules read the database and describe what looks risky about the cash
position. Nothing here is guessed by a model: Gemini only ever re-words these
verified numbers (Stage 8), so the same data always produces the same alerts.

Every rule is a pure function of the database plus the business profile:

1. **Overdue receivables** - pending invoices whose due date has passed.
2. **Projected buffer breach** - the Stage 4 forecast dips under the safety
   buffer inside 30 days.
3. **Duplicate payment** - two same-amount payments to one vendor within two
   days of each other.
4. **Unusual expense size** - a single expense far above its category's median.
5. **Category spend trend** - a category's 30-day daily rate is up >20% on the
   60 days before that.
6. **Commitment cluster** - seven days of scheduled payments holding more than
   40% of current cash.

The `risk_score` is a severity-weighted count, not a probability: 25 points per
high alert, 10 per medium, 5 per low, capped at 100. The weights deliberately
leave headroom: with the seeded data (2 high, 3 medium, 1 low) the score is 85,
so the badge can still move before it pins at the cap.

Alerts are **not persisted**. The `risk_alerts` table is deliberately left for
later (an audit trail of what was shown when); recomputing on every call keeps
the screen honest if a transaction is edited or added.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BusinessProfile, Commitment, Invoice, Transaction
from app.schemas.risk import EvidencePointer, RiskAlert, RiskResponse, RiskSummary
from app.services.forecast import build_forecast

TWO_PLACES = Decimal("0.01")

# Used only if a profile somehow has no buffer configured.
DEFAULT_MIN_CASH_BUFFER = Decimal("150000.00")

MAX_ALERTS = 8

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
TONE_BY_SEVERITY = {"high": "coral", "medium": "amber", "low": "sage"}
SEVERITY_WEIGHT = {"high": 25, "medium": 10, "low": 5}

# Rule 1: overdue receivables are "high" once they exceed 30% of the buffer.
OVERDUE_HIGH_SHARE = Decimal("0.3")

# Rule 3: look back 90 days; two equal payments within 2 days look duplicated.
DUPLICATE_LOOKBACK_DAYS = 90
DUPLICATE_MAX_GAP_DAYS = 2

# Rule 4: a one-off is unusual when it clears both of these bars.
UNUSUAL_MIN_AMOUNT = Decimal("50000")
UNUSUAL_CATEGORY_MULTIPLE = 2

# Rule 5: the 30-day daily rate must beat the prior 60-day rate by 20%.
TREND_LOOKBACK_DAYS = 90
TREND_RECENT_DAYS = 30
TREND_THRESHOLD_PCT = Decimal("20")

# Rule 6: a 7-day window is crowded when it holds >40% of current cash.
CLUSTER_HORIZON_DAYS = 30
CLUSTER_WINDOW_DAYS = 7
CLUSTER_SHARE_OF_CASH = Decimal("0.4")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _money(value) -> Decimal:
    """Round anything numeric to 2 decimal places (paisa)."""
    return Decimal(str(value or 0)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _rs(value) -> str:
    """Format rupees for running prose, e.g. "Rs 164,500".

    Body text keeps western grouping for readability. `metric` and
    `impact_value` are short display fields read at a glance, so they use
    `format_metric_inr` instead. Plain "Rs" avoids encoding surprises.
    """
    return f"Rs {float(value):,.0f}"


def format_metric_inr(n: float) -> str:
    """Indian-grouped INR: 85000 -> 'Rs 85,000'; 164500 -> 'Rs 1,64,500'."""
    value = float(n)
    sign = "-" if value < 0 else ""
    digits = str(int(round(abs(value))))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        digits = ",".join(groups + [tail])
    return f"Rs {sign}{digits}"


def _metric_number(metric: str) -> float:
    """Pull the leading number out of a display metric, for sorting."""
    digits = re.sub(r"[^0-9.]", "", metric)
    try:
        return float(digits)
    except ValueError:  # pragma: no cover - every rule emits a number
        return 0.0


def _profile(db: Session) -> BusinessProfile:
    """The single demo business. A missing row is a 400, not a crash."""
    profile = db.scalar(select(BusinessProfile).order_by(BusinessProfile.id))
    if profile is None:
        raise ValueError("No business profile found. Seed the database first.")
    return profile


def _current_balance(db: Session, opening: Decimal) -> Decimal:
    """Cash today = opening balance + every transaction (expenses negative)."""
    total = db.scalar(select(func.sum(Transaction.amount)))
    return _money(opening + Decimal(str(total or 0)))


# ---------------------------------------------------------------------------
# One trigger, before ids and tones are assigned
# ---------------------------------------------------------------------------

class _Trigger(NamedTuple):
    """A rule's output. A plain tuple, so the rules stay simple to test."""

    severity: str
    title: str
    subtitle: str
    metric: str
    body: str
    impact_label: str
    impact_value: str
    action_label: str
    evidence: list[EvidencePointer]


# ---------------------------------------------------------------------------
# Rule 1 - overdue customer invoices
# ---------------------------------------------------------------------------

def _rule_overdue_receivables(
    db: Session, as_of: dt.date, min_buffer: Decimal
) -> list[_Trigger]:
    """"Pending" plus a past due date is overdue; that state is never stored."""
    overdue = list(
        db.scalars(
            select(Invoice)
            .where(Invoice.status == "Pending", Invoice.due_date < as_of)
            .order_by(Invoice.due_date, Invoice.id)
        ).all()
    )
    if not overdue:
        return []

    total = _money(
        sum((_money(invoice.amount) for invoice in overdue), Decimal("0.00"))
    )

    if total > min_buffer * OVERDUE_HIGH_SHARE:
        severity = "high"
    elif total > 0:
        severity = "medium"
    else:
        severity = "low"

    oldest = overdue[0]
    days_late = (as_of - oldest.due_date).days

    return [
        _Trigger(
            severity=severity,
            title="Overdue customer invoices",
            subtitle=f"{len(overdue)} invoice(s) past due",
            metric=format_metric_inr(total),
            body=(
                f"You have {_rs(total)} sitting in {len(overdue)} overdue "
                f"invoice(s). The oldest is {oldest.client}'s {oldest.id}, due "
                f"{oldest.due_date}, now {days_late} days late. Chasing these "
                "protects the December buffer."
            ),
            impact_label="Potential impact",
            impact_value="Cash collection delay",
            action_label="Review collection plan",
            evidence=[
                EvidencePointer(
                    kind="invoice",
                    id=invoice.id,
                    label=f"{invoice.client} · {_rs(invoice.amount)}",
                )
                for invoice in overdue
            ],
        )
    ]


# ---------------------------------------------------------------------------
# Rule 2 - the forecast dips under the safety buffer
# ---------------------------------------------------------------------------

def _rule_forecast_shortfall(db: Session, min_buffer: Decimal) -> list[_Trigger]:
    """Reuses the Stage 4 engine, so the Risk Radar and Cash Flow agree."""
    forecast = build_forecast(db, days=30)
    if forecast.shortfall_date is None:
        return []

    lowest = forecast.lowest_balance
    lowest_value = Decimal(str(lowest.value))
    gap = _money(min_buffer - lowest_value)

    return [
        _Trigger(
            severity="high",
            title="Projected cash buffer breach",
            subtitle=(
                f"Forecast dips below {_rs(min_buffer)} on {forecast.shortfall_date}"
            ),
            metric=f"Lowest: {format_metric_inr(lowest_value)}",
            body=(
                f"The 30-day forecast shows your balance falling below the "
                f"{_rs(min_buffer)} safety buffer on {forecast.shortfall_date}. "
                f"The bottom point is {_rs(lowest_value)} on {lowest.date}. "
                "Reducing upcoming outflows or accelerating collections will "
                "close the gap."
            ),
            impact_label="Buffer shortfall",
            impact_value=f"{format_metric_inr(gap)} below floor",
            action_label="Review upcoming commitments",
            evidence=[
                EvidencePointer(
                    kind="commitment",
                    id=item.label,
                    label=f"{item.label} · {_rs(item.amount)} on {item.date}",
                )
                for item in forecast.commitments[:3]
            ],
        )
    ]


# ---------------------------------------------------------------------------
# Rule 3 - duplicate vendor payments
# ---------------------------------------------------------------------------

def _rule_duplicate_payment(db: Session, as_of: dt.date) -> list[_Trigger]:
    """Same vendor, same amount, at most two days apart, in the last 90 days."""
    window_start = as_of - dt.timedelta(days=DUPLICATE_LOOKBACK_DAYS)

    rows = list(
        db.scalars(
            select(Transaction)
            .where(
                Transaction.date >= window_start,
                Transaction.amount < 0,
                Transaction.counterparty_id.is_not(None),
            )
            .order_by(Transaction.date, Transaction.id)
        ).all()
    )

    groups: dict[tuple[int, Decimal], list[Transaction]] = defaultdict(list)
    for row in rows:
        groups[(row.counterparty_id, abs(_money(row.amount)))].append(row)

    duplicates: list[tuple[Transaction, Transaction]] = []
    # Sorted keys keep the alert stable from run to run.
    for key in sorted(groups, key=lambda group: (group[0], group[1])):
        ordered = sorted(groups[key], key=lambda row: (row.date, row.id))
        for index in range(len(ordered) - 1):
            first, second = ordered[index], ordered[index + 1]
            if (second.date - first.date).days <= DUPLICATE_MAX_GAP_DAYS:
                duplicates.append((first, second))
                break  # one duplicate alert per vendor/amount group

    if not duplicates:
        return []

    total_dup = _money(
        sum(
            (abs(_money(first.amount)) for first, _ in duplicates),
            Decimal("0.00"),
        )
    )
    largest = max(duplicates, key=lambda pair: abs(_money(pair[0].amount)))

    return [
        _Trigger(
            severity="medium",
            title="Duplicate payment suspicion",
            subtitle=f"{len(duplicates)} pair(s) worth {_rs(total_dup)}",
            metric=format_metric_inr(total_dup),
            body=(
                f"Found {len(duplicates)} potential duplicate payment(s). The "
                f"largest is {_rs(abs(_money(largest[0].amount)))} paid on "
                f"{largest[0].date} and {largest[1].date}. Verify with the "
                "vendor before the next payment cycle."
            ),
            impact_label="Potential overpayment",
            impact_value=f"Up to {format_metric_inr(total_dup)}",
            action_label="Verify with vendor",
            evidence=[
                EvidencePointer(
                    kind="transaction",
                    id=row.id,
                    label=f"{row.name} · {_rs(abs(_money(row.amount)))} on {row.date}",
                )
                for pair in duplicates
                for row in pair
            ],
        )
    ]


# ---------------------------------------------------------------------------
# Rule 4 - unusually large one-off expenses
# ---------------------------------------------------------------------------

def _rule_unusual_expense_size(db: Session, as_of: dt.date) -> list[_Trigger]:
    """A single expense above Rs 50,000 and twice its category's median."""
    window_start = as_of - dt.timedelta(days=DUPLICATE_LOOKBACK_DAYS)

    rows = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.date >= window_start, Transaction.amount < 0)
            .order_by(Transaction.date, Transaction.id)
        ).all()
    )

    per_category: dict[str, list[Decimal]] = defaultdict(list)
    for row in rows:
        per_category[row.category].append(abs(_money(row.amount)))
    medians = {category: median(values) for category, values in per_category.items()}

    flagged = [
        row
        for row in rows
        if abs(_money(row.amount)) > UNUSUAL_MIN_AMOUNT
        and abs(_money(row.amount))
        > UNUSUAL_CATEGORY_MULTIPLE * medians.get(row.category, Decimal("0"))
    ]
    if not flagged:
        return []

    total = _money(
        sum((abs(_money(row.amount)) for row in flagged), Decimal("0.00"))
    )
    largest = max(flagged, key=lambda row: abs(_money(row.amount)))

    return [
        _Trigger(
            severity="medium",
            title="Unusually large expenses",
            subtitle=f"{len(flagged)} transaction(s) above {_rs(UNUSUAL_MIN_AMOUNT)}",
            metric=format_metric_inr(total),
            body=(
                f"{len(flagged)} expense(s) in the last 90 days were more than "
                "twice the typical amount for their category. The largest was "
                f"{largest.name} at {_rs(abs(_money(largest.amount)))} on "
                f"{largest.date}. Confirm these were planned and budgeted."
            ),
            impact_label="One-off cash impact",
            impact_value=f"{format_metric_inr(total)} total",
            action_label="Review one-off expenses",
            evidence=[
                EvidencePointer(
                    kind="transaction",
                    id=row.id,
                    label=f"{row.name} · {_rs(abs(_money(row.amount)))} on {row.date}",
                )
                for row in sorted(flagged, key=lambda row: -abs(_money(row.amount)))[:5]
            ],
        )
    ]


# ---------------------------------------------------------------------------
# Rule 5 - a category's spend is climbing
# ---------------------------------------------------------------------------

def _rule_category_spend_trend(db: Session, as_of: dt.date) -> list[_Trigger]:
    """Compare each category's daily rate: last 30 days vs the 60 before."""
    recent_start = as_of - dt.timedelta(days=TREND_RECENT_DAYS - 1)
    lookback_start = as_of - dt.timedelta(days=TREND_LOOKBACK_DAYS - 1)

    recent: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    prior: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))

    rows = db.scalars(
        select(Transaction).where(
            Transaction.amount < 0,
            Transaction.date >= lookback_start,
            Transaction.date <= as_of,
        )
    ).all()

    for row in rows:
        target = recent if row.date >= recent_start else prior
        target[row.category] += abs(_money(row.amount))

    rising: list[tuple[str, Decimal, Decimal, Decimal]] = []
    for category, spend in recent.items():
        avg_recent = spend / TREND_RECENT_DAYS
        avg_prior = prior[category] / (TREND_LOOKBACK_DAYS - TREND_RECENT_DAYS)
        if avg_prior <= 0:
            continue
        pct = (avg_recent / avg_prior - 1) * 100
        if pct > TREND_THRESHOLD_PCT:
            rising.append((category, pct, avg_recent, avg_prior))

    if not rising:
        return []

    category, pct, avg_recent, avg_prior = max(rising, key=lambda item: item[1])
    monthly_excess = _money((avg_recent - avg_prior) * TREND_RECENT_DAYS)

    return [
        _Trigger(
            severity="low",
            title=f"{category} spend rising",
            subtitle=f"{category} up {float(pct):.0f}% month-over-month",
            metric=f"+{float(pct):.0f}%",
            body=(
                f"{category} costs are up {float(pct):.0f}% in the last 30 days "
                f"compared to the prior 60-day average. At this pace, the next "
                f"30 days will add about {_rs(monthly_excess)} more than a "
                "typical month. Verify these increases are planned and budgeted."
            ),
            impact_label="Run-rate increase",
            impact_value=f"+{format_metric_inr(monthly_excess)} vs baseline",
            action_label="Review supplier pricing",
            # A trend is a category-level pattern, so there is no single record
            # to point at. An empty list is honest; the UI shows no deep link.
            evidence=[],
        )
    ]


# ---------------------------------------------------------------------------
# Rule 6 - too many payments in one week
# ---------------------------------------------------------------------------

def _rule_commitment_cluster(
    db: Session, as_of: dt.date, current_balance: Decimal
) -> list[_Trigger]:
    """Find the busiest 7-day window of commitments in the next 30 days."""
    horizon_end = as_of + dt.timedelta(days=CLUSTER_HORIZON_DAYS)

    commits = list(
        db.scalars(
            select(Commitment)
            .where(Commitment.due_date > as_of, Commitment.due_date <= horizon_end)
            .order_by(Commitment.due_date, Commitment.id)
        ).all()
    )
    if not commits:
        return []

    best_sum = Decimal("0.00")
    best_window: tuple[dt.date, dt.date] | None = None

    # Windows start tomorrow through as_of+24, so each is a full 7 days that
    # still ends inside the 30-day horizon.
    for offset in range(CLUSTER_HORIZON_DAYS - CLUSTER_WINDOW_DAYS + 1):
        window_start = as_of + dt.timedelta(days=offset + 1)
        window_end = window_start + dt.timedelta(days=CLUSTER_WINDOW_DAYS - 1)
        total = sum(
            (
                _money(item.amount)
                for item in commits
                if window_start <= item.due_date <= window_end
            ),
            Decimal("0.00"),
        )
        if total > best_sum:
            best_sum = total
            best_window = (window_start, window_end)

    if best_window is None or best_sum <= current_balance * CLUSTER_SHARE_OF_CASH:
        return []

    window_start, window_end = best_window
    in_window = [
        item
        for item in commits
        if window_start <= item.due_date <= window_end
    ]
    best_sum = _money(best_sum)

    return [
        _Trigger(
            severity="medium",
            title="Commitment cluster ahead",
            subtitle=f"{_rs(best_sum)} due between {window_start} and {window_end}",
            metric=format_metric_inr(best_sum),
            body=(
                f"{len(in_window)} payments totalling {_rs(best_sum)} fall within "
                "7 days, more than 40% of your current cash. Stagger what you "
                "can, or time collections to land before this window."
            ),
            impact_label="Concentrated outflows",
            impact_value=f"{format_metric_inr(best_sum)} in 7 days",
            action_label="Stagger payments if possible",
            evidence=[
                EvidencePointer(
                    kind="commitment",
                    id=item.label,
                    label=f"{item.label} · {_rs(item.amount)} on {item.due_date}",
                )
                for item in in_window
            ],
        )
    ]


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def detect_alerts(db: Session) -> list[RiskAlert]:
    """Run all six rules and return the sorted, capped, id-assigned alerts."""
    profile = _profile(db)
    as_of = profile.as_of_date
    min_buffer = (
        _money(profile.min_cash_buffer)
        if profile.min_cash_buffer is not None
        else DEFAULT_MIN_CASH_BUFFER
    )
    balance = _current_balance(db, _money(profile.opening_balance))

    triggers: list[_Trigger] = []
    triggers.extend(_rule_overdue_receivables(db, as_of, min_buffer))
    triggers.extend(_rule_forecast_shortfall(db, min_buffer))
    triggers.extend(_rule_duplicate_payment(db, as_of))
    triggers.extend(_rule_unusual_expense_size(db, as_of))
    triggers.extend(_rule_category_spend_trend(db, as_of))
    triggers.extend(_rule_commitment_cluster(db, as_of, balance))

    # Severity first, then the bigger number. Python's sort is stable, so two
    # alerts with the same severity and metric keep the order the rules ran in.
    ordered = sorted(
        triggers,
        key=lambda trigger: (
            SEVERITY_ORDER[trigger.severity],
            -_metric_number(trigger.metric),
        ),
    )[:MAX_ALERTS]

    return [
        RiskAlert(
            id=f"RISK-{index}",
            severity=trigger.severity,
            tone=TONE_BY_SEVERITY[trigger.severity],
            title=trigger.title,
            subtitle=trigger.subtitle,
            metric=trigger.metric,
            body=trigger.body,
            impact_label=trigger.impact_label,
            impact_value=trigger.impact_value,
            action_label=trigger.action_label,
            evidence=trigger.evidence,
        )
        for index, trigger in enumerate(ordered, start=1)
    ]


def build_risk_response(db: Session) -> RiskResponse:
    """The full Risk Radar payload: summary badge, alerts and risk score."""
    alerts = detect_alerts(db)

    attention_count = sum(1 for alert in alerts if alert.severity in {"high", "medium"})
    low_count = sum(1 for alert in alerts if alert.severity == "low")

    if attention_count >= 2:
        tag = "REVIEW RECOMMENDED"
    elif attention_count == 1:
        tag = "MONITOR"
    else:
        tag = "STABLE"

    note = (
        f"Plus {low_count} planning consideration"
        f"{'' if low_count == 1 else 's'}"
        if low_count
        else "No planning considerations"
    )

    risk_score = min(100, sum(SEVERITY_WEIGHT[alert.severity] for alert in alerts))

    return RiskResponse(
        summary=RiskSummary(
            attention_count=attention_count,
            note=note,
            tag=tag,
        ),
        alerts=alerts,
        risk_score=risk_score,
    )
