"""Tests for the synthetic dataset.

Every test runs against a throw-away in-memory SQLite database, so the real
`ledgerlens.db` file is never touched. All data is fictional.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.core.database import Base
from app.models import BusinessProfile, Commitment, Counterparty, Invoice, Transaction
from app.seed.seed_data import (
    AS_OF_DATE,
    BALANCE_ON_2026_10_19,
    BALANCE_TOLERANCE,
    LAST_FIVE,
    MONTH_END_TARGETS,
    OPENING_BALANCE,
    TARGET_CASH,
    balance_on,
    check_hard_targets,
    dataset_fingerprint,
    seed_database,
)

COMMITMENT_WINDOW = (date(2026, 11, 20), date(2026, 12, 19))


def _money(value) -> Decimal:
    """Compare money at 2 decimal places."""
    return Decimal(str(value)).quantize(Decimal("0.01"))


@pytest.fixture()
def session():
    """A fresh in-memory database for each test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    with maker() as db:
        yield db
    Base.metadata.drop_all(engine)


@pytest.fixture()
def seeded(session):
    """A session already holding the seeded dataset."""
    result = seed_database(session)
    assert result["seeded"] is True
    return session


# ---------------------------------------------------------------------------
# Hard targets
# ---------------------------------------------------------------------------


def test_cash_balance_on_as_of_date(seeded):
    """Opening balance + every transaction = the headline ₹3,42,500."""
    opening = seeded.scalar(select(BusinessProfile.opening_balance))
    total = seeded.scalar(select(func.sum(Transaction.amount)))

    assert _money(opening) == _money(OPENING_BALANCE)
    assert _money(opening + total) == _money(TARGET_CASH)
    assert _money(balance_on(seeded, AS_OF_DATE)) == Decimal("342500.00")


def test_month_end_balances(seeded):
    """Each completed month closes at its pinned balance."""
    for when, expected in MONTH_END_TARGETS.items():
        assert _money(balance_on(seeded, when)) == _money(expected), f"balance on {when}"


def test_balance_one_month_ago_is_close_to_target(seeded):
    """19 Oct must be within ₹300 of ₹3,16,544 so the KPI reads +8.2%."""
    month_ago = balance_on(seeded, date(2026, 10, 19))

    assert abs(month_ago - BALANCE_ON_2026_10_19) <= BALANCE_TOLERANCE


def test_latest_five_transactions_match_exactly(seeded):
    """The five rows the frontend shows as recent activity."""
    rows = seeded.scalars(
        select(Transaction).order_by(Transaction.date.desc(), Transaction.id.desc()).limit(5)
    ).all()
    rows = list(reversed(rows))

    assert [row.id for row in rows] == [item[0] for item in LAST_FIVE]

    for row, (txn_id, when, name, category, amount, kind) in zip(rows, LAST_FIVE):
        assert row.id == txn_id
        assert row.date == when
        assert row.name == name
        assert row.category == category
        assert _money(row.amount) == _money(amount)
        assert row.type == kind


def test_transaction_ids_are_sequential_in_date_order(seeded):
    """Ids count up by date, with no gaps, and end at TXN-1048."""
    rows = seeded.scalars(select(Transaction).order_by(Transaction.date, Transaction.id)).all()

    numbers = [int(row.id.replace("TXN-", "")) for row in rows]
    assert numbers == list(range(numbers[0], numbers[0] + len(numbers)))
    assert numbers[-1] == 1048

    dates = [row.date for row in rows]
    assert dates == sorted(dates)


def test_open_invoices_and_overdue_calculation(seeded):
    """Open invoices total ₹1,09,500; overdue is computed, never stored."""
    pending = seeded.scalars(select(Invoice).where(Invoice.status == "Pending")).all()
    pending_total = _money(sum((_money(inv.amount) for inv in pending), Decimal("0.00")))

    assert {inv.id for inv in pending} == {"INV-198", "INV-204", "INV-211"}
    assert pending_total == Decimal("109500.00")

    overdue = [inv for inv in pending if inv.due_date < AS_OF_DATE]
    overdue_total = _money(sum((_money(inv.amount) for inv in overdue), Decimal("0.00")))
    assert len(overdue) == 2
    assert overdue_total == Decimal("85000.00")

    # "Overdue" must never be written into the status column.
    stored_statuses = set(seeded.scalars(select(Invoice.status)).all())
    assert stored_statuses <= {"Draft", "Pending", "Paid"}
    assert "Overdue" not in stored_statuses


def test_november_collections_total_184000(seeded):
    """Invoices paid 1-19 Nov add up to ₹1,84,000, each with a linked income."""
    paid = seeded.scalars(
        select(Invoice).where(
            Invoice.status == "Paid",
            Invoice.paid_date >= date(2026, 11, 1),
            Invoice.paid_date <= AS_OF_DATE,
        )
    ).all()

    assert _money(sum((_money(inv.amount) for inv in paid), Decimal("0.00"))) == Decimal("184000.00")

    for inv in paid:
        linked = seeded.scalar(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.invoice_id == inv.id, Transaction.type == "income")
        )
        assert linked == 1, f"{inv.id} should have one linked income transaction"


def test_commitments_in_next_30_days_total_248500(seeded):
    """The 30-day commitment window is pinned at ₹2,48,500."""
    start, end = COMMITMENT_WINDOW
    commitments = seeded.scalars(
        select(Commitment).where(Commitment.due_date >= start, Commitment.due_date <= end)
    ).all()

    total = _money(sum((_money(item.amount) for item in commitments), Decimal("0.00")))
    assert total == Decimal("248500.00")

    by_label = {item.label: item for item in commitments}
    assert by_label["Monthly rent"].amount == Decimal("22000.00")
    assert by_label["Monthly rent"].due_date == date(2026, 12, 1)
    assert by_label["Inventory restock"].amount == Decimal("48000.00")
    assert by_label["Payroll"].amount == Decimal("76000.00")


# ---------------------------------------------------------------------------
# Data hygiene
# ---------------------------------------------------------------------------


def test_signs_match_type_and_source_is_synthetic(seeded):
    """Income is positive, expenses negative, and every row is synthetic."""
    rows = seeded.scalars(select(Transaction)).all()
    assert rows, "expected seeded transactions"

    for row in rows:
        amount = _money(row.amount)
        assert row.source == "synthetic", f"{row.id} has source {row.source}"
        if row.type == "income":
            assert amount > 0, f"{row.id} is income with amount {amount}"
        else:
            assert row.type == "expense"
            assert amount < 0, f"{row.id} is an expense with amount {amount}"


def test_no_transaction_after_the_as_of_date(seeded):
    """History stops on the demo date."""
    newest = seeded.scalar(select(func.max(Transaction.date)))
    assert newest == AS_OF_DATE


def test_every_data_row_is_marked_synthetic(seeded):
    """Invoices, parties and the profile are all clearly fictional."""
    assert seeded.scalar(select(BusinessProfile.is_synthetic)) is True
    assert seeded.scalar(select(BusinessProfile.name)) == "Bloom & Bean"

    assert set(seeded.scalars(select(Invoice.source)).all()) == {"synthetic"}
    for gstin in seeded.scalars(select(Counterparty.gstin)).all():
        assert gstin is None or gstin.startswith("29SYNTH"), gstin


def test_history_is_a_realistic_size(seeded):
    """Roughly 150-250 transactions across the six-month history."""
    count = seeded.scalar(select(func.count()).select_from(Transaction))
    assert 150 <= count <= 250


# ---------------------------------------------------------------------------
# Seeding behaviour
# ---------------------------------------------------------------------------


def test_seeding_twice_without_reset_changes_nothing(session):
    """A restart must not duplicate the dataset."""
    first = seed_database(session)
    assert first["seeded"] is True

    count_after_first = session.scalar(select(func.count()).select_from(Transaction))
    second = seed_database(session)

    assert second["seeded"] is False
    assert session.scalar(select(func.count()).select_from(Transaction)) == count_after_first


def test_reset_reproduces_identical_data(session):
    """Reseeding is deterministic: same rows, byte for byte."""
    seed_database(session)
    first = dataset_fingerprint(session)

    seed_database(session, reset=True)
    second = dataset_fingerprint(session)

    assert first == second


def test_reset_clears_previous_rows(session):
    """--reset wipes first, so no stale rows survive."""
    seed_database(session)
    total_before = session.scalar(select(func.count()).select_from(Transaction))

    seed_database(session, reset=True)
    total_after = session.scalar(select(func.count()).select_from(Transaction))

    assert total_before == total_after


def test_check_hard_targets_returns_the_pinned_numbers(seeded):
    """The shared verification helper agrees with direct queries."""
    numbers = check_hard_targets(seeded)

    assert _money(numbers["cash_on_as_of"]) == Decimal("342500.00")
    assert _money(numbers["pending_invoices"]) == Decimal("109500.00")
    assert _money(numbers["overdue_total"]) == Decimal("85000.00")
    assert _money(numbers["commitments_window"]) == Decimal("248500.00")
    assert numbers["overdue_count"] == 2
    assert numbers["latest_ids"] == [item[0] for item in LAST_FIVE]
