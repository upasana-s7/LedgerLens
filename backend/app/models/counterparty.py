"""Customers and vendors.

Every GSTIN stored here is invented for the demo. They follow the real
15-character layout so the UI looks realistic, but no number is real.
"""

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Counterparty(Base):
    """A customer who owes us money, or a vendor we pay."""

    __tablename__ = "counterparties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    # "customer" = we invoice them; "vendor" = they invoice us.
    type: Mapped[str] = mapped_column(String(20))

    # Fictional GSTIN, e.g. "29SYNTH0001A1Z1". NULL for unregistered parties.
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)

    # Agreed credit period, used later to work out due dates.
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=30)
