"""Invoice and receivables logic (Stage 7).

Two rules drive everything here:

* **"Overdue" is never stored.** The database holds only "Draft", "Pending" and
  "Paid"; overdue is computed from `due_date` against the demo date, so the
  list cannot go stale when a day passes.
* **Marking an invoice paid always writes the matching income transaction.**
  The receivables screen and the cash balance then move together instead of
  drifting apart.

A "Draft" invoice (created by the Stage 9 upload flow) cannot be marked paid:
a human has to review and confirm the extracted fields first.
"""

import datetime as dt
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Invoice, Transaction
from app.schemas.invoice import (
    AgingBucket,
    InvoiceItem,
    InvoiceListResponse,
    InvoiceSummary,
    MarkPaidResponse,
    ReceivableListResponse,
)
from app.services.transactions import next_transaction_id, round_money

# The demo's fixed "today". Parsed once so every response agrees.
AS_OF_DATE = dt.date.fromisoformat(settings.AS_OF_DATE)

# The ageing chart always shows these four columns, in this order.
AGING_LABELS = ("Current", "1-30 days", "31-60 days", "60+ days")

DisplayStatus = Literal["Draft", "Pending", "Overdue", "Paid"]


class InvoiceNotFoundError(ValueError):
    """Unknown invoice id - the router turns this into a 404."""


class InvoiceStateError(ValueError):
    """The invoice exists but cannot change state - the router sends a 409."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _money(value) -> Decimal:
    """Rupees to 2 decimal places, following the forecast engine's convention."""
    return round_money(Decimal(str(value or 0)))


def _compute_display_status(
    invoice: Invoice, as_of: dt.date
) -> tuple[DisplayStatus, int]:
    """Return `(display_status, days_overdue)` for one invoice."""
    if invoice.status == "Paid":
        return ("Paid", 0)
    if invoice.status == "Draft":
        return ("Draft", 0)
    # Anything still "Pending" is overdue once its due date has passed.
    if invoice.due_date < as_of:
        return ("Overdue", (as_of - invoice.due_date).days)
    return ("Pending", 0)


def _to_item(invoice: Invoice, as_of: dt.date) -> InvoiceItem:
    """Convert an ORM invoice into the flat row the frontend renders."""
    status, days_overdue = _compute_display_status(invoice, as_of)
    return InvoiceItem(
        id=invoice.id,
        client=invoice.client,
        due_date=invoice.due_date.isoformat(),
        amount=float(_money(invoice.amount)),
        status=status,
        days_overdue=days_overdue,
    )


def _summary(db: Session, as_of: dt.date) -> InvoiceSummary:
    """The four counters above the invoice list."""
    invoices = list(db.scalars(select(Invoice)).all())
    pending = [invoice for invoice in invoices if invoice.status == "Pending"]

    total_outstanding = _money(
        sum((_money(invoice.amount) for invoice in pending), Decimal("0.00"))
    )
    overdue_total = _money(
        sum(
            (
                _money(invoice.amount)
                for invoice in pending
                if invoice.due_date < as_of
            ),
            Decimal("0.00"),
        )
    )

    # "This month" runs from the 1st of the demo month through the demo date.
    month_start = as_of.replace(day=1)
    collected = _money(
        sum(
            (
                _money(invoice.paid_amount)
                for invoice in invoices
                if invoice.status == "Paid"
                and invoice.paid_date is not None
                and month_start <= invoice.paid_date <= as_of
            ),
            Decimal("0.00"),
        )
    )

    return InvoiceSummary(
        total_outstanding=float(total_outstanding),
        outstanding_count=len(pending),
        overdue_total=float(overdue_total),
        collected_this_month=float(collected),
    )


def _aging(invoices: list[Invoice], as_of: dt.date) -> list[AgingBucket]:
    """Bucket unpaid invoices by how long they have been outstanding."""
    counts = {label: 0 for label in AGING_LABELS}
    totals = {label: Decimal("0.00") for label in AGING_LABELS}

    for invoice in invoices:
        if invoice.status != "Pending":
            continue
        _, days_overdue = _compute_display_status(invoice, as_of)
        if invoice.due_date >= as_of:
            label = "Current"
        elif days_overdue <= 30:
            label = "1-30 days"
        elif days_overdue <= 60:
            label = "31-60 days"
        else:
            label = "60+ days"
        counts[label] += 1
        totals[label] += _money(invoice.amount)

    return [
        AgingBucket(label=label, count=counts[label], amount=float(totals[label]))
        for label in AGING_LABELS
    ]


def _overdue_count(db: Session, as_of: dt.date) -> int:
    """How many unpaid invoices are past due right now (a fresh query)."""
    return (
        db.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.status == "Pending", Invoice.due_date < as_of)
        )
        or 0
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def build_invoice_list(db: Session) -> InvoiceListResponse:
    """Every invoice, newest issue date first, with the summary counters."""
    as_of = AS_OF_DATE

    invoices = list(
        db.scalars(
            select(Invoice).order_by(Invoice.issue_date.desc(), Invoice.id.desc())
        ).all()
    )

    return InvoiceListResponse(
        summary=_summary(db, as_of),
        items=[_to_item(invoice, as_of) for invoice in invoices],
    )


def build_receivable_list(db: Session) -> ReceivableListResponse:
    """Open invoices only, the most overdue first, plus collection progress."""
    as_of = AS_OF_DATE

    pending = list(
        db.scalars(select(Invoice).where(Invoice.status == "Pending")).all()
    )
    # Overdue first (False sorts before True), then the oldest due date, so the
    # longest-late invoice leads the list.
    pending.sort(key=lambda invoice: (invoice.due_date >= as_of, invoice.due_date, invoice.id))

    outstanding_total = _money(
        sum((_money(invoice.amount) for invoice in pending), Decimal("0.00"))
    )
    overdue_count = sum(1 for invoice in pending if invoice.due_date < as_of)

    collected = _money(_summary(db, as_of).collected_this_month)
    denominator = collected + outstanding_total
    progress = int(round(collected / denominator * 100)) if denominator > 0 else 0

    return ReceivableListResponse(
        outstanding_total=float(outstanding_total),
        overdue_count=overdue_count,
        collection_progress_pct=progress,
        aging_buckets=_aging(pending, as_of),
        items=[_to_item(invoice, as_of) for invoice in pending],
    )


def mark_paid(db: Session, invoice_id: str) -> MarkPaidResponse:
    """Collect one invoice: flip it to Paid and record the cash coming in.

    The linked income transaction is what keeps the two screens honest - the
    invoice leaves the receivables list and the money shows up in the ledger on
    the same date. Drafts are refused because their fields are unconfirmed.
    """
    as_of = AS_OF_DATE

    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
    if invoice.status == "Paid":
        raise InvoiceStateError(f"Invoice {invoice_id} is already paid")
    if invoice.status == "Draft":
        raise InvoiceStateError(
            f"Invoice {invoice_id} is a draft; confirm it before marking as paid"
        )

    amount = _money(invoice.amount)

    invoice.status = "Paid"
    invoice.paid_amount = amount
    invoice.paid_date = as_of

    db.add(
        Transaction(
            id=next_transaction_id(db),
            date=as_of,
            name=f"{invoice.client} — payment for {invoice.id}",
            category="Sales",
            amount=amount,  # positive: money in
            type="income",
            counterparty_id=invoice.counterparty_id,
            payment_mode="Bank transfer",
            invoice_id=invoice.id,
            source="invoice",
            # Derived from the demo date, not the wall clock, so the data stays
            # reproducible.
            created_at=dt.datetime.combine(as_of, dt.time(10, 0)),
        )
    )
    db.commit()
    db.refresh(invoice)

    # Recompute after the mutation so the reply already shows the new totals.
    summary = _summary(db, as_of)

    return MarkPaidResponse(
        id=invoice.id,
        status="Paid",
        paid_at=as_of.isoformat(),
        outstanding_total=summary.total_outstanding,
        overdue_count=_overdue_count(db, as_of),
    )
