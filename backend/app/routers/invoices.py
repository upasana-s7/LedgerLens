"""Invoices router - list, mark paid (Stage 7), upload + confirm (Stage 9).

The logic lives in `app/services/invoices.py`; these functions only deal with
HTTP: dependency injection, response models and mapping service errors to
status codes.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.routers import not_implemented
from app.schemas.invoice import InvoiceListResponse, MarkPaidResponse
from app.services import invoices as service

router = APIRouter(tags=["Invoices"])


@router.get("/invoices", response_model=InvoiceListResponse)
def list_invoices(db: Session = Depends(get_db)) -> InvoiceListResponse:
    """All invoices plus the outstanding / overdue / collected summary."""
    return service.build_invoice_list(db)


@router.post("/invoices/{invoice_id}/mark-paid", response_model=MarkPaidResponse)
def mark_invoice_paid(
    invoice_id: str, db: Session = Depends(get_db)
) -> MarkPaidResponse:
    """Mark one invoice as Paid, record the income and return fresh totals."""
    try:
        return service.mark_paid(db, invoice_id)
    except service.InvoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # Already paid, or a draft that has to be confirmed first.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# Declared after the {invoice_id} route but on a different path segment count,
# so there is no conflict: "upload" only matches this exact path.
@router.post("/invoices/upload", status_code=201)
def upload_invoice(file: UploadFile = File(...)) -> dict:
    """Extract fields from an invoice photo/PDF and save it as a Draft."""
    raise not_implemented(9)


@router.post("/invoices/{invoice_id}/confirm")
def confirm_invoice(invoice_id: str) -> dict:
    """Save the reviewed fields and move a Draft invoice to Pending."""
    raise not_implemented(9)
