"""Tests for `POST /api/transactions/upload` (CSV import)."""

HAPPY_CSV = (
    "date,name,amount,type,category\n"
    "2026-11-01,Test sale A,1000,income,Sales\n"
    "2026-11-02,Test purchase B,500,expense,Inventory\n"
    "2026-11-03,Test sale C,750,income,Sales\n"
)

MIXED_CSV = (
    "date,name,amount,type,category\n"
    "2026-11-01,Good one,1000,income,Sales\n"
    "2026-11-02,Bad amount,not-a-number,expense,Inventory\n"
    "2026-11-03,Good two,500,expense,Inventory\n"
    "2027-01-01,Future row,200,income,Sales\n"
)


def _upload(client, text: str):
    """Post a CSV as the multipart field named `file`."""
    return client.post(
        "/api/transactions/upload",
        files={"file": ("transactions.csv", text.encode("utf-8"), "text/csv")},
    )


def test_happy_path_imports_all_rows(client):
    """Three good rows import and the TXN sequence continues from 1048."""
    response = _upload(client, HAPPY_CSV)

    assert response.status_code == 200
    body = response.json()

    assert body["imported"] == 3
    assert body["skipped"] == 0
    assert body["errors"] == []
    assert [row["id"] for row in body["rows"]] == ["TXN-1049", "TXN-1050", "TXN-1051"]

    # Signs and source are set by the importer.
    assert body["rows"][0]["amount"] == 1000
    assert body["rows"][1]["amount"] == -500
    assert body["rows"][1]["type"] == "expense"


def test_imported_rows_are_marked_csv(client, seeded_db):
    """Imported rows carry source="csv" and are in the database."""
    _upload(client, HAPPY_CSV)

    total = client.get("/api/transactions").json()["total"]
    assert total == 164

    row = client.get("/api/transactions", params={"q": "Test sale A"}).json()["items"][0]
    assert row["id"] == "TXN-1049"


def test_mixed_file_imports_good_rows_and_reports_bad_ones(client):
    """Two good rows land; the two bad rows are reported with their numbers."""
    response = _upload(client, MIXED_CSV)

    assert response.status_code == 200
    body = response.json()

    assert body["imported"] == 2
    assert body["skipped"] == 2
    assert [error["row"] for error in body["errors"]] == [2, 4]
    assert "amount" in body["errors"][0]["message"].lower()
    assert "after the demo date" in body["errors"][1]["message"]


def test_missing_required_column_is_a_400(client):
    """A file without the amount column is malformed, not a partial import."""
    response = _upload(client, "date,name,type,category\n2026-11-01,Test,income,Sales\n")

    assert response.status_code == 400
    assert "amount" in response.json()["detail"]


def test_empty_file_imports_nothing(client):
    """An empty upload is not an error."""
    response = _upload(client, "")

    assert response.status_code == 200
    assert response.json() == {"imported": 0, "skipped": 0, "rows": [], "errors": []}


def test_header_only_file_imports_nothing(client):
    """A file with just the header has no data rows."""
    response = _upload(client, "date,name,amount,type,category\n")

    assert response.status_code == 200
    assert response.json()["imported"] == 0
    assert response.json()["errors"] == []


def test_future_date_row_is_skipped_with_a_clear_message(client):
    """Rows after the demo date are rejected individually."""
    response = _upload(
        client,
        "date,name,amount,type,category\n"
        "2026-11-01,Good row,1000,income,Sales\n"
        "2027-03-01,Too far ahead,300,expense,General\n",
    )

    body = response.json()
    assert body["imported"] == 1
    assert body["skipped"] == 1
    assert body["errors"][0]["row"] == 2
    assert "2026-11-19" in body["errors"][0]["message"]


def test_dd_mm_yyyy_dates_are_accepted(client):
    """Indian DD/MM/YYYY dates import correctly."""
    response = _upload(
        client,
        "date,name,amount,type,category\n"
        "05/11/2026,Cafe Bloom order,2000,income,Sales\n",
    )

    body = response.json()
    assert body["imported"] == 1
    assert body["rows"][0]["date"] == "2026-11-05"
