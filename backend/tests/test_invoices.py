"""Tests for the Stage 7 invoice endpoints.

The fixtures build a throw-away in-memory copy of the seeded database, so these
assert real numbers from the Bloom & Bean data rather than hardcoded payloads.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import Counterparty, Invoice, Transaction
from app.services.transactions import next_transaction_id

AS_OF_DATE = dt.date(2026, 11, 19)


@pytest.fixture()
def invoice_list(client):
    """The invoice list payload, fetched once per test."""
    response = client.get("/api/invoices")
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def test_invoices_summary_matches_seed(invoice_list):
    """Open invoices, overdue money and November collections are the seed's."""
    summary = invoice_list["summary"]
    assert summary["total_outstanding"] == 109500
    assert summary["outstanding_count"] == 3
    assert summary["overdue_total"] == 85000
    assert summary["collected_this_month"] == 184000


def test_invoices_items_include_paid_and_pending(invoice_list):
    """Every invoice is listed, paid history included: 25 rows, 3 open."""
    items = invoice_list["items"]
    assert len(items) == 25
    assert sum(1 for item in items if item["status"] in {"Pending", "Overdue"}) == 3
    assert sum(1 for item in items if item["status"] == "Paid") == 22


def test_invoices_sorted_newest_issue_date_first(invoice_list):
    """The list reads like a ledger: most recently issued first."""
    items = invoice_list["items"]
    assert items[0]["id"] == "INV-211"
    assert items[1]["id"] == "INV-206"


def test_overdue_computed_correctly(invoice_list):
    """INV-204 is 7 days late, INV-198 is 11, INV-211 is not due yet."""
    by_id = {item["id"]: item for item in invoice_list["items"]}

    assert by_id["INV-204"]["status"] == "Overdue"
    assert by_id["INV-204"]["days_overdue"] == 7
    assert by_id["INV-198"]["status"] == "Overdue"
    assert by_id["INV-198"]["days_overdue"] == 11
    assert by_id["INV-211"]["status"] == "Pending"
    assert by_id["INV-211"]["days_overdue"] == 0


def test_paid_invoices_have_no_days_overdue(invoice_list):
    """A settled invoice is never counted as late, however old it is."""
    paid = [item for item in invoice_list["items"] if item["status"] == "Paid"]
    assert paid
    assert all(item["days_overdue"] == 0 for item in paid)


# ---------------------------------------------------------------------------
# Mark paid
# ---------------------------------------------------------------------------

def test_mark_paid_mutates_and_creates_transaction(client, seeded_db):
    """Collecting INV-204 flips the row and writes a linked income row."""
    response = client.post("/api/invoices/INV-204/mark-paid")
    assert response.status_code == 200

    invoice = seeded_db.get(Invoice, "INV-204")
    seeded_db.refresh(invoice)
    assert invoice.status == "Paid"
    assert invoice.paid_amount == Decimal("52000.00")
    assert invoice.paid_date == AS_OF_DATE

    payment = seeded_db.scalar(
        select(Transaction).where(Transaction.invoice_id == "INV-204")
    )
    assert payment is not None
    assert payment.amount == Decimal("52000.00")
    assert payment.type == "income"
    assert payment.source == "invoice"
    assert payment.date == AS_OF_DATE
    assert payment.counterparty_id == invoice.counterparty_id


def test_mark_paid_response_totals(client):
    """INV-198 is still 11 days late, so one overdue invoice remains."""
    body = client.post("/api/invoices/INV-204/mark-paid").json()

    assert body["id"] == "INV-204"
    assert body["status"] == "Paid"
    assert body["paid_at"] == "2026-11-19"
    assert body["outstanding_total"] == 57500
    assert body["overdue_count"] == 1


def test_mark_paid_is_reflected_in_the_list(client):
    """The next GET shows the invoice as paid and the totals shrunk."""
    client.post("/api/invoices/INV-204/mark-paid")

    body = client.get("/api/invoices").json()
    by_id = {item["id"]: item for item in body["items"]}

    assert by_id["INV-204"]["status"] == "Paid"
    assert by_id["INV-204"]["days_overdue"] == 0
    assert body["summary"]["total_outstanding"] == 57500
    assert body["summary"]["outstanding_count"] == 2
    assert body["summary"]["overdue_total"] == 33000


def test_mark_paid_unknown_returns_404(client):
    """A missing invoice is a 404 with a readable message."""
    response = client.post("/api/invoices/NOPE-999/mark-paid")

    assert response.status_code == 404
    assert response.json() == {"detail": "Invoice NOPE-999 not found"}


def test_mark_paid_already_paid_returns_409(client):
    """Collecting the same invoice twice is a conflict, not a second payment."""
    response = client.post("/api/invoices/INV-206/mark-paid")

    assert response.status_code == 409
    assert response.json() == {"detail": "Invoice INV-206 is already paid"}


def test_mark_paid_draft_returns_409(client, seeded_db):
    """Drafts must be confirmed first, so a direct mark-paid is refused."""
    counterparty_id = seeded_db.scalar(select(Counterparty.id))
    seeded_db.add(
        Invoice(
            id="INV-212",
            counterparty_id=counterparty_id,
            client="Cafe Bloom",
            issue_date=dt.date(2026, 11, 15),
            due_date=dt.date(2026, 12, 15),
            amount=Decimal("31000.00"),
            status="Draft",
            paid_amount=Decimal("0.00"),
            paid_date=None,
            source="extracted",
        )
    )
    seeded_db.commit()

    response = client.post("/api/invoices/INV-212/mark-paid")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Invoice INV-212 is a draft; confirm it before marking as paid"
    }


def test_next_txn_id_increments(client, seeded_db):
    """The payment takes the next free TXN id and the sequence moves on."""
    before = next_transaction_id(seeded_db)
    assert before == "TXN-1049"

    client.post("/api/invoices/INV-204/mark-paid")

    assert seeded_db.scalar(select(func.count()).select_from(Transaction)) == 162
    assert next_transaction_id(seeded_db) == "TXN-1050"
