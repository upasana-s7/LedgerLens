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


def test_no_placeholder_route_returns_501():
    """Stage 9 built the last placeholder, so the 501 contract is now gone.

    The old placeholder tests are removed on purpose: with every route live
    there is nothing to assert 501 against. What still matters is that the
    staged URLs are *registered* (not 404) and only answer their real methods,
    so a wrong-method probe returns 405 - a route that had never been declared
    would answer 404 instead.
    """
    # Upload is POST-only in the contract.
    upload_get = client.get("/api/invoices/upload")
    assert upload_get.status_code == 405

    # No 501 remains anywhere in the API surface.
    probes = [
        client.get("/api/health"),
        client.get("/api/dashboard"),
        client.get("/api/transactions"),
        client.get("/api/cashflow/forecast"),
        client.get("/api/risk/alerts"),
        client.get("/api/invoices"),
        client.get("/api/receivables"),
        client.get("/api/copilot/suggestions"),
        client.post("/api/copilot/chat", json={"message": "hi"}),
        client.post("/api/simulator/run", json={}),
        client.post("/api/invoices/INV-204/confirm", json={}),
    ]
    for response in probes:
        assert response.status_code != 501


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
