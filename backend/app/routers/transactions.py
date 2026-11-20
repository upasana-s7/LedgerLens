"""Transactions router - list, create and CSV import.

Logic arrives in Stage 3. See docs/API_CONTRACT.md for the data shape.

Note on route order: `/transactions/upload` is declared before any `/.../{id}`
route would be, so "upload" is never mistaken for an id.
"""

from typing import Optional

from fastapi import APIRouter, File, Query, UploadFile

from app.routers import not_implemented

router = APIRouter(tags=["Transactions"])


@router.get("/transactions")
def list_transactions(
    q: Optional[str] = None,
    type: Optional[str] = None,
    category: Optional[str] = None,
    # `from` is a Python keyword, so the parameter is named `from_` and the
    # public query name stays `?from=` via the alias.
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    page: int = 1,
    limit: int = 50,
) -> dict:
    """Search / filter transactions, newest first, paginated."""
    raise not_implemented(3)


@router.post("/transactions", status_code=201)
def create_transaction() -> dict:
    """Create one transaction. The backend sets the sign and the next TXN id."""
    raise not_implemented(3)


@router.post("/transactions/upload", status_code=201)
def upload_transactions(file: UploadFile = File(...)) -> dict:
    """Import transactions from a CSV file (returns imported/skipped rows)."""
    raise not_implemented(3)
