"""Response shapes for invoices and receivables (Stage 7).

Money leaves the API as a plain JSON number in rupees, never a string. `status`
is always the *display* status, computed by the service: the database only ever
stores "Draft", "Pending" or "Paid", and "Overdue" is worked out from the due
date so it can never go stale.
"""

from typing import Literal

from pydantic import BaseModel

InvoiceStatus = Literal["Draft", "Pending", "Overdue", "Paid"]


class InvoiceItem(BaseModel):
    """One invoice row, ready to render in a list or a table."""

    id: str
    client: str
    # ISO "YYYY-MM-DD".
    due_date: str
    amount: float
    status: InvoiceStatus
    # 0 unless the invoice is overdue.
    days_overdue: int


class InvoiceSummary(BaseModel):
    """The four counters above the invoice list."""

    # Pending only: drafts are not receivables and paid invoices are history.
    total_outstanding: float
    outstanding_count: int
    overdue_total: float
    # Money actually received in the demo month so far.
    collected_this_month: float


class InvoiceListResponse(BaseModel):
    """`GET /api/invoices`: every invoice, newest issue date first."""

    summary: InvoiceSummary
    items: list[InvoiceItem]


class AgingBucket(BaseModel):
    """One column of the receivables ageing chart."""

    label: str
    count: int
    amount: float


class ReceivableListResponse(BaseModel):
    """`GET /api/receivables`: open invoices plus collection progress."""

    outstanding_total: float
    overdue_count: int
    collection_progress_pct: int
    # Always four buckets, in label order.
    aging_buckets: list[AgingBucket]
    items: list[InvoiceItem]


class MarkPaidResponse(BaseModel):
    """Result of marking one invoice as collected."""

    id: str
    status: Literal["Paid"]
    # ISO date of the demo "today" the payment was recorded on.
    paid_at: str
    # Post-update totals, so the UI can refresh its counters from this reply.
    outstanding_total: float
    overdue_count: int
