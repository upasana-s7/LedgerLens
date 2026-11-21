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
    response = client.post("/api/invoices/INV-204/confirm")

    assert response.status_code == 501
    assert response.json() == {
        "detail": "Not implemented yet (planned for Stage 9)"
    }


def test_placeholder_list_covers_all_staged_routes():
    """Every staged route exists and reports the 501 error shape."""
    # /api/dashboard and /api/transactions went live in Stage 3,
    # /api/cashflow/forecast in Stage 4, /api/simulator/run in Stage 5,
    # /api/risk/alerts in Stage 6, /api/invoices + /api/receivables in Stage 7
    # and both copilot routes in Stage 8, so none of them answer 501 any more.
    # What is left is invoice upload / confirm (Stage 9).
    staged_gets = []
    staged_posts = [
        ("/api/invoices/INV-204/confirm", 9),
    ]

    for url, stage in staged_gets:  # pragma: no cover - kept for Stage 9
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

    # The upload route needs a file part to get past request validation.
    upload = client.post(
        "/api/invoices/upload",
        files={"file": ("bill.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert upload.status_code == 501
    assert upload.json()["detail"] == (
        "Not implemented yet (planned for Stage 9)"
    )


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
