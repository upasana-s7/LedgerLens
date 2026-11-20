"""One message in a copilot conversation.

`evidence_json` stores the citations the answer was based on, so a reply can
always be checked against the underlying invoices or transactions.
"""

import datetime as dt

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChatMessage(Base):
    """A question from the user, or an answer from the copilot."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    # "user" | "assistant"
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)

    # JSON list of citations, e.g. [{"kind": "invoice", "id": "INV-204"}].
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
