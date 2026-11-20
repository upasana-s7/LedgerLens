"""A record of one CSV or invoice file a user uploaded.

Keeping a batch row means an import can be explained later: which file, how
many rows landed, and exactly which rows were rejected and why.
"""

import datetime as dt

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UploadBatch(Base):
    """One imported file."""

    __tablename__ = "upload_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    # "transactions" (CSV) or "invoice" (image/PDF)
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))

    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)

    # JSON list of {"row": 7, "message": "..."} shown back to the user.
    errors_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
