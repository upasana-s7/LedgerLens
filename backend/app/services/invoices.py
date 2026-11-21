"""Invoice and receivables logic (Stage 7).

Two rules drive everything here:

* **"Overdue" is never stored.** The database holds only "Draft", "Pending" and
  "Paid"; overdue is computed from `due_date` against the demo date, so the
  list cannot go stale when a day passes.
* **Marking an invoice paid always writes the matching income transaction.**
  The receivables screen and the cash balance then move together instead of
  drifting apart.

A "Draft" invoice (created by the Stage 9 upload flow) cannot be marked paid:
a human has to review and confirm the extracted fields first.

Stage 9 adds the two ends of that flow:

* **Upload validates first.** A file is checked for type and size before any
  extraction is attempted, so an unsupported file is a clean 400.
* **Extraction is best-effort and never fails an upload.** If Gemini is
  unconfigured, errors, or returns unreadable fields, the invoice is still
  created as a Draft with warnings and zeros, because a human reviews and
  corrects the fields before confirming.
* **Confirm is the gate into receivables.** Draft -> Pending is the only
  transition that makes an invoice count, which is why `amount` and `due_date`
  are only trusted after this step.
* **Uploaded files persist** in `uploads/` (git-ignored), named after the
  invoice id, so the original document can be shown next to the extracted
  fields.
"""

import datetime as dt
import json
import os
import re
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Counterparty, Invoice, Transaction
from app.schemas.invoice import (
    AgingBucket,
    InvoiceConfirmRequest,
    InvoiceConfirmResponse,
    InvoiceExtractedFields,
    InvoiceItem,
    InvoiceListResponse,
    InvoiceSummary,
    InvoiceUploadResponse,
    MarkPaidResponse,
    ReceivableListResponse,
)

# Stage 9 uploads: accepted types, size cap and where the originals live.
ALLOWED_MIME = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
MAX_BYTES = 5 * 1024 * 1024
UPLOAD_DIR = "uploads"

INVOICE_ID_RE = re.compile(r"^INV-(\d+)$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Used when the document's own number could not be read.
UNKNOWN_CLIENT = "Unknown (needs review)"
# A Draft needs a payable-looking amount for the NOT NULL column; confirm
# replaces it with what the user typed.
DRAFT_PLACEHOLDER_AMOUNT = Decimal("0.01")
from app.services.transactions import next_transaction_id, round_money

# The demo's fixed "today". Parsed once so every response agrees.
AS_OF_DATE = dt.date.fromisoformat(settings.AS_OF_DATE)

# The ageing chart always shows these four columns, in this order.
AGING_LABELS = ("Current", "1-30 days", "31-60 days", "60+ days")

DisplayStatus = Literal["Draft", "Pending", "Overdue", "Paid"]


class InvoiceNotFoundError(ValueError):
    """Unknown invoice id - the router turns this into a 404."""


class InvoiceStateError(ValueError):
    """The invoice exists but cannot change state - the router sends a 409."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _money(value) -> Decimal:
    """Rupees to 2 decimal places, following the forecast engine's convention."""
    return round_money(Decimal(str(value or 0)))


def _compute_display_status(
    invoice: Invoice, as_of: dt.date
) -> tuple[DisplayStatus, int]:
    """Return `(display_status, days_overdue)` for one invoice."""
    if invoice.status == "Paid":
        return ("Paid", 0)
    if invoice.status == "Draft":
        return ("Draft", 0)
    # Anything still "Pending" is overdue once its due date has passed.
    if invoice.due_date < as_of:
        return ("Overdue", (as_of - invoice.due_date).days)
    return ("Pending", 0)


def _to_item(invoice: Invoice, as_of: dt.date) -> InvoiceItem:
    """Convert an ORM invoice into the flat row the frontend renders."""
    status, days_overdue = _compute_display_status(invoice, as_of)
    return InvoiceItem(
        id=invoice.id,
        client=invoice.client,
        due_date=invoice.due_date.isoformat(),
        amount=float(_money(invoice.amount)),
        status=status,
        days_overdue=days_overdue,
    )


def _summary(db: Session, as_of: dt.date) -> InvoiceSummary:
    """The four counters above the invoice list."""
    invoices = list(db.scalars(select(Invoice)).all())
    pending = [invoice for invoice in invoices if invoice.status == "Pending"]

    total_outstanding = _money(
        sum((_money(invoice.amount) for invoice in pending), Decimal("0.00"))
    )
    overdue_total = _money(
        sum(
            (
                _money(invoice.amount)
                for invoice in pending
                if invoice.due_date < as_of
            ),
            Decimal("0.00"),
        )
    )

    # "This month" runs from the 1st of the demo month through the demo date.
    month_start = as_of.replace(day=1)
    collected = _money(
        sum(
            (
                _money(invoice.paid_amount)
                for invoice in invoices
                if invoice.status == "Paid"
                and invoice.paid_date is not None
                and month_start <= invoice.paid_date <= as_of
            ),
            Decimal("0.00"),
        )
    )

    return InvoiceSummary(
        total_outstanding=float(total_outstanding),
        outstanding_count=len(pending),
        overdue_total=float(overdue_total),
        collected_this_month=float(collected),
    )


def _aging(invoices: list[Invoice], as_of: dt.date) -> list[AgingBucket]:
    """Bucket unpaid invoices by how long they have been outstanding."""
    counts = {label: 0 for label in AGING_LABELS}
    totals = {label: Decimal("0.00") for label in AGING_LABELS}

    for invoice in invoices:
        if invoice.status != "Pending":
            continue
        _, days_overdue = _compute_display_status(invoice, as_of)
        if invoice.due_date >= as_of:
            label = "Current"
        elif days_overdue <= 30:
            label = "1-30 days"
        elif days_overdue <= 60:
            label = "31-60 days"
        else:
            label = "60+ days"
        counts[label] += 1
        totals[label] += _money(invoice.amount)

    return [
        AgingBucket(label=label, count=counts[label], amount=float(totals[label]))
        for label in AGING_LABELS
    ]


def _overdue_count(db: Session, as_of: dt.date) -> int:
    """How many unpaid invoices are past due right now (a fresh query)."""
    return (
        db.scalar(
            select(func.count())
            .select_from(Invoice)
            .where(Invoice.status == "Pending", Invoice.due_date < as_of)
        )
        or 0
    )


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def build_invoice_list(db: Session) -> InvoiceListResponse:
    """Every invoice, newest issue date first, with the summary counters."""
    as_of = AS_OF_DATE

    invoices = list(
        db.scalars(
            select(Invoice).order_by(Invoice.issue_date.desc(), Invoice.id.desc())
        ).all()
    )

    return InvoiceListResponse(
        summary=_summary(db, as_of),
        items=[_to_item(invoice, as_of) for invoice in invoices],
    )


def build_receivable_list(db: Session) -> ReceivableListResponse:
    """Open invoices only, the most overdue first, plus collection progress."""
    as_of = AS_OF_DATE

    pending = list(
        db.scalars(select(Invoice).where(Invoice.status == "Pending")).all()
    )
    # Overdue first (False sorts before True), then the oldest due date, so the
    # longest-late invoice leads the list.
    pending.sort(key=lambda invoice: (invoice.due_date >= as_of, invoice.due_date, invoice.id))

    outstanding_total = _money(
        sum((_money(invoice.amount) for invoice in pending), Decimal("0.00"))
    )
    overdue_count = sum(1 for invoice in pending if invoice.due_date < as_of)

    collected = _money(_summary(db, as_of).collected_this_month)
    denominator = collected + outstanding_total
    progress = int(round(collected / denominator * 100)) if denominator > 0 else 0

    return ReceivableListResponse(
        outstanding_total=float(outstanding_total),
        overdue_count=overdue_count,
        collection_progress_pct=progress,
        aging_buckets=_aging(pending, as_of),
        items=[_to_item(invoice, as_of) for invoice in pending],
    )


def mark_paid(db: Session, invoice_id: str) -> MarkPaidResponse:
    """Collect one invoice: flip it to Paid and record the cash coming in.

    The linked income transaction is what keeps the two screens honest - the
    invoice leaves the receivables list and the money shows up in the ledger on
    the same date. Drafts are refused because their fields are unconfirmed.
    """
    as_of = AS_OF_DATE

    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
    if invoice.status == "Paid":
        raise InvoiceStateError(f"Invoice {invoice_id} is already paid")
    if invoice.status == "Draft":
        raise InvoiceStateError(
            f"Invoice {invoice_id} is a draft; confirm it before marking as paid"
        )

    amount = _money(invoice.amount)

    invoice.status = "Paid"
    invoice.paid_amount = amount
    invoice.paid_date = as_of

    db.add(
        Transaction(
            id=next_transaction_id(db),
            date=as_of,
            name=f"{invoice.client} — payment for {invoice.id}",
            category="Sales",
            amount=amount,  # positive: money in
            type="income",
            counterparty_id=invoice.counterparty_id,
            payment_mode="Bank transfer",
            invoice_id=invoice.id,
            source="invoice",
            # Derived from the demo date, not the wall clock, so the data stays
            # reproducible.
            created_at=dt.datetime.combine(as_of, dt.time(10, 0)),
        )
    )
    db.commit()
    db.refresh(invoice)

    # Recompute after the mutation so the reply already shows the new totals.
    summary = _summary(db, as_of)

    return MarkPaidResponse(
        id=invoice.id,
        status="Paid",
        paid_at=as_of.isoformat(),
        outstanding_total=summary.total_outstanding,
        overdue_count=_overdue_count(db, as_of),
    )


# ---------------------------------------------------------------------------
# Stage 9 - upload (extraction) and confirm
# ---------------------------------------------------------------------------

def _validate_upload(filename: str, content: bytes, content_type: str) -> None:
    """Reject the wrong kind of file, or one that is too large, before any work."""
    if content_type not in ALLOWED_MIME:
        raise ValueError(
            f"Unsupported file type: {content_type}. Accepted: PDF, PNG, JPG"
        )
    if len(content) > MAX_BYTES:
        raise ValueError("File exceeds 5 MB limit")


def _next_invoice_id(db: Session) -> str:
    """The next free `INV-nnn`, counted from the highest number already stored."""
    highest = 0
    for invoice_id in db.scalars(select(Invoice.id)).all():
        match = INVOICE_ID_RE.match(invoice_id or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"INV-{highest + 1:03d}"


def _empty_extraction() -> dict:
    """The "nothing could be read" shape, used by every failure path."""
    return {"client": "", "due_date": "", "amount": 0, "invoice_number": ""}


def _extract_with_gemini(content: bytes, mime_type: str) -> dict:
    """Ask Gemini vision for the four fields. Tests monkeypatch this function.

    The SDK is imported lazily so the rest of the app (and the test suite) never
    needs the dependency or a key. Any exception propagates to the caller, which
    decides whether to fall back - this function never swallows failures.
    """
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options={"timeout": 30_000},
    )

    prompt = """
Extract the following fields from this invoice image/document and return them as a strict JSON object with keys:
- client (string, the customer/counterparty name on the bill-to section)
- due_date (string, ISO YYYY-MM-DD; if only payment terms are shown, compute due date from issue_date)
- amount (number, total in Indian Rupees as a positive number; if GST is present, use the grand total including GST)
- invoice_number (string, the invoice number from the document)

Rules:
- If a field is unreadable or missing, use empty string for text fields and 0 for amount.
- Do NOT invent values. Do NOT add other fields. Return ONLY the JSON object, no markdown, no explanation.
""".strip()

    contents = [
        prompt,
        genai_types.Part.from_bytes(data=content, mime_type=mime_type),
    ]
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=contents,
    )

    text = (response.text or "").strip()
    if not text:
        return _empty_extraction()

    # Models often wrap JSON in a markdown fence even when told not to.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return _empty_extraction()
    if not isinstance(data, dict):
        return _empty_extraction()

    return {
        "client": str(data.get("client", "") or ""),
        "due_date": str(data.get("due_date", "") or ""),
        "amount": data.get("amount", 0),
        "invoice_number": str(data.get("invoice_number", "") or ""),
    }


def _resolve_counterparty(db: Session, client: str) -> int:
    """Reuse the customer row with this name, or add one as a customer."""
    existing = db.scalar(
        select(Counterparty).where(func.lower(Counterparty.name) == client.lower())
    )
    if existing is not None:
        return existing.id

    top_id = db.scalar(select(func.max(Counterparty.id))) or 0
    new = Counterparty(id=top_id + 1, name=client[:120], type="customer")
    db.add(new)
    db.flush()  # assign the id without committing yet
    return new.id


def upload_invoice(
    db: Session, filename: str, content: bytes, content_type: str
) -> InvoiceUploadResponse:
    """Store the file as a Draft and suggest fields read from the document.

    Goes through three stages in this order: validate, extract (best-effort),
    then persist. Extraction problems become `warnings`, never an error, because
    the review screen lets the user type the correct values and confirm.
    """
    _validate_upload(filename, content, content_type)

    invoice_id = _next_invoice_id(db)
    warnings: list[str] = []

    if settings.GEMINI_API_KEY:
        try:
            extracted = _extract_with_gemini(content, content_type)
        except Exception as exc:  # noqa: BLE001 - extraction must never 500
            warnings.append(
                f"Automatic extraction failed: {type(exc).__name__}. "
                "Please fill fields manually."
            )
            extracted = _empty_extraction()
    else:
        warnings.append(
            "Gemini API key not configured; extraction skipped. "
            "Fill fields manually."
        )
        extracted = _empty_extraction()

    client = str(extracted.get("client", "") or "").strip()
    due_date = str(extracted.get("due_date", "") or "").strip()
    try:
        amount = float(extracted.get("amount", 0) or 0)
    except (ValueError, TypeError):
        amount = 0.0
    invoice_number = str(extracted.get("invoice_number", "") or "").strip()

    if not client:
        warnings.append("Could not read customer name.")
    if not due_date or not ISO_DATE_RE.match(due_date):
        warnings.append("Could not read a valid due date (ISO format expected).")
        due_date = ""
    if amount <= 0:
        warnings.append("Could not read invoice total.")
    if not invoice_number:
        warnings.append("Could not read invoice number.")

    confidence = (
        sum(
            [
                bool(client),
                bool(due_date),
                amount > 0,
                bool(invoice_number),
            ]
        )
        / 4.0
    )

    stored_due_date = (
        dt.date.fromisoformat(due_date)
        if due_date
        else AS_OF_DATE + dt.timedelta(days=30)
    )
    stored_amount = (
        Decimal(str(amount)).quantize(Decimal("0.01"))
        if amount > 0
        else DRAFT_PLACEHOLDER_AMOUNT
    )
    stored_client = client or UNKNOWN_CLIENT

    invoice = Invoice(
        id=invoice_id,
        invoice_number=invoice_number or None,
        counterparty_id=_resolve_counterparty(db, stored_client),
        client=stored_client,
        # The document's issue date is not extracted reliably, so the demo
        # "today" is used; the user confirms the due date that actually matters.
        issue_date=AS_OF_DATE,
        due_date=stored_due_date,
        amount=stored_amount,
        gst_amount=Decimal("0.00"),
        status="Draft",
        paid_amount=Decimal("0.00"),
        source="extracted",
        extraction_json=json.dumps(extracted),
        confidence=confidence,
    )
    db.add(invoice)

    # The original document is kept next to the review screen's fields.
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(f"{UPLOAD_DIR}/{invoice_id}{ALLOWED_MIME[content_type]}", "wb") as fh:
        fh.write(content)

    db.commit()
    db.refresh(invoice)

    return InvoiceUploadResponse(
        id=invoice.id,
        status="Draft",
        fields=InvoiceExtractedFields(
            client=client,
            due_date=due_date,
            amount=amount if amount > 0 else 0.0,
            invoice_number=invoice_number,
        ),
        confidence=confidence,
        warnings=warnings,
    )


def confirm_invoice(
    db: Session, invoice_id: str, payload: InvoiceConfirmRequest
) -> InvoiceConfirmResponse:
    """Accept the reviewed fields and move a Draft invoice into receivables."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise InvoiceNotFoundError(f"Invoice {invoice_id} not found")
    if invoice.status != "Draft":
        raise InvoiceStateError(
            f"Invoice {invoice_id} is already {invoice.status}, not Draft"
        )

    invoice.client = payload.client
    invoice.invoice_number = payload.invoice_number
    invoice.due_date = dt.date.fromisoformat(payload.due_date)
    invoice.amount = Decimal(str(payload.amount)).quantize(Decimal("0.01"))
    # A customer name may be new after the user corrected the extracted one.
    invoice.counterparty_id = _resolve_counterparty(db, invoice.client)
    invoice.status = "Pending"

    db.commit()
    db.refresh(invoice)

    return InvoiceConfirmResponse(
        id=invoice.id,
        status="Pending",
        invoice=_to_item(invoice, AS_OF_DATE),
    )
