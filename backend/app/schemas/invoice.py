"""Response shapes for invoices and receivables (Stage 7).

Money leaves the API as a plain JSON number in rupees, never a string. `status`
is always the *display* status, computed by the service: the database only ever
stores "Draft", "Pending" or "Paid", and "Overdue" is worked out from the due
date so it can never go stale.
"""

from typing import Literal

from pydantic import BaseModel, Field

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


class InvoiceExtractedFields(BaseModel):
    """What the extractor read off the uploaded document.

    Empty strings / zero mean "could not read it": the user fills those in on
    the review screen before confirming.
    """

    client: str
    # ISO "YYYY-MM-DD", or "" when the date could not be read.
    due_date: str
    # Positive rupees; 0 when the total could not be read.
    amount: float
    invoice_number: str


class InvoiceUploadResponse(BaseModel):
    """Result of uploading one invoice file. Always a Draft."""

    id: str
    status: Literal["Draft"]
    fields: InvoiceExtractedFields
    # Share of the four fields that were read successfully, 0.0 - 1.0.
    confidence: float
    # Plain-English notes for the review screen; empty when everything landed.
    warnings: list[str]


class InvoiceConfirmRequest(BaseModel):
    """The reviewed fields the user accepts."""

    client: str = Field(..., min_length=1, max_length=200)
    due_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    amount: float = Field(..., gt=0)
    invoice_number: str = Field(..., min_length=1, max_length=50)


class InvoiceConfirmResponse(BaseModel):
    """A confirmed invoice, now part of receivables."""

    id: str
    status: Literal["Pending"]
    invoice: InvoiceItem


class MarkPaidResponse(BaseModel):
    """Result of marking one invoice as collected."""

    id: str
    status: Literal["Paid"]
    # ISO date of the demo "today" the payment was recorded on.
    paid_at: str
    # Post-update totals, so the UI can refresh its counters from this reply.
    outstanding_total: float
    overdue_count: int
