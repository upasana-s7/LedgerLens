"""Invoices router - list, mark paid (Stage 7), upload + confirm (Stage 9).

The logic lives in `app/services/invoices.py`; these functions only deal with
HTTP: dependency injection, response models and mapping service errors to
status codes.
"""

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.invoice import (
    InvoiceConfirmRequest,
    InvoiceConfirmResponse,
    InvoiceListResponse,
    InvoiceUploadResponse,
    MarkPaidResponse,
)
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
@router.post(
    "/invoices/upload", status_code=201, response_model=InvoiceUploadResponse
)
async def upload_invoice_endpoint(
    file: UploadFile = File(...), db: Session = Depends(get_db)
) -> InvoiceUploadResponse:
    """Extract fields from an invoice photo/PDF and save it as a Draft.

    A 201 means the file was accepted and stored. Extraction problems come back
    as `warnings`, not as errors, because the user can still fill the fields in.
    """
    content = await file.read()
    try:
        return service.upload_invoice(
            db,
            file.filename or "upload",
            content,
            file.content_type or "application/octet-stream",
        )
    except ValueError as exc:
        # Unsupported type or oversize file: nothing was stored.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/invoices/{invoice_id}/confirm", response_model=InvoiceConfirmResponse)
def confirm_invoice_endpoint(
    invoice_id: str,
    payload: InvoiceConfirmRequest,
    db: Session = Depends(get_db),
) -> InvoiceConfirmResponse:
    """Save the reviewed fields and move a Draft invoice to Pending."""
    try:
        return service.confirm_invoice(db, invoice_id, payload)
    except service.InvoiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.InvoiceStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
