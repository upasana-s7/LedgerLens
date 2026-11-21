"""Receivables router - who owes money, and marking it collected.

Both routes delegate to `app/services/invoices.py`, so the Receivables screen
and the Invoices screen always agree on the numbers.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.invoice import MarkPaidResponse, ReceivableListResponse
from app.services import invoices as service

router = APIRouter(tags=["Receivables"])


@router.get("/receivables", response_model=ReceivableListResponse)
def get_receivables(db: Session = Depends(get_db)) -> ReceivableListResponse:
    """Unpaid invoices, overdue first, with collection progress and ageing."""
    return service.build_receivable_list(db)


@router.post("/receivables/{invoice_id}/mark-paid", response_model=MarkPaidResponse)
def mark_receivable_paid(
    invoice_id: str, db: Session = Depends(get_db)
) -> MarkPaidResponse:
    """Mark one invoice as collected (same behaviour as the invoice route)."""
    try:
        return service.mark_paid(db, invoice_id)
    except service.InvoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
