"""Tests for `POST /api/simulator/run` (Stage 5).

Expected numbers are recomputed from the same database through the forecast
service, so these tests check wiring and arithmetic rather than a hardcoded
copy of the seed values.
"""

import pytest

from app.schemas.simulator import SimulatorRequest
from app.services.forecast import build_forecast, get_daily_baselines
from app.services.simulator import build_simulation

RESPONSE_FIELDS = {
    "base_balance",
    "scenario_cost",
    "additional_revenue",
    "projected_balance",
    "verdict",
    "verdict_label",
    "threshold",
    "explanation",
    "explanation_source",
}


def _run(client, purchase: float, uplift: float) -> dict:
    """POST a scenario and assert it succeeded."""
    response = client.post(
        "/api/simulator/run",
        json={"purchase_amount": purchase, "revenue_uplift_pct": uplift},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_purchase_in_range_valid_response(client):
    """50,000 / 15% returns every documented field with the right types."""
    body = _run(client, 50000, 15)

    assert set(body) == RESPONSE_FIELDS
    for field in (
        "base_balance",
        "scenario_cost",
        "additional_revenue",
        "projected_balance",
        "threshold",
    ):
        assert isinstance(body[field], (int, float))
    assert isinstance(body["explanation"], str) and body["explanation"]
    assert body["verdict"] in {"comfortable", "caution"}


def test_scenario_cost_equals_purchase_amount(client):
    """The cost is the purchase, rounded to paisa, with no hidden fee."""
    body = _run(client, 50000, 15)
    assert body["scenario_cost"] == 50000.0


def test_additional_revenue_formula(client, seeded_db):
    """Uplift is worth net_baseline x pct x 30 days, within one rupee."""
    body = _run(client, 50000, 15)

    _inflow, _outflow, net_baseline = get_daily_baselines(seeded_db)
    expected = float(net_baseline) * 0.15 * 30

    assert abs(body["additional_revenue"] - expected) <= 1


def test_projected_balance_formula(client):
    """projected = base - purchase + additional_revenue, within one rupee."""
    body = _run(client, 50000, 15)
    expected = (
        body["base_balance"] - body["scenario_cost"] + body["additional_revenue"]
    )
    assert abs(body["projected_balance"] - expected) <= 1


def test_base_balance_matches_forecast_day_30(client, seeded_db):
    """The simulator starts from the forecast's own day-30 balance."""
    body = _run(client, 50000, 15)

    day_30 = build_forecast(seeded_db, days=30).daily_series[-1].balance
    assert body["base_balance"] == pytest.approx(day_30, abs=0.01)
    # And it is the same figure the dashboard card shows.
    dashboard = client.get("/api/dashboard").json()
    assert body["base_balance"] == dashboard["kpis"]["projected_30d"]["value"]


def test_verdict_is_caution_for_all_valid_inputs_with_seed(client):
    """With the seeded cash-tight data every scenario trips caution.

    The comfort threshold is 1.5x the Rs 1,50,000 buffer = Rs 2,25,000, while
    the day-30 base is Rs 1,30,513 and the best possible uplift is
    1,217 x 0.4 x 30 = Rs 14,605. Even the cheapest purchase (Rs 10,000) tops
    out around Rs 1,35,119, so no valid slider combination can clear the
    threshold. That is the honest answer for this dataset, not a bug, and the
    rule is left strict rather than loosened to produce a "comfortable" case.
    """
    for purchase, uplift in [
        (50000, 15),
        (10000, 0),
        (10000, 40),
        (200000, 0),
        (200000, 40),
    ]:
        body = _run(client, purchase, uplift)
        assert body["verdict"] == "caution", (purchase, uplift)
        assert body["verdict_label"] == "Proceed with caution"


def test_verdict_flips_to_comfortable_when_buffer_cannot_be_breached(
    client, seeded_db
):
    """The threshold rule is real: drop the buffer and the verdict flips.

    This keeps the "always caution" test above from being the only evidence
    that the comparison exists, without weakening the seeded-data expectation.
    """
    from sqlalchemy import select

    from app.models import BusinessProfile

    profile = seeded_db.scalars(
        select(BusinessProfile).order_by(BusinessProfile.id)
    ).one()
    profile.min_cash_buffer = 10000
    seeded_db.commit()

    body = _run(client, 50000, 40)

    assert body["threshold"] == 15000.0
    assert body["verdict"] == "comfortable"
    assert body["verdict_label"] == "Comfortably affordable"


def test_explanation_source_is_rules(client):
    """Stage 5 is deterministic; Gemini arrives in Stage 8."""
    assert _run(client, 50000, 15)["explanation_source"] == "rules"


def test_explanation_mentions_real_numbers(client):
    """The prose is a template over the computed figures."""
    body = _run(client, 50000, 15)

    assert "Rs 50,000" in body["explanation"]
    assert "Rs 85,990" in body["explanation"]
    assert "Rs 225,000" in body["explanation"]
    assert "15%" in body["explanation"]


def test_threshold_is_one_and_a_half_times_the_buffer(client):
    """1.5 x Rs 1,50,000 = Rs 2,25,000."""
    assert _run(client, 50000, 15)["threshold"] == 225000.0


def test_purchase_below_min_returns_422(client):
    response = client.post(
        "/api/simulator/run",
        json={"purchase_amount": 5000, "revenue_uplift_pct": 15},
    )
    assert response.status_code == 422


def test_purchase_above_max_returns_422(client):
    response = client.post(
        "/api/simulator/run",
        json={"purchase_amount": 250000, "revenue_uplift_pct": 15},
    )
    assert response.status_code == 422


def test_uplift_out_of_range_returns_422(client):
    for uplift in (-5, 50):
        response = client.post(
            "/api/simulator/run",
            json={"purchase_amount": 50000, "revenue_uplift_pct": uplift},
        )
        assert response.status_code == 422, uplift


def test_missing_field_returns_422(client):
    response = client.post(
        "/api/simulator/run", json={"purchase_amount": 50000}
    )
    assert response.status_code == 422


def test_base_balance_consistent_across_calls(client, seeded_db):
    """Different scenarios, same DB: identical base. No randomness."""
    first = _run(client, 10000, 0)["base_balance"]
    second = _run(client, 200000, 40)["base_balance"]
    service = build_simulation(
        seeded_db,
        SimulatorRequest(purchase_amount=50000, revenue_uplift_pct=15),
    )

    assert first == second
    assert service.base_balance == pytest.approx(first, abs=0.01)
