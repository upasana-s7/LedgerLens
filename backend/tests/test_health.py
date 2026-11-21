"""Stage 1 smoke tests.

They check the plumbing only: the health endpoint, the 501 placeholders and
that the frontend dev origin is allowed through CORS.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FRONTEND_ORIGIN = "http://localhost:5173"


def test_health_returns_exact_payload():
    """GET /api/health -> 200 with the agreed JSON."""
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "LedgerLens API",
        "version": "0.1.0",
    }


def test_placeholder_route_returns_501():
    """Routes planned for later stages answer with a clear 501 + detail."""
    response = client.get("/api/cashflow/forecast")

    assert response.status_code == 501
    assert response.json() == {
        "detail": "Not implemented yet (planned for Stage 4)"
    }


def test_placeholder_list_covers_all_staged_routes():
    """Every staged route exists and reports the 501 error shape."""
    # /api/dashboard and /api/transactions went live in Stage 3, so they are
    # no longer expected to answer 501.
    staged_gets = [
        ("/api/cashflow/forecast", 4),
        ("/api/risk/alerts", 6),
        ("/api/receivables", 7),
        ("/api/invoices", 7),
        ("/api/copilot/suggestions", 8),
    ]
    staged_posts = [
        ("/api/simulator/run", 5),
        ("/api/receivables/INV-204/mark-paid", 7),
        ("/api/invoices/INV-204/mark-paid", 7),
    ]

    for url, stage in staged_gets:
        response = client.get(url)
        assert response.status_code == 501, url
        assert response.json()["detail"] == (
            f"Not implemented yet (planned for Stage {stage})"
        ), url

    for url, stage in staged_posts:
        response = client.post(url)
        assert response.status_code == 501, url
        assert response.json()["detail"] == (
            f"Not implemented yet (planned for Stage {stage})"
        ), url


def test_cors_preflight_from_vite_dev_origin_is_allowed():
    """The browser preflight from the React dev server must succeed."""
    response = client.options(
        "/api/health",
        headers={
            "Origin": FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == FRONTEND_ORIGIN
