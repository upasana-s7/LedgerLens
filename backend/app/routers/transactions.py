"""Transactions router - list, create and CSV import.

The logic lives in `app/services/transactions.py` and
`app/services/csv_import.py`; these functions only handle HTTP concerns
(query parameters, status codes and turning ValueError into 4xx responses).

Route order matters: `/transactions/upload` is declared before any
`/transactions/{id}` route would be, so "upload" is never read as an id.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.transaction import (
    TransactionCreate,
    TransactionListResponse,
    TransactionResponse,
    UploadResult,
)
from app.services import transactions as service
from app.services.csv_import import import_transactions_csv

router = APIRouter(tags=["Transactions"])


@router.get("/transactions", response_model=TransactionListResponse)
def list_transactions(
    q: Optional[str] = None,
    type: Optional[Literal["all", "income", "expense"]] = "all",
    category: Optional[str] = None,
    # `from` is a Python keyword, so the parameter is named `from_` and the
    # public query name stays `?from=` via the alias.
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TransactionListResponse:
    """Search / filter transactions, newest first, paginated."""
    try:
        items, total = service.list_transactions(
            db,
            q=q,
            type=type,
            category=category,
            from_date=from_,
            to_date=to,
            page=page,
            limit=limit,
        )
    except ValueError as exc:
        # An unparseable `from` / `to` date is a client mistake -> 422.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TransactionListResponse(
        total=total,
        page=page,
        limit=limit,
        items=[TransactionResponse.model_validate(row) for row in items],
    )


@router.post("/transactions", status_code=201, response_model=TransactionResponse)
def create_transaction(
    payload: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TransactionResponse:
    """Create one transaction. The backend sets the sign and the next TXN id."""
    try:
        transaction = service.create_transaction(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return TransactionResponse.model_validate(transaction)


@router.post("/transactions/upload", response_model=UploadResult)
def upload_transactions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UploadResult:
    """Import transactions from a CSV file (returns imported/skipped rows).

    A malformed file (missing column, unreadable bytes) is a 400. Individual
    bad rows are skipped and listed in `errors` instead.
    """
    file_bytes = file.file.read()

    try:
        return import_transactions_csv(db, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
