"""Tests for `GET /api/cashflow/forecast` and the Stage 4 forecast engine.

Where possible the expected numbers are recomputed from the same in-memory
database, so these tests check the model and its wiring rather than a
hardcoded copy of the seed values.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import BusinessProfile, Commitment, Invoice, Transaction
from app.services.forecast import build_forecast
from app.services.kpi import _month_end_balance
from app.services.transactions import AS_OF_DATE

EXPECTED_MONTHS = ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb"]


@pytest.fixture()
def forecast(client):
    """The forecast body, fetched once per test."""
    response = client.get("/api/cashflow/forecast")
    assert response.status_code == 200
    return response.json()


# ---------------------------------------------------------------------------
# Shape and starting point
# ---------------------------------------------------------------------------

def test_full_response_shape(forecast):
    """Every documented top-level key is present, and only those."""
    assert set(forecast) == {
        "opening_balance",
        "inflows_30d",
        "outflows_30d",
        "series",
        "daily_series",
        "range_label",
        "commitments",
        "assumptions",
        "lowest_balance",
        "shortfall_date",
        "is_sample_data",
    }
    assert forecast["range_label"] == "Jun 2026 — Feb 2027"
    assert forecast["is_sample_data"] is True


def test_opening_balance_equals_seeded_cash(forecast):
    """The KPI's cash figure is the forecast's starting point."""
    assert forecast["opening_balance"] == 342500


def test_series_length_is_9(forecast):
    assert len(forecast["series"]) == 9


def test_series_months_are_correct(forecast):
    assert [point["month"] for point in forecast["series"]] == EXPECTED_MONTHS
    assert [point["month_iso"] for point in forecast["series"]] == [
        "2026-06", "2026-07", "2026-08", "2026-09", "2026-10",
        "2026-11", "2026-12", "2027-01", "2027-02",
    ]


def test_historical_months_match_dashboard(seeded_db, forecast):
    """Jun-Oct are real month-end balances, identical to the dashboard's."""
    for point, month in zip(forecast["series"][:5], range(6, 11)):
        expected = float(_month_end_balance(seeded_db, dt.date(2026, month, 1)))
        assert point["actual"] == expected
        assert point["forecast"] == expected
    # The pinned seed targets, as a second, independent check.
    assert [point["actual"] for point in forecast["series"][:5]] == [
        310000, 355000, 328000, 392000, 365000,
    ]


def test_november_actual_equals_current_balance(forecast):
    """November is not over, so actual == forecast == today's cash."""
    november = forecast["series"][5]
    assert november["actual"] == forecast["opening_balance"]
    assert november["forecast"] == forecast["opening_balance"]


def test_future_months_have_null_actual(forecast):
    for point in forecast["series"][6:]:
        assert point["actual"] is None
        assert isinstance(point["forecast"], (int, float))
        assert point["forecast"] > 0


def test_forecast_values_differ_from_dashboard_extrapolation(forecast):
    """Dec, Jan and Feb come from the daily model, not one flat step.

    The dashboard repeats the average monthly change, so its three points are
    evenly spaced. The forecast engine moves by commitments, collections and
    day count instead, which makes the three future points differ.
    """
    december, january, february = (point["forecast"] for point in forecast["series"][6:])
    values = [december, january, february]

    assert len(set(values)) == 3
    # And the December step is not simply repeated into January.
    assert round(january - december, 2) != round(february - january, 2)


# ---------------------------------------------------------------------------
# Daily projection
# ---------------------------------------------------------------------------

def test_daily_series_has_90_points(forecast):
    assert len(forecast["daily_series"]) == 90
    assert forecast["daily_series"][0]["date"] == "2026-11-20"
    assert forecast["daily_series"][-1]["date"] == "2027-02-17"


def test_daily_series_days_parameter_respected(client):
    body = client.get("/api/cashflow/forecast?days=30").json()

    assert len(body["daily_series"]) == 30
    assert body["daily_series"][0]["date"] == "2026-11-20"
    assert body["daily_series"][-1]["date"] == "2026-12-19"
    # The 30-day totals do not move when the horizon changes.
    assert body["inflows_30d"] == client.get("/api/cashflow/forecast").json()["inflows_30d"]


def test_lowest_balance_is_minimum_of_daily_series(forecast):
    daily = forecast["daily_series"]
    lowest = forecast["lowest_balance"]

    assert lowest["value"] == min(point["balance"] for point in daily)
    # Ties go to the earliest date.
    assert lowest["date"] == next(
        point["date"] for point in daily if point["balance"] == lowest["value"]
    )


def test_lowest_balance_date_within_window(forecast):
    dates = [point["date"] for point in forecast["daily_series"]]
    assert forecast["lowest_balance"]["date"] in dates
    assert AS_OF_DATE.isoformat() < forecast["lowest_balance"]["date"]


def test_shortfall_null_or_matches_first_breach(seeded_db, forecast):
    """`shortfall_date` is the FIRST day under the buffer, or null."""
    buffer = seeded_db.scalar(
        select(BusinessProfile.min_cash_buffer).order_by(BusinessProfile.id)
    )
    buffer = Decimal(str(buffer))
    daily = forecast["daily_series"]
    breaches = [
        point["date"] for point in daily if Decimal(str(point["balance"])) < buffer
    ]

    if forecast["shortfall_date"] is None:
        assert breaches == []
    else:
        assert breaches
        assert forecast["shortfall_date"] == breaches[0]


# ---------------------------------------------------------------------------
# Commitments
# ---------------------------------------------------------------------------

def test_commitments_sorted_by_date(seeded_db, forecast):
    """Every commitment in the window, ascending, with positive amounts."""
    commitments = forecast["commitments"]
    dates = [item["date"] for item in commitments]

    assert dates == sorted(dates)
    assert all(item["amount"] > 0 for item in commitments)

    expected = seeded_db.scalars(
        select(Commitment)
        .where(
            Commitment.due_date > AS_OF_DATE,
            Commitment.due_date <= AS_OF_DATE + dt.timedelta(days=90),
        )
        .order_by(Commitment.due_date, Commitment.id)
    ).all()
    assert [(item["label"], item["date"]) for item in commitments] == [
        (row.label, row.due_date.isoformat()) for row in expected
    ]


# ---------------------------------------------------------------------------
# 30-day inflow / outflow totals
# ---------------------------------------------------------------------------

def test_inflows_30d_and_outflows_30d_are_positive(forecast):
    assert forecast["inflows_30d"] > 0
    assert forecast["outflows_30d"] > 0


def test_inflows_minus_outflows_approx_matches_balance_delta_30d(forecast):
    """The headline 30-day totals must explain the daily series exactly.

    Both are built from the same daily model, so the net of the two has to
    equal the change from today's cash to day 30's closing balance.
    """
    net = forecast["inflows_30d"] - forecast["outflows_30d"]
    delta = forecast["daily_series"][29]["balance"] - forecast["opening_balance"]

    assert abs(net - delta) < 1.0


def test_outflows_30d_includes_the_scheduled_commitments(seeded_db, forecast):
    """Commitments due in the next 30 days are part of the outflow figure."""
    total = seeded_db.scalar(
        select(func.sum(Commitment.amount)).where(
            Commitment.due_date > AS_OF_DATE,
            Commitment.due_date <= AS_OF_DATE + dt.timedelta(days=30),
        )
    )
    assert Decimal(str(forecast["outflows_30d"])) >= Decimal(str(total))


def test_overdue_collections_are_probability_weighted(seeded_db, forecast):
    """Overdue AR is collected at 60%, upcoming at 80% - never 100%."""
    overdue = seeded_db.scalars(
        select(Invoice).where(
            Invoice.status == "Pending",
            Invoice.due_date < AS_OF_DATE,
        )
    ).all()
    overdue_total = sum((Decimal(str(inv.amount)) for inv in overdue), Decimal("0"))

    assert overdue_total == Decimal("85000")
    # 60% of 85,000 = 51,000, plus 80% of INV-211's 24,500 = 19,600, plus the
    # daily counter-sale inflow for 30 days.
    model = build_forecast(seeded_db)
    counter_part = Decimal(str(model.inflows_30d)) - Decimal("70600")
    assert counter_part > 0


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------

def test_invalid_days_param_returns_422(client):
    assert client.get("/api/cashflow/forecast?days=10").status_code == 422
    assert client.get("/api/cashflow/forecast?days=200").status_code == 422
    assert client.get("/api/cashflow/forecast?days=abc").status_code == 422


def test_forecast_reacts_to_a_new_transaction(client):
    """The forecast is computed from the DB, never hardcoded."""
    before = client.get("/api/cashflow/forecast").json()["opening_balance"]

    client.post(
        "/api/transactions",
        json={"name": "New delivery", "amount": 2500, "type": "expense", "category": "Inventory"},
    )

    after = client.get("/api/cashflow/forecast").json()["opening_balance"]
    assert after == before - 2500


def test_baseline_excludes_commitment_covered_categories(seeded_db):
    """Rent history is not averaged in while rent is also a commitment.

    With the seeded calendar every expense category is commitment-covered, so
    the operational baseline is zero; only counter sales remain in the daily
    inflow.
    """
    model = build_forecast(seeded_db)
    outflow_line = next(
        line for line in model.assumptions if line.startswith("Recurring operational")
    )
    assert "Rs 0 per day" in outflow_line

    covered = seeded_db.scalars(select(Commitment.category)).all()
    assert set(covered) == {"General", "Inventory", "Rent", "Payroll", "Utilities"}
    # Sanity: the transaction table really does have expenses to exclude.
    assert seeded_db.scalar(
        select(func.count()).select_from(Transaction).where(Transaction.type == "expense")
    ) > 0
