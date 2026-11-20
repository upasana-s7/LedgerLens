"""The business the demo data belongs to.

LedgerLens shows one workspace at a time: the fictional "Bloom & Bean".
`opening_balance` is the cash in the bank on `start_date`, before any of the
seeded transactions. Every later balance is that opening figure plus the sum
of transactions up to a given date.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import Boolean, Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BusinessProfile(Base):
    """Identity and starting point of the demo business."""

    __tablename__ = "business_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    business_type: Mapped[str] = mapped_column(String(60))
    city: Mapped[str] = mapped_column(String(60))
    industry: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="INR")

    # Cash available on start_date, in rupees.
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2))

    start_date: Mapped[dt.date] = mapped_column(Date)
    # The fixed "today" of the demo. Never the real current date.
    as_of_date: Mapped[dt.date] = mapped_column(Date)

    # Safety floor: the business should never plan to drop below this.
    min_cash_buffer: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("150000.00")
    )

    # True for generated demo data, so the UI can label it as fictional.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=True)
