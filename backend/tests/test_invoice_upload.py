"""Tests for invoice upload + confirm (Stage 9).

No test calls Google: `_extract_with_gemini` is monkeypatched, so the suite
exercises validation, warnings, persistence and the Draft -> Pending gate
without a network or an API key.
"""

import base64
import os

import pytest

from app.core.config import settings
from app.services import invoices as service

TINY_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

GOOD_FIELDS = {
    "client": "Cafe Aroma",
    "due_date": "2026-12-15",
    "amount": 28910,
    "invoice_number": "LL-2026-212",
}

CONFIRM_BODY = {
    "client": "Cafe Aroma",
    "due_date": "2026-12-15",
    "amount": 28910,
    "invoice_number": "LL-2026-212",
}


@pytest.fixture()
def upload_dir(tmp_path, monkeypatch):
    """Run uploads inside a temp folder so nothing lands in backend/uploads/."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path
    # tmp_path is cleaned up by pytest.


@pytest.fixture()
def api(client, upload_dir, monkeypatch):
    """A client with a fake key so the extraction branch is taken."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key-for-test")
    return client


@pytest.fixture()
def extractor(monkeypatch):
    """Install a fake extractor and return a function to change its behaviour."""

    def _install(result=None, error=None):
        def _fake(content, mime_type):
            if error is not None:
                raise error
            return dict(result or GOOD_FIELDS)

        monkeypatch.setattr(service, "_extract_with_gemini", _fake)

    _install(GOOD_FIELDS)
    return _install


def _upload(api, name="invoice.png", content=TINY_PNG, mime="image/png"):
    return api.post(
        "/api/invoices/upload",
        files={"file": (name, content, mime)},
    )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

def test_upload_pdf_happy_path_mocked(api, extractor):
    response = _upload(
        api, "invoice.pdf", b"%PDF-1.4 fake", "application/pdf"
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == "INV-212"
    assert body["status"] == "Draft"
    assert body["confidence"] == 1.0
    assert body["warnings"] == []
    assert body["fields"] == {
        "client": "Cafe Aroma",
        "due_date": "2026-12-15",
        "amount": 28910.0,
        "invoice_number": "LL-2026-212",
    }


def test_upload_png_happy_path_mocked(api, extractor):
    response = _upload(api)

    assert response.status_code == 201
    assert response.json()["id"] == "INV-212"
    assert response.json()["confidence"] == 1.0


def test_upload_creates_file_on_disk(api, extractor, upload_dir):
    response = _upload(api)

    path = os.path.join("uploads", f"{response.json()['id']}.png")
    assert os.path.exists(path)
    with open(path, "rb") as fh:
        assert fh.read() == TINY_PNG


def test_upload_saves_draft_row(api, extractor, seeded_db):
    response = _upload(api)
    invoice = seeded_db.get(service.Invoice, response.json()["id"])

    assert invoice is not None
    assert invoice.status == "Draft"
    assert invoice.source == "extracted"
    assert invoice.confidence == 1.0
    assert invoice.invoice_number == "LL-2026-212"


def test_upload_extraction_failure_still_returns_201(api, extractor):
    extractor(error=RuntimeError("vision exploded"))

    response = _upload(api)

    assert response.status_code == 201
    body = response.json()
    assert body["confidence"] == 0.0
    assert any("extraction failed" in warning for warning in body["warnings"])
    assert body["fields"]["client"] == ""


def test_upload_empty_fields_produce_warnings(api, extractor):
    extractor({"client": "", "due_date": "", "amount": 0, "invoice_number": ""})

    body = _upload(api).json()

    assert body["confidence"] == 0.0
    assert len(body["warnings"]) == 4
    assert "Could not read customer name." in body["warnings"]
    assert "Could not read invoice total." in body["warnings"]


def test_upload_without_api_key_skips_extraction(api, extractor, monkeypatch):
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")

    body = _upload(api).json()

    assert body["confidence"] == 0.0
    assert any("not configured" in warning for warning in body["warnings"])


def test_upload_unsupported_mime_returns_400(api, extractor):
    response = _upload(api, "invoice.gif", b"GIF89a", "image/gif")

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_oversize_returns_400(api, extractor):
    response = _upload(api, content=b"x" * (6 * 1024 * 1024))

    assert response.status_code == 400
    assert response.json()["detail"] == "File exceeds 5 MB limit"


def test_upload_without_file_returns_422(api):
    response = api.post("/api/invoices/upload", files={})

    assert response.status_code == 422


def test_next_invoice_id_after_upload(api, extractor):
    first = _upload(api).json()["id"]
    second = _upload(api).json()["id"]

    assert (first, second) == ("INV-212", "INV-213")


def test_extraction_prompt_uses_correct_mime(api, monkeypatch):
    captured = {}

    def _fake(content, mime_type):
        captured["mime"] = mime_type
        captured["size"] = len(content)
        return dict(GOOD_FIELDS)

    monkeypatch.setattr(service, "_extract_with_gemini", _fake)

    _upload(api, "invoice.jpeg", b"\xff\xd8\xff\xe0", "image/jpeg")

    assert captured == {"mime": "image/jpeg", "size": 4}


def test_upload_handles_non_numeric_amount(api, monkeypatch):
    monkeypatch.setattr(
        service,
        "_extract_with_gemini",
        lambda content, mime_type: {
            "client": "Cafe Aroma",
            "due_date": "2026-12-15",
            "amount": "not a number",
            "invoice_number": "LL-1",
        },
    )

    body = _upload(api).json()

    assert body["fields"]["amount"] == 0.0
    assert body["confidence"] == 0.75
    assert "Could not read invoice total." in body["warnings"]


# ---------------------------------------------------------------------------
# Confirm
# ---------------------------------------------------------------------------

def test_confirm_happy_path(api, extractor):
    invoice_id = _upload(api).json()["id"]

    response = api.post(
        f"/api/invoices/{invoice_id}/confirm", json=CONFIRM_BODY
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == invoice_id
    assert body["status"] == "Pending"
    assert body["invoice"] == {
        "id": invoice_id,
        "client": "Cafe Aroma",
        "due_date": "2026-12-15",
        "amount": 28910.0,
        "status": "Pending",
        "days_overdue": 0,
    }


def test_confirm_overrides_extracted_fields(api, extractor):
    extractor({"client": "", "due_date": "", "amount": 0, "invoice_number": ""})
    invoice_id = _upload(api).json()["id"]

    body = api.post(f"/api/invoices/{invoice_id}/confirm", json=CONFIRM_BODY).json()

    assert body["invoice"]["client"] == "Cafe Aroma"
    assert body["invoice"]["amount"] == 28910.0


def test_confirm_missing_invoice_returns_404(api):
    response = api.post("/api/invoices/INV-999/confirm", json=CONFIRM_BODY)

    assert response.status_code == 404
    assert response.json()["detail"] == "Invoice INV-999 not found"


def test_confirm_already_confirmed_returns_409(api, extractor):
    invoice_id = _upload(api).json()["id"]
    api.post(f"/api/invoices/{invoice_id}/confirm", json=CONFIRM_BODY)

    response = api.post(f"/api/invoices/{invoice_id}/confirm", json=CONFIRM_BODY)

    assert response.status_code == 409
    assert "already Pending" in response.json()["detail"]


def test_confirm_invalid_due_date_returns_422(api, extractor):
    invoice_id = _upload(api).json()["id"]

    response = api.post(
        f"/api/invoices/{invoice_id}/confirm",
        json={**CONFIRM_BODY, "due_date": "not-a-date"},
    )

    assert response.status_code == 422


def test_confirm_zero_amount_returns_422(api, extractor):
    invoice_id = _upload(api).json()["id"]

    response = api.post(
        f"/api/invoices/{invoice_id}/confirm",
        json={**CONFIRM_BODY, "amount": 0},
    )

    assert response.status_code == 422


def test_confirmed_invoice_appears_in_receivables(api, extractor):
    invoice_id = _upload(api).json()["id"]
    before = api.get("/api/receivables").json()["outstanding_total"]

    api.post(f"/api/invoices/{invoice_id}/confirm", json=CONFIRM_BODY)
    body = api.get("/api/receivables").json()

    ids = [item["id"] for item in body["items"]]
    assert invoice_id in ids
    assert body["outstanding_total"] == pytest.approx(before + 28910.0)


def test_draft_does_not_appear_in_receivables(api, extractor):
    invoice_id = _upload(api).json()["id"]

    body = api.get("/api/receivables").json()

    assert invoice_id not in [item["id"] for item in body["items"]]


def test_confirmed_invoice_appears_in_invoice_list(api, extractor):
    invoice_id = _upload(api).json()["id"]
    api.post(f"/api/invoices/{invoice_id}/confirm", json=CONFIRM_BODY)

    items = api.get("/api/invoices").json()["items"]
    entry = next(item for item in items if item["id"] == invoice_id)

    assert entry["status"] == "Pending"
    assert entry["amount"] == 28910.0
