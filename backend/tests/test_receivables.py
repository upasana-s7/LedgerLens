"""Tests for the Stage 7 receivables endpoints.

These check the collection screen specifically: open invoices only, the
overdue-first ordering, the ageing buckets and the progress bar.
"""

import pytest

AS_OF_DATE = "2026-11-19"


@pytest.fixture()
def receivables(client):
    """The receivables payload, fetched once per test."""
    response = client.get("/api/receivables")
    assert response.status_code == 200
    return response.json()


def _bucket(body, label):
    """The ageing bucket with this label."""
    return next(item for item in body["aging_buckets"] if item["label"] == label)


def test_receivables_total_and_count(receivables):
    """52,000 + 33,000 + 24,500 open, two of them already late."""
    assert receivables["outstanding_total"] == 109500
    assert receivables["overdue_count"] == 2


def test_receivables_collection_progress(receivables):
    """184,000 collected of 293,500 billed: 63% rounded."""
    pct = receivables["collection_progress_pct"]
    assert isinstance(pct, int)
    assert 60 <= pct <= 65
    assert pct == 63


def test_receivables_only_pending(receivables):
    """Drafts and settled invoices never appear on the collection screen."""
    items = receivables["items"]
    assert items
    assert all(item["status"] in {"Pending", "Overdue"} for item in items)


def test_receivables_sorted_overdue_first(receivables):
    """Every overdue invoice comes before every one that is not due yet."""
    items = receivables["items"]
    flags = [item["status"] == "Overdue" for item in items]

    assert flags == sorted(flags, reverse=True)
    assert items[0]["status"] == "Overdue"
    assert items[0]["id"] == "INV-198"  # oldest due date, so the most late

    overdue_dates = [item["due_date"] for item in items if item["status"] == "Overdue"]
    assert overdue_dates == sorted(overdue_dates)


def test_aging_buckets_are_four_in_order(receivables):
    """The chart always has the same four columns."""
    assert [item["label"] for item in receivables["aging_buckets"]] == [
        "Current",
        "1-30 days",
        "31-60 days",
        "60+ days",
    ]


def test_aging_buckets_current(receivables):
    """INV-211 (24,500) is not due until 28 November."""
    bucket = _bucket(receivables, "Current")
    assert bucket["count"] == 1
    assert bucket["amount"] == 24500


def test_aging_buckets_1_30(receivables):
    """INV-198 (11 days) and INV-204 (7 days) total 85,000."""
    bucket = _bucket(receivables, "1-30 days")
    assert bucket["count"] == 2
    assert bucket["amount"] == 85000


def test_aging_buckets_empty_tail(receivables):
    """Nothing in the seed is more than 30 days late."""
    for label in ("31-60 days", "60+ days"):
        bucket = _bucket(receivables, label)
        assert bucket["count"] == 0
        assert bucket["amount"] == 0


def test_receivables_after_mark_paid(client):
    """Collecting INV-204 leaves 57,500 open and one overdue invoice."""
    client.post("/api/receivables/INV-204/mark-paid")

    body = client.get("/api/receivables").json()
    assert body["outstanding_total"] == 57500
    assert body["overdue_count"] == 1
    assert len(body["items"]) == 2
    assert {item["id"] for item in body["items"]} == {"INV-198", "INV-211"}


def test_receivables_mark_paid_same_as_invoices(client):
    """Both routes return the same shape and change the same records."""
    body = client.post("/api/receivables/INV-204/mark-paid")

    assert body.status_code == 200
    assert set(body.json()) == {
        "id",
        "status",
        "paid_at",
        "outstanding_total",
        "overdue_count",
    }
    assert body.json()["id"] == "INV-204"
    assert body.json()["status"] == "Paid"
    assert body.json()["paid_at"] == AS_OF_DATE

    ids = {item["id"] for item in client.get("/api/receivables").json()["items"]}
    assert "INV-204" not in ids


def test_receivables_mark_paid_unknown_returns_404(client):
    """The receivables route shares the invoice route's error handling."""
    response = client.post("/api/receivables/NOPE-999/mark-paid")

    assert response.status_code == 404
    assert response.json() == {"detail": "Invoice NOPE-999 not found"}
