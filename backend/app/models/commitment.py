"""Money we already know is leaving the business soon.

Rent, payroll, loan EMIs and vendor payables are commitments. The forecast
(Stage 4) subtracts them so "safe to spend" is not an overstatement.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Commitment(Base):
    """A known upcoming payment."""

    __tablename__ = "commitments"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(120))
    # Always positive: this is an amount we owe, not a signed movement.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    due_date: Mapped[dt.date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(30))

    # True for repeating items such as rent or payroll.
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)

    counterparty_id: Mapped[int | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
