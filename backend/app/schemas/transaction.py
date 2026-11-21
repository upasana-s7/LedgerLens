"""Request and response shapes for transactions.

Pydantic v2 is used here. Response models set `from_attributes=True` so a
SQLAlchemy `Transaction` object can be handed straight to FastAPI and it will
be serialised field by field (`TransactionResponse.model_validate(row)`).

Money leaves the API as a plain JSON **number** in rupees - never a string.
"""

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The only categories the app understands. Anything else is rejected.
CATEGORIES = ("Sales", "Inventory", "Rent", "Utilities", "Payroll", "General")


class TransactionResponse(BaseModel):
    """One transaction as the frontend receives it."""

    # Allows `TransactionResponse.model_validate(orm_object)`.
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    category: str
    # ISO "YYYY-MM-DD". The database stores a real date, so a validator turns
    # it into a string when the object is serialised.
    date: str
    # Signed: negative for expenses, positive for income.
    amount: float
    type: Literal["income", "expense"]

    @field_validator("date", mode="before")
    @classmethod
    def _date_to_iso(cls, value: object) -> object:
        """Accept a `date`/`datetime` from the ORM and emit an ISO string."""
        if isinstance(value, (dt.date, dt.datetime)):
            return value.isoformat()[:10]
        return value


class TransactionCreate(BaseModel):
    """Body of `POST /api/transactions`.

    The client always sends a **positive** amount plus a `type`; the service
    applies the sign. `amount > 0` is enforced here, which is why a
    zero/negative amount is a 422 without any custom code.
    """

    name: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0)
    type: Literal["income", "expense"]
    category: str | None = None
    # Optional: when omitted the service uses the demo "today" (AS_OF_DATE).
    date: str | None = None


class TransactionListResponse(BaseModel):
    """One page of transactions, plus the count after filtering."""

    total: int
    page: int
    limit: int
    items: list[TransactionResponse]


class UploadErrorRow(BaseModel):
    """One CSV row that could not be imported."""

    # 1-based CSV line number, counting the header as line 1.
    row: int
    message: str


class UploadResult(BaseModel):
    """Summary of a CSV import: what landed and what was rejected."""

    imported: int
    skipped: int
    rows: list[TransactionResponse]
    errors: list[UploadErrorRow]
