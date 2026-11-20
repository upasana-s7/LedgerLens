"""Invoices we have sent to customers.

Important rule: only "Draft", "Pending" and "Paid" are ever stored. "Overdue"
is NOT stored - it is worked out later by comparing `due_date` with the
business's `as_of_date`. Storing it would mean the data goes stale the moment
a day passes.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Invoice(Base):
    """A bill sent to a customer, and what has been paid against it."""

    __tablename__ = "invoices"

    # Human-readable id such as "INV-204".
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    # The number printed on the paper invoice, if we know it.
    invoice_number: Mapped[str | None] = mapped_column(String(40), nullable=True)

    counterparty_id: Mapped[int] = mapped_column(ForeignKey("counterparties.id"))
    # Denormalised customer name, so a list can be rendered without a join.
    client: Mapped[str] = mapped_column(String(120))

    issue_date: Mapped[dt.date] = mapped_column(Date)
    due_date: Mapped[dt.date] = mapped_column(Date, index=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    gst_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00")
    )
    # Draft | Pending | Paid  (never "Overdue")
    status: Mapped[str] = mapped_column(String(20), index=True)

    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00")
    )
    paid_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    # Raw text returned by invoice extraction (Stage 9), kept for auditing.
    extraction_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How sure the extractor was, 0.0 - 1.0.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # synthetic | extracted | manual
    source: Mapped[str] = mapped_column(String(20), default="synthetic")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    __table_args__ = (
        Index("ix_invoices_status_due_date", "status", "due_date"),
    )
