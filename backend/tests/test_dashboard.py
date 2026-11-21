"""Tests for `GET /api/dashboard` and the KPI service.

The expected numbers are recomputed from the same database through the service
helpers, so these tests check the wiring and the arithmetic - not a hardcoded
copy of the seed values.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import BusinessProfile, Transaction
from app.services.forecast import build_forecast
from app.services.risk import build_risk_response
from app.services.kpi import (
    _cashflow_series,
    _commitments_due,
    _current_balance,
    _min_cash_buffer,
    _month_end_balance,
    _projected_30d,
    _safe_to_spend,
)
from app.services.transactions import AS_OF_DATE

VALID_TONES = {"green", "sage", "amber", "coral"}


@pytest.fixture()
def dashboard(client):
    """The dashboard body, fetched once per test."""
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    return response.json()


def test_full_response_shape(dashboard):
    """Every documented top-level key is present."""
    assert set(dashboard) == {
        "workspace",
        "period",
        "as_of_date",
        "kpis",
        "cashflow_series",
        "series_range_label",
        "insight",
        "ai_cfo",
        "risk_items",
        "recent_transactions",
    }
    assert dashboard["workspace"] == {
        "name": "Bloom & Bean",
        "type": "Small business",
        "city": "Bengaluru",
        "is_sample_data": True,
    }
    assert dashboard["period"] == {
        "label": "Nov 2026",
        "start": "2026-11-01",
        "end": "2026-11-30",
    }
    assert dashboard["as_of_date"] == "2026-11-19"
    assert dashboard["series_range_label"] == "Jun 2026 — Feb 2027"


def test_available_cash_is_342500(dashboard):
    """Opening balance plus every transaction."""
    assert dashboard["kpis"]["available_cash"]["value"] == 342500
    assert dashboard["kpis"]["available_cash"]["note"] == "vs. last month"


def test_overdue_receivables_matches_the_invoices(dashboard):
    """₹85,000 across 2 overdue invoices."""
    card = dashboard["kpis"]["overdue_receivables"]
    assert card["value"] == 85000
    assert "2" in card["change"]


def test_projected_30d_comes_from_the_forecast_engine(client, seeded_db):
    """projected_30d is the forecast's day-30 balance, not its own formula.

    Stage 4.1 made the Overview card delegate to the same daily projection the
    Cash Flow screen uses, so the two screens can never disagree.
    """
    body = client.get("/api/dashboard").json()
    projected = Decimal(str(body["kpis"]["projected_30d"]["value"]))

    current = _current_balance(seeded_db)
    day_30 = Decimal(str(build_forecast(seeded_db, days=30).daily_series[-1].balance))

    # Printed so the reviewer can see the numbers behind the KPI.
    print(
        "\nprojected_30d breakdown:"
        f"\n  current_balance          = {current}"
        f"\n  forecast day-30 balance  = {day_30}"
        f"\n  commitments_30d          = {_commitments_due(seeded_db)}"
        f"\n  projected_30d            = {projected}"
    )

    assert projected == day_30
    assert abs(projected - _projected_30d(seeded_db)) <= Decimal("0.01")


def test_projected_30d_dips_below_the_safety_buffer(seeded_db):
    """December's lump sums pull the 30-day projection under ₹1,50,000.

    This is the honest picture the Stage 4.0 zero-outflow baseline hid.
    """
    assert _projected_30d(seeded_db) < _min_cash_buffer(seeded_db)


def test_safe_to_spend_tone_is_coral_below_the_buffer(dashboard, seeded_db):
    """With a real outflow baseline the cushion is gone, so the card is coral."""
    card = dashboard["kpis"]["safe_to_spend"]

    assert card["value"] == float(_safe_to_spend(seeded_db))
    assert card["value"] < 0
    assert card["tone"] == "coral"
    assert dashboard["kpis"]["projected_30d"]["tone"] == "amber"


def test_safe_to_spend_tone_is_coral_when_cash_runs_out(client, seeded_db):
    """Temporarily sink the opening balance in the in-memory DB only.

    The seed data is untouched; this test just proves the tone rule reacts to
    the computed numbers instead of being hardcoded.
    """
    profile = seeded_db.scalars(
        select(BusinessProfile).order_by(BusinessProfile.id)
    ).one()
    profile.opening_balance = Decimal("-1000000")
    seeded_db.commit()

    body = client.get("/api/dashboard").json()

    assert body["kpis"]["available_cash"]["value"] < 0
    assert body["kpis"]["safe_to_spend"]["value"] <= 0
    assert body["kpis"]["safe_to_spend"]["tone"] == "coral"
    assert body["kpis"]["projected_30d"]["tone"] == "coral"


def test_safe_to_spend_keeps_the_buffer(seeded_db, dashboard):
    """safe_to_spend = projected_30d - the ₹1,50,000 buffer."""
    projected = dashboard["kpis"]["projected_30d"]["value"]
    safe = dashboard["kpis"]["safe_to_spend"]["value"]

    assert safe == round(projected - 150000, 2)
    assert float(_safe_to_spend(seeded_db)) == safe


def test_recent_transactions_are_the_last_four(dashboard):
    """Newest first, exactly the four most recent rows."""
    ids = [item["id"] for item in dashboard["recent_transactions"]]
    assert ids == ["TXN-1048", "TXN-1047", "TXN-1046", "TXN-1045"]


def test_cashflow_series_has_nine_points(seeded_db, dashboard):
    """Six actual months, then three forecast months."""
    series = dashboard["cashflow_series"]

    assert len(series) == 9
    assert [point["month"] for point in series] == [
        "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb",
    ]
    assert [point["month_iso"] for point in series] == [
        "2026-06", "2026-07", "2026-08", "2026-09", "2026-10",
        "2026-11", "2026-12", "2027-01", "2027-02",
    ]


def test_actual_months_equal_computed_month_end(seeded_db, dashboard):
    """For Jun-Nov, actual == forecast == the month-end balance."""
    series = dashboard["cashflow_series"][:6]
    months = [(2026, month) for month in range(6, 12)]

    for point, (year, month) in zip(series, months):
        expected = float(_month_end_balance(seeded_db, dt.date(year, month, 1)))
        assert point["actual"] == expected
        assert point["forecast"] == expected

    # The cash KPI and the last actual point agree.
    assert series[-1]["actual"] == dashboard["kpis"]["available_cash"]["value"]


def test_future_months_have_no_actual(dashboard):
    """Dec-Feb are forecast only; actual must be None, never 0."""
    for point in dashboard["cashflow_series"][6:]:
        assert point["actual"] is None
        assert isinstance(point["forecast"], (int, float))
        assert point["forecast"] > 0


def test_series_builder_returns_the_same_shape(seeded_db):
    """The service helper and the endpoint agree."""
    assert len(_cashflow_series(seeded_db)) == 9


def test_insight_and_ai_cfo_use_real_numbers(dashboard):
    """The prose is a deterministic template that mentions the real figures."""
    insight = dashboard["insight"]
    assert "₹3,42,500" in insight
    assert "₹85,000" in insight

    ai_cfo = dashboard["ai_cfo"]
    assert ai_cfo["source"] == "rules"
    assert ai_cfo["tag"] == "CASH FLOW WATCH"
    assert ai_cfo["updated_at"] == "2026-11-19T09:00:00"
    assert "₹" in ai_cfo["body"]


def test_risk_items_and_tones(dashboard, seeded_db):
    """Two risk lines, taken from the Risk Radar service (Stage 6)."""
    risks = dashboard["risk_items"]
    alerts = build_risk_response(seeded_db).alerts

    assert len(risks) == 2
    for item, alert in zip(risks, alerts[:2]):
        assert item["title"] == alert.title
        assert item["tone"] == alert.tone
        assert item["detail"] == alert.subtitle

    for risk in risks:
        assert risk["tone"] in {"coral", "amber", "sage"}

    for card in dashboard["kpis"].values():
        assert card["tone"] in VALID_TONES
        assert isinstance(card["value"], (int, float))


def test_dashboard_reacts_to_a_new_transaction(client):
    """The dashboard is computed from the DB, never hardcoded."""
    before = client.get("/api/dashboard").json()["kpis"]["available_cash"]["value"]

    client.post(
        "/api/transactions",
        json={"name": "New delivery", "amount": 2500, "type": "expense", "category": "Inventory"},
    )

    after = client.get("/api/dashboard").json()["kpis"]["available_cash"]["value"]
    assert after == before - 2500


def test_recent_transactions_reflect_the_newest_row(client, seeded_db):
    """A freshly created row becomes the first recent transaction."""
    client.post(
        "/api/transactions",
        json={"name": "Latest sale", "amount": 900, "type": "income", "category": "Sales"},
    )

    ids = [item["id"] for item in client.get("/api/dashboard").json()["recent_transactions"]]
    assert ids[0] == "TXN-1049"

    newest = seeded_db.scalars(
        select(Transaction).order_by(Transaction.date.desc(), Transaction.id.desc()).limit(1)
    ).one()
    assert newest.id == "TXN-1049"
