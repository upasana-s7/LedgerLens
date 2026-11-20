"""Receivables router - who owes money, and marking it collected.

Logic arrives in Stage 7.
"""

from fastapi import APIRouter

from app.routers import not_implemented

router = APIRouter(tags=["Receivables"])


@router.get("/receivables")
def get_receivables() -> dict:
    """Unpaid invoices, overdue first, with collection progress."""
    raise not_implemented(7)


@router.post("/receivables/{invoice_id}/mark-paid")
def mark_receivable_paid(invoice_id: str) -> dict:
    """Mark one invoice as collected (same behaviour as the invoice route)."""
    raise not_implemented(7)
