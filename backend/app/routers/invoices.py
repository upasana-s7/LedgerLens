"""Invoices router - list, upload a bill photo/PDF, confirm, mark paid.

Logic arrives in Stage 7 (list / mark paid) and Stage 9 (upload + confirm).
"""

from fastapi import APIRouter, File, UploadFile

from app.routers import not_implemented

router = APIRouter(tags=["Invoices"])


@router.get("/invoices")
def list_invoices() -> dict:
    """All invoices plus the outstanding / overdue / collected summary."""
    raise not_implemented(7)


@router.post("/invoices/{invoice_id}/mark-paid")
def mark_invoice_paid(invoice_id: str) -> dict:
    """Mark one invoice as Paid and return the updated totals."""
    raise not_implemented(7)


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
