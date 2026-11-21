"""Import transactions from a CSV file.

Expected columns (case-insensitive, order does not matter):

    date,name,amount,type,category

- `date`     ISO `YYYY-MM-DD` or Indian `DD/MM/YYYY`
- `amount`   positive number; the sign is applied from `type`
- `type`     income | expense
- `category` optional, one of the six known categories

A bad row is skipped and reported; the good rows still import. That is normal
partial success, not an error response.
"""

import datetime as dt
import io

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Transaction
from app.schemas.transaction import (
    CATEGORIES,
    TransactionResponse,
    UploadErrorRow,
    UploadResult,
)
from app.services.transactions import (
    AS_OF_DATE,
    next_transaction_id,
    parse_date,
    round_money,
)

# Columns the file must contain. `category` is optional.
REQUIRED_COLUMNS = ("date", "name", "amount", "type")


def _parse_csv_date(value: str) -> dt.date:
    """Accept ISO (`2026-11-19`) or Indian (`19/11/2026`) dates."""
    text = value.strip()
    if "/" in text:
        try:
            return dt.datetime.strptime(text, "%d/%m/%Y").date()
        except ValueError as exc:
            raise ValueError(
                "date must be YYYY-MM-DD or DD/MM/YYYY"
            ) from exc
    return parse_date(text)


def _read_frame(file_bytes: bytes) -> pd.DataFrame:
    """Read the CSV into a DataFrame, or raise a clear ValueError.

    Everything is read as text: we validate each cell ourselves so the error
    message can point at the exact row and column.
    """
    try:
        frame = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
    except Exception as exc:  # pandas raises several unrelated error types
        raise ValueError(f"Could not read the CSV file: {exc}") from exc

    frame.columns = [str(column).strip().lower() for column in frame.columns]

    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(
            "CSV is missing required column(s): " + ", ".join(missing)
        )

    return frame


def import_transactions_csv(db: Session, file_bytes: bytes) -> UploadResult:
    """Import every valid row of `file_bytes` and report what happened."""
    # An empty upload is not an error - it simply imports nothing.
    if not file_bytes or not file_bytes.strip():
        return UploadResult(imported=0, skipped=0, rows=[], errors=[])

    frame = _read_frame(file_bytes)

    good_rows: list[Transaction] = []
    errors: list[UploadErrorRow] = []

    # `enumerate(..., start=1)` counts data rows from 1, so a problem in the
    # first row after the header is reported as row 1.
    for row_number, row in enumerate(frame.to_dict(orient="records"), start=1):
        try:
            raw_date = str(row.get("date", "")).strip()
            raw_name = str(row.get("name", "")).strip()
            raw_amount = str(row.get("amount", "")).strip()
            raw_type = str(row.get("type", "")).strip().lower()
            raw_category = str(row.get("category", "")).strip()

            if not raw_name:
                raise ValueError("name is required")

            when = _parse_csv_date(raw_date)
            if when > AS_OF_DATE:
                raise ValueError(
                    f"date {when.isoformat()} is after the demo date "
                    f"{AS_OF_DATE.isoformat()}"
                )

            try:
                amount = round_money(float(raw_amount))
            except ValueError as exc:
                raise ValueError("amount is not a number") from exc
            if amount <= 0:
                raise ValueError("amount must be greater than 0")

            if raw_type not in ("income", "expense"):
                raise ValueError("type must be income or expense")

            category = raw_category or "General"
            if category not in CATEGORIES:
                raise ValueError(
                    f"category must be one of {', '.join(CATEGORIES)}"
                )

            good_rows.append(
                Transaction(
                    # The id is filled in below, once we know how many rows
                    # survived validation.
                    id="",
                    date=when,
                    name=raw_name,
                    category=category,
                    amount=amount if raw_type == "income" else -amount,
                    type=raw_type,
                    payment_mode="Bank transfer",
                    source="csv",
                    created_at=dt.datetime.combine(when, dt.time(10, 0)),
                )
            )
        except ValueError as exc:
            errors.append(UploadErrorRow(row=row_number, message=str(exc)))

    # Continue the TXN sequence from the current maximum.
    start_number = int(next_transaction_id(db).split("-")[1])
    for offset, transaction in enumerate(good_rows):
        transaction.id = f"TXN-{start_number + offset:04d}"

    if good_rows:
        db.add_all(good_rows)
        db.commit()
        for transaction in good_rows:
            db.refresh(transaction)

    return UploadResult(
        imported=len(good_rows),
        skipped=len(errors),
        rows=[TransactionResponse.model_validate(row) for row in good_rows],
        errors=errors,
    )
