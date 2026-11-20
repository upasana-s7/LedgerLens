"""A cash-flow risk the app has detected.

Table only for now - Stage 6 fills it using deterministic rules. `evidence_json`
holds the ids of the invoices/transactions that justify the alert, so every
warning can be traced back to real rows.
"""

import datetime as dt

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RiskAlert(Base):
    """One detected risk, e.g. "Overdue customer invoices"."""

    __tablename__ = "risk_alerts"

    # Human-readable id such as "RISK-1".
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    type: Mapped[str] = mapped_column(String(50))
    # high | medium | low
    severity: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))

    # JSON list of {"kind": "invoice", "id": "INV-204"}.
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # open | dismissed
    status: Mapped[str] = mapped_column(String(20), default="open")
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
