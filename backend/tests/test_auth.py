"""Authentication tests (Stage 11).

Unlike the rest of the suite these use `public_client`, which does NOT bypass
the auth dependency: the real cookie has to be issued and read back. The
financial endpoints behind it return the same shared Bloom & Bean data for
every signed-in user, so the last test also proves the gate does not change
the payload.
"""

REGISTER = {
    "name": "Asha Rao",
    "email": "asha@example.com",
    "password": "correct-horse",
}


def _register(client, **overrides):
    """Register the standard test account, with optional field overrides."""
    body = {**REGISTER, **overrides}
    return client.post("/api/auth/register", json=body)


def test_register_and_login_flow(public_client):
    """Register signs you in; logging in again on a fresh jar works too."""
    response = _register(public_client)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Asha Rao"
    assert body["email"] == "asha@example.com"
    assert set(body) == {"id", "name", "email"}  # never the password or hash

    cookie = response.headers["set-cookie"]
    assert "access_token=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie or "samesite=lax" in cookie.lower()

    # The cookie alone is enough to identify the user afterwards.
    assert public_client.get("/api/auth/me").json()["email"] == "asha@example.com"

    # A new browser (empty cookie jar) can log in with the same credentials.
    public_client.cookies.clear()
    login = public_client.post(
        "/api/auth/login",
        json={"email": "asha@example.com", "password": "correct-horse"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["email"] == "asha@example.com"
    assert "access_token=" in login.headers["set-cookie"]


def test_login_wrong_password(public_client):
    _register(public_client)
    public_client.cookies.clear()

    response = public_client.post(
        "/api/auth/login",
        json={"email": "asha@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"
    # A failed login must not hand out a session.
    assert "access_token=" not in response.headers.get("set-cookie", "")


def test_duplicate_email(public_client):
    assert _register(public_client).status_code == 200

    # Same address, different casing: emails are stored lower-case.
    duplicate = _register(public_client, email="ASHA@example.com", name="Someone Else")

    assert duplicate.status_code == 400
    assert "already exists" in duplicate.json()["detail"]


def test_me_endpoint_requires_auth(public_client):
    response = public_client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_me_endpoint_returns_user(public_client):
    _register(public_client)

    response = public_client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "name": "Asha Rao",
        "email": "asha@example.com",
    }


def test_logout_clears_cookie(public_client):
    _register(public_client)
    assert public_client.get("/api/auth/me").status_code == 200

    response = public_client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"detail": "Logged out"}
    # The browser is told to drop the cookie, and the jar no longer has it.
    assert "access_token" in response.headers["set-cookie"]
    assert public_client.cookies.get("access_token") is None
    assert public_client.get("/api/auth/me").status_code == 401


def test_financial_endpoint_requires_auth(public_client):
    """No cookie -> 401 on both a read and a write financial route."""
    for method, path, kwargs in [
        ("get", "/api/dashboard", {}),
        ("get", "/api/transactions", {}),
        ("get", "/api/cashflow/forecast", {}),
        ("get", "/api/invoices", {}),
        ("get", "/api/receivables", {}),
        ("get", "/api/risk/alerts", {}),
        ("post", "/api/simulator/run", {"json": {"purchase_amount": 50000, "revenue_uplift": 15}}),
        ("post", "/api/copilot/chat", {"json": {"message": "How is cash?"}}),
    ]:
        response = getattr(public_client, method)(path, **kwargs)
        assert response.status_code == 401, path
        assert response.json()["detail"] == "Not authenticated"

    # The health check stays public.
    assert public_client.get("/api/health").status_code == 200


def test_financial_endpoint_works_when_logged_in(public_client):
    """After registering, the same dashboard is returned as before Stage 11."""
    _register(public_client)

    response = public_client.get("/api/dashboard")

    assert response.status_code == 200, response.text
    body = response.json()
    # The shared Bloom & Bean figures are untouched by authentication.
    assert body["workspace"]["name"] == "Bloom & Bean"
    assert body["kpis"]["available_cash"]["value"] == 342500
    assert body["kpis"]["overdue_receivables"]["value"] == 85000
