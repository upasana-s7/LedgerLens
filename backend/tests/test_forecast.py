"""Tests for `GET /api/cashflow/forecast` and the Stage 4 forecast engine.

Where possible the expected numbers are recomputed from the same in-memory
database, so these tests check the model and its wiring rather than a
hardcoded copy of the seed values.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models import BusinessProfile, Commitment, Transaction
from app.services.forecast import _daily_baselines, build_forecast
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


def test_future_months_reflect_commitments(forecast):
    """Dec dips for the December payments, then the balance recovers.

    A flat straight-line extrapolation would step by the same amount every
    month; the daily model instead drops hard in December and claws back
    afterwards once the lump sums are paid.
    """
    december, january, february = (point["forecast"] for point in forecast["series"][6:])

    assert december < forecast["opening_balance"]
    assert december < january < february


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


def test_each_day_moves_by_the_baseline(seeded_db, forecast):
    """Days without a commitment move by exactly the net baseline."""
    _, _, net = _daily_baselines(seeded_db)
    daily = forecast["daily_series"]

    # 2026-11-20 and 11-21 have no commitments, so the step is just the
    # baseline (within a paisa of rounding).
    step = Decimal(str(daily[1]["balance"])) - Decimal(str(daily[0]["balance"]))

    assert abs(step - net) < Decimal("0.01")


def test_commitment_days_are_lump_sums(seeded_db, forecast):
    """A commitment day drops by the baseline minus that day's commitments."""
    daily = {point["date"]: Decimal(str(point["balance"])) for point in forecast["daily_series"]}

    # 2026-12-07 carries the ₹76,000 payroll commitment.
    before = daily["2026-12-06"]
    after = daily["2026-12-07"]
    _, _, net = _daily_baselines(seeded_db)

    assert before - after > Decimal("70000")
    assert abs((before + net - Decimal("76000")) - after) < Decimal("0.02")


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


# ---------------------------------------------------------------------------
# The Stage 4.1 fix: a real outflow baseline, a real shortfall
# ---------------------------------------------------------------------------

def test_outflow_baseline_is_nonzero(seeded_db):
    """The bug we fixed: outflow must never collapse to zero."""
    inbox, outflow, net = _daily_baselines(seeded_db)

    assert inbox > 0
    assert outflow > 0
    # Expenses outweigh income over the seeded 90 days, so net is negative.
    assert net == inbox - outflow


def test_assumptions_no_zero_outflow_claim(forecast):
    """The "Rs 0 per day" assumption line must be gone."""
    for line in forecast["assumptions"]:
        assert "Rs 0 per day" not in line


def test_assumptions_are_the_five_documented_lines(forecast):
    """No AR-probability wording survived the rewrite."""
    assumptions = forecast["assumptions"]

    assert len(assumptions) == 5
    assert assumptions[0].startswith("Baseline daily net flow: Rs ")
    assert assumptions[1].startswith("Scheduled commitments are applied")
    assert assumptions[2] == "Safety buffer: Rs 150,000"
    assert assumptions[3] == "Projection horizon: 90 days"
    assert assumptions[4].startswith("Model intentionally overstates")
    for line in assumptions:
        assert "probability" not in line
        assert "collected" not in line


def test_lowest_balance_below_safety_buffer(forecast):
    """December's lump sums really do take cash under ₹1,50,000."""
    assert forecast["lowest_balance"]["value"] < 150000


def test_shortfall_date_is_not_none(forecast):
    shortfall = forecast["shortfall_date"]

    assert shortfall is not None
    when = dt.date.fromisoformat(shortfall)
    assert AS_OF_DATE < when <= AS_OF_DATE + dt.timedelta(days=90)


def test_shortfall_date_is_first_breach(forecast):
    """`shortfall_date` is the FIRST day under the buffer."""
    breaches = [
        point["date"]
        for point in forecast["daily_series"]
        if Decimal(str(point["balance"])) < Decimal("150000")
    ]

    assert breaches
    assert forecast["shortfall_date"] == breaches[0]


def test_day_90_balance_is_realistic(forecast):
    """The projection must not run away: day 90 stays near today's cash."""
    day_90 = Decimal(str(forecast["daily_series"][-1]["balance"]))
    current = Decimal(str(forecast["opening_balance"]))

    assert current * Decimal("0.3") <= day_90 <= current * Decimal("2.0")


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


def test_outflows_30d_include_the_commitments(seeded_db, forecast):
    """Thirty days of routine outflow plus the scheduled payments."""
    total = seeded_db.scalar(
        select(func.sum(Commitment.amount)).where(
            Commitment.due_date > AS_OF_DATE,
            Commitment.due_date <= AS_OF_DATE + dt.timedelta(days=30),
        )
    )
    assert Decimal(str(forecast["outflows_30d"])) > Decimal(str(total))


def test_inflows_minus_outflows_approx_matches_balance_delta_30d(forecast):
    """The headline 30-day totals must explain the daily series exactly.

    Both are built from the same daily model, so the net of the two has to
    equal the change from today's cash to day 30's closing balance.
    """
    net = forecast["inflows_30d"] - forecast["outflows_30d"]
    delta = forecast["daily_series"][29]["balance"] - forecast["opening_balance"]

    assert abs(net - delta) < 1.0


# ---------------------------------------------------------------------------
# Parameter validation and live behaviour
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


def test_baseline_uses_every_category(seeded_db):
    """No category is filtered out of the 90-day baseline any more.

    Stage 4.0 excluded commitment-covered categories, which zeroed the outflow
    with the seeded calendar. The net baseline must equal the plain signed sum
    of every transaction in the window divided by 90.
    """
    start = AS_OF_DATE - dt.timedelta(days=89)
    total = seeded_db.scalar(
        select(func.sum(Transaction.amount)).where(
            Transaction.date >= start,
            Transaction.date <= AS_OF_DATE,
        )
    )
    _, _, net = _daily_baselines(seeded_db)

    expected = Decimal(str(total)) / 90
    # The baseline rounds inflow and outflow to 4 places separately, so allow
    # a paisa of accumulated rounding.
    assert abs(net - expected) <= Decimal("0.01")
    assert seeded_db.scalar(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.type == "expense")
    ) > 0


def test_no_invoice_collections_are_added(seeded_db, forecast):
    """The old AR-events code path is gone.

    With no AR events, the 30-day projection delta is exactly 30 days of net
    flow minus the commitments due in those 30 days - nothing else can move
    the balance.
    """
    _, _, net = _daily_baselines(seeded_db)
    committed = seeded_db.scalar(
        select(func.sum(Commitment.amount)).where(
            Commitment.due_date > AS_OF_DATE,
            Commitment.due_date <= AS_OF_DATE + dt.timedelta(days=30),
        )
    )
    expected = Decimal("342500") + net * 30 - Decimal(str(committed))
    day_30 = Decimal(str(forecast["daily_series"][29]["balance"]))

    assert abs(day_30 - expected) <= Decimal("0.5")


def test_business_profile_values_drive_the_buffer(seeded_db):
    """The buffer in the assumptions is read from the profile, not hardcoded."""
    buffer = seeded_db.scalar(
        select(BusinessProfile.min_cash_buffer).order_by(BusinessProfile.id)
    )
    assert f"Safety buffer: Rs {Decimal(str(buffer)):,.0f}" in build_forecast(
        seeded_db
    ).assumptions
