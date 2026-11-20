"""One movement of money in or out of the business.

Amounts are SIGNED: income is positive, expenses are negative. `type` always
matches that sign, and the seed/test code checks it. Keeping one signed column
means a cash balance is simply `opening_balance + SUM(amount)` - no branching
on type when adding things up.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Transaction(Base):
    """A single cash movement."""

    __tablename__ = "transactions"

    # Human-readable id such as "TXN-1048" (string, not an auto integer).
    id: Mapped[str] = mapped_column(String(20), primary_key=True)

    date: Mapped[dt.date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(200))

    # Sales | Inventory | Rent | Utilities | Payroll | General
    category: Mapped[str] = mapped_column(String(30))

    # Negative for expenses, positive for income.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    # "income" | "expense" - must always agree with the sign of `amount`.
    type: Mapped[str] = mapped_column(String(10))

    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
    # UPI | Bank transfer | Cash | Card
    payment_mode: Mapped[str] = mapped_column(String(20), default="Bank transfer")

    # Set when this income is the settlement of an invoice.
    invoice_id: Mapped[str | None] = mapped_column(
        ForeignKey("invoices.id"), nullable=True
    )

    # synthetic | csv | manual | invoice
    source: Mapped[str] = mapped_column(String(20), default="synthetic")
    upload_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("upload_batches.id"), nullable=True
    )

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    __table_args__ = (
        # The dashboard and cash-flow chart always filter/sort by date.
        Index("ix_transactions_date_type", "date", "type"),
    )
