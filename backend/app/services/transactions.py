"""Transaction logic: searching, filtering, paginating and creating rows.

Everything here is plain deterministic Python. No AI, no guessing: the signs,
the ids and the validation are all worked out in code.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Transaction
from app.schemas.transaction import CATEGORIES, TransactionCreate

# The fixed "today" of the demo. Imported once so every module agrees.
AS_OF_DATE = dt.date.fromisoformat(settings.AS_OF_DATE)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def parse_date(value: str, field: str = "date") -> dt.date:
    """Turn an ISO `YYYY-MM-DD` string into a real date.

    Raises ValueError with a friendly message, which the router turns into a
    422 response. The CSV importer accepts one more format and parses that
    itself before calling the same checks.
    """
    try:
        return dt.date.fromisoformat(value.strip())
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO date like 2026-11-19") from exc


def next_transaction_id(db: Session) -> str:
    """Return the next free id, e.g. "TXN-1049" after the seeded history.

    Ids are zero-padded to four digits, so the string maximum is also the
    numeric maximum. We still parse the number, so the sequence keeps counting
    up correctly even past TXN-9999.
    """
    latest = db.scalar(select(func.max(Transaction.id)))
    if latest is None:
        return "TXN-1001"
    return f"TXN-{int(latest.split('-')[1]) + 1}"


def round_money(value: Decimal) -> Decimal:
    """Round to 2 decimal places (paisa)."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def list_transactions(
    db: Session,
    q: str | None = None,
    type: str | None = None,
    category: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    page: int = 1,
    limit: int = 50,
) -> tuple[list[Transaction], int]:
    """Filter, sort and paginate transactions.

    Returns `(items_on_this_page, total_after_filtering)` - see the contract:
    `total` is the count after filtering, not the page size.
    """
    query = select(Transaction)

    # Free text: case-insensitive substring over the name and the category.
    if q:
        pattern = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(Transaction.name).like(pattern),
                func.lower(Transaction.category).like(pattern),
            )
        )

    # "all" (or nothing) means no type filter at all.
    if type and type != "all":
        query = query.where(Transaction.type == type)

    if category:
        query = query.where(Transaction.category == category)

    if from_date:
        query = query.where(Transaction.date >= parse_date(from_date, "from"))

    if to_date:
        query = query.where(Transaction.date <= parse_date(to_date, "to"))

    # Count on the filtered query, before pagination.
    total = db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0

    # Newest first. Id breaks ties on the same day (higher id = later row).
    query = (
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )

    return list(db.scalars(query).all()), total


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def create_transaction(db: Session, payload: TransactionCreate) -> Transaction:
    """Validate one manual transaction and save it.

    The body's amount is positive; this function applies the sign so that
    `type` and `amount` can never disagree. Raises ValueError for anything the
    router should report as 422.
    """
    category = payload.category or "General"
    if category not in CATEGORIES:
        raise ValueError(
            f"category must be one of {', '.join(CATEGORIES)}"
        )

    when = parse_date(payload.date) if payload.date else AS_OF_DATE
    if when > AS_OF_DATE:
        raise ValueError(f"date cannot be after the demo date {AS_OF_DATE.isoformat()}")

    amount = round_money(Decimal(str(payload.amount)))
    if amount <= 0:
        raise ValueError("amount must be greater than 0")

    signed = amount if payload.type == "income" else -amount

    transaction = Transaction(
        id=next_transaction_id(db),
        date=when,
        name=payload.name.strip(),
        category=category,
        amount=signed,
        type=payload.type,
        payment_mode="Bank transfer",
        source="manual",
        # Derived from the row's own date (not the wall clock), so the demo
        # data stays reproducible.
        created_at=dt.datetime.combine(when, dt.time(10, 0)),
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction
