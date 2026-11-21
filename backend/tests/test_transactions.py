"""Tests for `GET /api/transactions` and `POST /api/transactions`."""

from sqlalchemy import select

from app.models import Transaction

# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_list_returns_first_page_of_seed_data_newest_first(client):
    """Default listing: 50 of 161 rows, newest date first."""
    response = client.get("/api/transactions")

    assert response.status_code == 200
    body = response.json()

    assert body["total"] == 161
    assert body["page"] == 1
    assert body["limit"] == 50
    assert len(body["items"]) == 50

    dates = [item["date"] for item in body["items"]]
    assert dates == sorted(dates, reverse=True)
    assert body["items"][0]["id"] == "TXN-1048"
    assert body["items"][0]["name"] == "Aarav Foods — bulk order"
    assert body["items"][0]["amount"] == 48500
    assert body["items"][0]["type"] == "income"


def test_filter_by_type(client):
    """`type=income` returns only positive rows, `expense` only negatives."""
    income = client.get("/api/transactions", params={"type": "income", "limit": 200}).json()
    expense = client.get("/api/transactions", params={"type": "expense", "limit": 200}).json()

    assert income["items"], "expected income rows"
    assert all(item["type"] == "income" and item["amount"] > 0 for item in income["items"])

    assert expense["items"], "expected expense rows"
    assert all(item["type"] == "expense" and item["amount"] < 0 for item in expense["items"])

    # Every row is either income or expense.
    assert income["total"] + expense["total"] == 161


def test_filter_by_category(client):
    """`category` is an exact match."""
    body = client.get("/api/transactions", params={"category": "Sales", "limit": 200}).json()

    assert body["items"]
    assert all(item["category"] == "Sales" for item in body["items"])


def test_search_q_matches_name_and_category(client):
    """`q` is a case-insensitive substring search."""
    body = client.get("/api/transactions", params={"q": "aarav"}).json()

    assert body["items"]
    assert all(
        "aarav" in (item["name"] + " " + item["category"]).lower()
        for item in body["items"]
    )


def test_filter_by_date_range(client):
    """`from` and `to` are inclusive."""
    body = client.get(
        "/api/transactions",
        params={"from": "2026-11-15", "to": "2026-11-19", "limit": 200},
    ).json()

    assert body["items"]
    dates = [item["date"] for item in body["items"]]
    assert min(dates) >= "2026-11-15"
    assert max(dates) <= "2026-11-19"
    # The five pinned rows for 15-19 Nov.
    assert [item["id"] for item in body["items"][:5]] == [
        "TXN-1048",
        "TXN-1047",
        "TXN-1046",
        "TXN-1045",
        "TXN-1044",
    ]


def test_filters_combine(client):
    """All filters apply together."""
    body = client.get(
        "/api/transactions",
        params={
            "q": "order",
            "type": "income",
            "category": "Sales",
            "from": "2026-11-01",
            "to": "2026-11-19",
        },
    ).json()

    assert all(item["type"] == "income" for item in body["items"])
    assert all(item["category"] == "Sales" for item in body["items"])
    assert all("order" in item["name"].lower() for item in body["items"])


def test_pagination_page_two_is_the_next_slice(client):
    """page=2 starts where page=1 stopped."""
    first = client.get("/api/transactions", params={"page": 1, "limit": 10}).json()
    second = client.get("/api/transactions", params={"page": 2, "limit": 10}).json()

    assert len(first["items"]) == 10
    assert len(second["items"]) == 10
    assert second["page"] == 2
    assert second["total"] == 161
    assert {item["id"] for item in first["items"]}.isdisjoint(
        {item["id"] for item in second["items"]}
    )
    assert second["items"][0]["id"] != first["items"][0]["id"]


# ---------------------------------------------------------------------------
# Creating
# ---------------------------------------------------------------------------


def test_create_income_gets_next_id_and_positive_amount(client, seeded_db):
    """A manual income row becomes TXN-1049 and is stored positive."""
    response = client.post(
        "/api/transactions",
        json={"name": "Walk-in coffee order", "amount": 1200, "type": "income", "category": "Sales"},
    )

    assert response.status_code == 201
    body = response.json()

    assert body["id"] == "TXN-1049"
    assert body["amount"] == 1200
    assert body["type"] == "income"
    assert body["category"] == "Sales"
    # Date defaults to the demo date.
    assert body["date"] == "2026-11-19"

    row = seeded_db.scalar(select(Transaction).where(Transaction.id == "TXN-1049"))
    assert row is not None
    assert row.source == "manual"
    assert row.amount > 0


def test_create_expense_is_stored_negative(client):
    """The client sends a positive amount; the backend applies the minus sign."""
    response = client.post(
        "/api/transactions",
        json={"name": "Milk delivery", "amount": 500, "type": "expense"},  # category omitted
    )

    assert response.status_code == 201
    body = response.json()

    assert body["amount"] == -500
    assert body["type"] == "expense"
    assert body["category"] == "General"


def test_create_rejects_invalid_input(client):
    """Bad amounts, types, dates and categories are all 422."""
    valid = {"name": "Test", "amount": 100, "type": "income"}

    cases = [
        {"amount": 0},  # must be > 0
        {"amount": -50},  # must be > 0
        {"type": "refund"},  # not income/expense
        {"date": "2027-01-01"},  # after the demo date
        {"category": "Travel"},  # not a known category
        {"date": "19/11/2026"},  # not ISO
    ]

    for change in cases:
        response = client.post("/api/transactions", json={**valid, **change})
        assert response.status_code == 422, change
        assert "detail" in response.json()


def test_create_does_not_change_the_balance_maths(client, seeded_db):
    """A new row is included in the cash total immediately."""
    before = client.get("/api/dashboard").json()["kpis"]["available_cash"]["value"]

    client.post(
        "/api/transactions",
        json={"name": "Extra sale", "amount": 1000, "type": "income", "category": "Sales"},
    )

    after = client.get("/api/dashboard").json()["kpis"]["available_cash"]["value"]
    assert after == before + 1000
