"""A LedgerLens user account (Stage 11).

Authentication only: this table proves *who* is calling the API. It does NOT
partition the data. Every signed-in user sees the same shared Bloom & Bean
workspace, so no financial table carries a `user_id`.

The password is stored as a bcrypt hash, never in plain text.
"""

import datetime as dt

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """Someone who can sign in to the LedgerLens dashboard."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(120))

    # Unique + indexed: login looks the account up by email, and two accounts
    # may never share one.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    # bcrypt hash (60 chars), never the plain password.
    hashed_password: Mapped[str] = mapped_column(String(255))

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=lambda: dt.datetime.now(dt.timezone.utc)
    )
