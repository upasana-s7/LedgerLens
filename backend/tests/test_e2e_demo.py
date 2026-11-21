"""The whole demo story in one test (Stage 10).

This is the safety net for the live demo: it walks the exact order the presenter
clicks through - dashboard, upload, confirm, receivables, mark paid, dashboard
again, copilot - on ONE fresh seed, and asserts every state transition.

Nothing here calls Google. `_extract_with_gemini` is monkeypatched for the
upload, and the copilot runs with `GEMINI_API_KEY` blanked so it uses its
deterministic fallback path. The test therefore proves the backend logic, not
the network.
"""

import base64
import os

import pytest

from app.core.config import settings
from app.services import invoices as service

TINY_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

NEW_INVOICE = {
    "client": "Cafe Test",
    "due_date": "2026-12-15",
    "amount": 28910,
    "invoice_number": "TEST-999",
}


def test_full_demo_story(client, db_session, monkeypatch):
    new_id = None
    upload_path = None
    try:
        # Act 1: baseline - the numbers the demo opens on.
        dashboard1 = client.get("/api/dashboard").json()
        assert dashboard1["kpis"]["available_cash"]["value"] == 342500.0
        assert dashboard1["kpis"]["projected_30d"]["value"] == 130513.34
        receivables1 = client.get("/api/receivables").json()
        assert receivables1["outstanding_total"] == 109500.0
        assert receivables1["overdue_count"] == 2

        # Act 2: upload a new invoice. The extractor is faked, so no Gemini call.
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key-for-test")
        monkeypatch.setattr(
            service,
            "_extract_with_gemini",
            lambda content, mime_type: dict(NEW_INVOICE),
        )
        upload = client.post(
            "/api/invoices/upload",
            files={"file": ("t.png", TINY_PNG, "image/png")},
        ).json()
        assert upload["status"] == "Draft"
        new_id = upload["id"]
        assert new_id == "INV-212"
        assert upload["fields"]["client"] == "Cafe Test"
        assert upload["confidence"] == 1.0
        assert upload["warnings"] == []

        # A draft is not real money yet: receivables must not move.
        draft_receivables = client.get("/api/receivables").json()
        assert draft_receivables["outstanding_total"] == 109500.0
        assert new_id not in [item["id"] for item in draft_receivables["items"]]

        # Act 3: confirm it - the gate into receivables.
        confirm = client.post(
            f"/api/invoices/{new_id}/confirm", json=NEW_INVOICE
        ).json()
        assert confirm["status"] == "Pending"
        assert confirm["invoice"]["client"] == "Cafe Test"
        assert confirm["invoice"]["amount"] == 28910.0

        # Act 4: receivables reflects the new invoice.
        receivables2 = client.get("/api/receivables").json()
        assert receivables2["outstanding_total"] == 109500.0 + 28910.0
        assert any(item["id"] == new_id for item in receivables2["items"])
        # The new invoice is due in the future, so the overdue count holds.
        assert receivables2["overdue_count"] == 2

        # Act 5: mark an existing overdue invoice paid (INV-204, Rs 52,000).
        mark = client.post("/api/receivables/INV-204/mark-paid").json()
        assert mark["status"] == "Paid"
        assert mark["outstanding_total"] == 109500.0 + 28910.0 - 52000.0
        assert mark["overdue_count"] == 1

        # Act 6: the dashboard sees the cash that just came in.
        dashboard2 = client.get("/api/dashboard").json()
        assert dashboard2["kpis"]["available_cash"]["value"] == 342500.0 + 52000.0
        # The forecast starts from the new balance and the collected payment
        # also lifts the 90-day income baseline, so the projection rises.
        assert (
            dashboard2["kpis"]["projected_30d"]["value"]
            > dashboard1["kpis"]["projected_30d"]["value"]
        )
        # Only INV-198 (Rs 33,000) is left overdue.
        assert dashboard2["kpis"]["overdue_receivables"]["value"] == 33000.0

        # Act 7: the copilot reads the updated state (fallback, no Gemini call).
        monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
        chat = client.post(
            "/api/copilot/chat",
            json={"message": "How much is overdue?", "history": []},
        ).json()
        assert chat["source"] == "fallback"
        assert "33,000" in chat["reply"] or "33000" in chat["reply"]
        assert "52,000" not in chat["reply"]
    finally:
        # The upload writes the original document into backend/uploads/.
        if new_id:
            upload_path = os.path.join(service.UPLOAD_DIR, f"{new_id}.png")
            if os.path.exists(upload_path):
                os.remove(upload_path)
            try:
                os.rmdir(service.UPLOAD_DIR)
            except OSError:
                # Another file (or another test's upload) is still there.
                pass
