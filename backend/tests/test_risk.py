"""Tests for the Stage 6 Risk Radar (`GET /api/risk/alerts`).

The rules read the seeded in-memory database, so these tests assert that each
planted anomaly is actually discovered - not that a hardcoded list is returned.
"""

import datetime as dt
import re
from collections import defaultdict
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import BusinessProfile, Transaction
from app.services.risk import build_risk_response, detect_alerts

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
EXPECTED_TONE = {"high": "coral", "medium": "amber", "low": "sage"}


@pytest.fixture()
def risk(client):
    """The risk payload, fetched once per test."""
    response = client.get("/api/risk/alerts")
    assert response.status_code == 200
    return response.json()


def _alert_with(risk, fragment):
    """The first alert whose title contains `fragment` (case-insensitive)."""
    for alert in risk["alerts"]:
        if fragment.lower() in alert["title"].lower():
            return alert
    return None


def _category_mom(db):
    """Recompute rule 5's month-over-month percentage for every category.

    Only used for the diagnostic print and the "did it really not fire?" check.
    """
    as_of = db.scalar(select(BusinessProfile.as_of_date))
    recent_start = as_of - dt.timedelta(days=29)
    lookback_start = as_of - dt.timedelta(days=89)

    recent = defaultdict(lambda: Decimal("0.00"))
    prior = defaultdict(lambda: Decimal("0.00"))

    rows = db.scalars(
        select(Transaction).where(
            Transaction.amount < 0,
            Transaction.date >= lookback_start,
            Transaction.date <= as_of,
        )
    ).all()

    for row in rows:
        target = recent if row.date >= recent_start else prior
        target[row.category] += abs(Decimal(str(row.amount)))

    result = {}
    for category, spend in recent.items():
        avg_recent = spend / Decimal(30)
        avg_prior = prior[category] / Decimal(60)
        if avg_prior > 0:
            result[category] = float((avg_recent / avg_prior - 1) * 100)
    return result


# ---------------------------------------------------------------------------
# Shape and ordering
# ---------------------------------------------------------------------------

def test_response_has_summary_alerts_risk_score(risk):
    """Exactly the documented top-level keys."""
    assert set(risk) == {"summary", "alerts", "risk_score"}
    assert set(risk["summary"]) == {"attention_count", "note", "tag"}
    assert isinstance(risk["risk_score"], int)
    assert risk["alerts"], "the seeded data should trigger at least one rule"


def test_alerts_sorted_by_severity(risk):
    """high before medium before low."""
    ranks = [SEVERITY_RANK[alert["severity"]] for alert in risk["alerts"]]
    assert ranks == sorted(ranks)


def test_alert_ids_sequential(risk):
    """RISK-1 .. RISK-N, in the order the alerts are returned."""
    assert [alert["id"] for alert in risk["alerts"]] == [
        f"RISK-{index}" for index in range(1, len(risk["alerts"]) + 1)
    ]


def test_tone_matches_severity(risk):
    """high -> coral, medium -> amber, low -> sage."""
    for alert in risk["alerts"]:
        assert alert["tone"] == EXPECTED_TONE[alert["severity"]]


def test_risk_score_bounded(risk):
    """The weighted count never leaves 0-100."""
    assert 0 <= risk["risk_score"] <= 100


def test_attention_count_matches_high_and_medium(risk):
    """attention_count is the number of alerts that need action."""
    expected = sum(
        1 for alert in risk["alerts"] if alert["severity"] in {"high", "medium"}
    )
    assert risk["summary"]["attention_count"] == expected


def test_tag_uses_attention_count(risk):
    """REVIEW RECOMMENDED (>=2), MONITOR (1), STABLE (0)."""
    count = risk["summary"]["attention_count"]
    expected = (
        "REVIEW RECOMMENDED" if count >= 2 else "MONITOR" if count == 1 else "STABLE"
    )
    assert risk["summary"]["tag"] == expected


def test_max_8_alerts(risk):
    """The list is capped so the screen never becomes a wall of cards."""
    assert len(risk["alerts"]) <= 8


# ---------------------------------------------------------------------------
# The six rules
# ---------------------------------------------------------------------------

def test_overdue_receivables_alert_present(risk):
    """INV-198 (Rs 33,000) and INV-204 (Rs 52,000) are overdue: Rs 85,000."""
    alert = _alert_with(risk, "Overdue customer invoices")
    assert alert is not None
    assert "85,000" in alert["metric"]
    assert alert["severity"] == "high"  # 85,000 > 30% of the 150,000 buffer
    ids = {item["id"] for item in alert["evidence"]}
    assert {"INV-198", "INV-204"} <= ids
    assert all(item["kind"] == "invoice" for item in alert["evidence"])


def test_forecast_shortfall_alert_present(risk):
    """The 30-day forecast dips under the Rs 1,50,000 buffer."""
    alert = _alert_with(risk, "buffer")
    assert alert is not None
    assert alert["severity"] == "high"
    assert "150,000" in alert["subtitle"]
    assert alert["evidence"], "the breach should point at the commitments behind it"
    assert all(item["kind"] == "commitment" for item in alert["evidence"])


def test_duplicate_payment_alert_present(risk, seeded_db):
    """Two Rs 14,800 FreshKart payments one day apart (12 and 13 September)."""
    alert = _alert_with(risk, "Duplicate")
    assert alert is not None
    assert "14,800" in alert["metric"]

    ids = [item["id"] for item in alert["evidence"] if item["kind"] == "transaction"]
    assert len(ids) >= 2

    rows = seeded_db.scalars(select(Transaction).where(Transaction.id.in_(ids))).all()
    by_counterparty = defaultdict(list)
    for row in rows:
        by_counterparty[row.counterparty_id].append(row)

    assert any(
        len(group) >= 2 for group in by_counterparty.values()
    ), "the duplicate pair should share one vendor"


def test_unusual_expense_alert_present(risk, seeded_db):
    """The Rs 78,000 cold-room compressor in August is the planted outlier."""
    alert = _alert_with(risk, "Unusually large")
    assert alert is not None

    ids = [item["id"] for item in alert["evidence"] if item["kind"] == "transaction"]
    rows = seeded_db.scalars(select(Transaction).where(Transaction.id.in_(ids))).all()
    amounts = {abs(Decimal(str(row.amount))) for row in rows}

    assert Decimal("78000.00") in amounts


def test_commitment_cluster_alert_present(risk):
    """Rent, payroll, EMI and restock all land 1-7 December."""
    alert = _alert_with(risk, "cluster")
    assert alert is not None
    assert alert["severity"] == "medium"
    assert alert["evidence"]
    assert all(item["kind"] == "commitment" for item in alert["evidence"])


def test_category_trend_alert_or_skip(risk, seeded_db):
    """Low-severity trend alert, or a documented reason it did not fire."""
    mom = _category_mom(seeded_db)
    print("\nCategory month-over-month change (last 30d vs prior 60d):")
    for category, pct in sorted(mom.items(), key=lambda item: -item[1]):
        print(f"  {category:<12} {pct:+7.1f}%")

    trend_alerts = [
        alert for alert in risk["alerts"] if alert["title"].endswith("spend rising")
    ]

    if trend_alerts:
        assert re.fullmatch(r"\+\d+%", trend_alerts[0]["metric"])
        assert trend_alerts[0]["severity"] == "low"
    else:
        # No category cleared the 20% bar, so the rule correctly stayed quiet.
        assert max(mom.values(), default=0.0) <= 20.0


# ---------------------------------------------------------------------------
# Dashboard integration
# ---------------------------------------------------------------------------

def test_dashboard_risk_items_come_from_risk_service(client, risk):
    """The Overview's two risk lines are the Risk Radar's top two alerts."""
    items = client.get("/api/dashboard").json()["risk_items"]
    alerts = risk["alerts"]

    assert len(items) == 2
    for index, item in enumerate(items):
        if index < len(alerts):
            assert item["title"] == alerts[index]["title"]
            assert item["detail"] == alerts[index]["subtitle"]
            assert item["tone"] == alerts[index]["tone"]
        else:
            assert item["tone"] == "sage"
            assert item["title"] == "All clear"


def test_service_helpers_agree_with_the_endpoint(risk, seeded_db):
    """`detect_alerts` returns the same alerts the endpoint serialised."""
    alerts = detect_alerts(seeded_db)
    assert [alert.id for alert in alerts] == [item["id"] for item in risk["alerts"]]
    assert build_risk_response(seeded_db).summary.tag == risk["summary"]["tag"]
