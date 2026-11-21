"""Tests for the Stage 8 Virtual CFO (`/api/copilot/*`).

No test ever calls Google. Tests that exercise the Gemini path monkeypatch
`_call_gemini` on the service module, so the suite needs no network and no key.
"""

import pytest

from app.core.config import settings
from app.services import copilot as copilot_service

CHIPS = [
    "Can I afford new inventory?",
    "What needs my attention?",
    "How much is overdue?",
]
PANEL = [
    "Can I afford a Rs 50,000 inventory order?",
    "Which invoices should I follow up on?",
    "What is changing my cash position?",
]


def _ask(client, message, history=None):
    return client.post(
        "/api/copilot/chat",
        json={"message": message, "history": history or []},
    )


@pytest.fixture()
def fallback_client(client, monkeypatch):
    """A client whose settings say 'no API key', forcing the fallback path."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    return client


@pytest.fixture()
def gemini_client(client, monkeypatch):
    """A client with a fake key; tests then mock `_call_gemini` themselves."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake-key-for-test")
    return client


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

def test_suggestions_returns_static_lists(client):
    response = client.get("/api/copilot/suggestions")

    assert response.status_code == 200
    body = response.json()
    assert body["chips"] == CHIPS
    assert body["panel"] == PANEL
    assert len(body["chips"]) == 3
    assert len(body["panel"]) == 3


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_chat_empty_message_returns_422(client):
    response = _ask(client, "")

    assert response.status_code == 422


def test_chat_too_long_message_returns_422(client):
    response = _ask(client, "a" * 2001)

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------

def test_fallback_when_no_api_key(fallback_client):
    response = _ask(fallback_client, "hello")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fallback"
    assert len(body["reply"]) > 50
    assert body["suggested_questions"] == CHIPS


def test_fallback_affordability_question_mentions_real_numbers(fallback_client):
    response = _ask(fallback_client, "Can I afford a Rs 50,000 inventory order?")

    body = response.json()
    assert body["source"] == "fallback"
    reply = body["reply"]
    assert "130,513" in reply or "130513" in reply
    assert "INV-204" in reply or "INV-198" in reply
    assert body["citations"], "an affordability answer should cite the invoice"


def test_fallback_attention_question_mentions_risks(fallback_client):
    response = _ask(fallback_client, "What needs my attention?")

    body = response.json()
    reply = body["reply"].lower()
    assert "overdue" in reply or "85,000" in reply or "risk" in reply
    assert any(citation["kind"] == "alert" for citation in body["citations"])


def test_fallback_cash_question(fallback_client):
    response = _ask(fallback_client, "What is my cash position?")

    reply = response.json()["reply"]
    assert "342,500" in reply or "342500" in reply
    assert "30-day" in reply or "forecast" in reply.lower()


def test_fallback_default(fallback_client):
    response = _ask(fallback_client, "hello")

    reply = response.json()["reply"].lower()
    assert any(word in reply for word in ("cash", "overdue", "risk"))


# ---------------------------------------------------------------------------
# Gemini path
# ---------------------------------------------------------------------------

def test_gemini_path_returns_gemini_source(gemini_client, monkeypatch):
    monkeypatch.setattr(
        copilot_service,
        "_call_gemini",
        lambda message, history, context: (
            "Your cash is Rs 342,500 and INV-204 is overdue."
        ),
    )

    body = _ask(gemini_client, "How am I doing?").json()

    assert body["source"] == "gemini"
    assert body["reply"] == "Your cash is Rs 342,500 and INV-204 is overdue."
    assert [c["id"] for c in body["citations"]] == ["INV-204"]
    assert body["citations"][0]["label"] == "Aarav Foods · Rs 52,000"
    assert body["suggested_questions"] == CHIPS


def test_gemini_failure_falls_back(gemini_client, monkeypatch):
    def _boom(message, history, context):
        raise RuntimeError("network down")

    monkeypatch.setattr(copilot_service, "_call_gemini", _boom)

    response = _ask(gemini_client, "What needs my attention?")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "fallback"
    assert "85,000" in body["reply"]


def test_hallucinated_number_falls_back(gemini_client, monkeypatch):
    monkeypatch.setattr(
        copilot_service,
        "_call_gemini",
        lambda message, history, context: (
            "You should invest Rs 9,99,999 in new equipment."
        ),
    )

    body = _ask(gemini_client, "Should I invest?").json()

    assert body["source"] == "fallback"
    assert "9,99,999" not in body["reply"]


def test_empty_gemini_reply_falls_back(gemini_client, monkeypatch):
    monkeypatch.setattr(copilot_service, "_call_gemini", lambda *args: "   ")

    body = _ask(gemini_client, "How am I doing?").json()

    assert body["source"] == "fallback"


def test_citation_extraction_from_reply(gemini_client, monkeypatch):
    monkeypatch.setattr(
        copilot_service,
        "_call_gemini",
        lambda message, history, context: (
            "INV-198 is the oldest overdue invoice and RISK-1 is the buffer "
            "breach at Rs 129,296."
        ),
    )

    body = _ask(gemini_client, "What is most urgent?").json()

    assert body["source"] == "gemini"
    kinds = {citation["kind"] for citation in body["citations"]}
    ids = [citation["id"] for citation in body["citations"]]
    assert kinds == {"invoice", "alert"}
    assert "INV-198" in ids
    assert "RISK-1" in ids
    assert "The Daily Table · Rs 33,000" in [
        citation["label"] for citation in body["citations"]
    ]


def test_citation_unknown_id_skipped(gemini_client, monkeypatch):
    monkeypatch.setattr(
        copilot_service,
        "_call_gemini",
        lambda message, history, context: "INV-9999 is critical.",
    )

    body = _ask(gemini_client, "Which invoice is critical?").json()

    assert body["source"] == "gemini"
    assert body["citations"] == []


def test_transaction_citation_uses_risk_evidence(gemini_client, monkeypatch):
    monkeypatch.setattr(
        copilot_service,
        "_call_gemini",
        lambda message, history, context: (
            "The compressor replacement TXN-0968 cost Rs 78,000."
        ),
    )

    body = _ask(gemini_client, "Which expense was unusual?").json()

    assert body["source"] == "gemini"
    assert body["citations"][0]["kind"] == "transaction"
    assert body["citations"][0]["id"] == "TXN-0968"
    assert body["citations"][0]["label"].startswith(
        "Cold room compressor replacement"
    )


def test_history_passed_to_gemini(gemini_client, monkeypatch):
    captured = {}

    def _capture(message, history, context):
        captured["message"] = message
        captured["history"] = history
        return "Your cash is Rs 342,500."

    monkeypatch.setattr(copilot_service, "_call_gemini", _capture)

    body = _ask(
        gemini_client,
        "And next month?",
        history=[
            {"role": "user", "text": "hi"},
            {"role": "assistant", "text": "hello"},
        ],
    ).json()

    assert body["source"] == "gemini"
    assert captured["message"] == "And next month?"
    assert [turn.role for turn in captured["history"]] == ["user", "assistant"]
    assert [turn.text for turn in captured["history"]] == ["hi", "hello"]


def test_max_5_citations(gemini_client, monkeypatch):
    monkeypatch.setattr(
        copilot_service,
        "_call_gemini",
        lambda message, history, context: (
            "INV-198, INV-204, RISK-1, RISK-2, RISK-3 and RISK-4 all matter, "
            "with Rs 342,500 in cash."
        ),
    )

    body = _ask(gemini_client, "Summarise everything").json()

    assert body["source"] == "gemini"
    assert len(body["citations"]) == 5


def test_number_guard_accepts_rounded_context_values(gemini_client, monkeypatch):
    """A rounded paraphrase of a real figure is not treated as a hallucination."""
    monkeypatch.setattr(
        copilot_service,
        "_call_gemini",
        lambda message, history, context: (
            "Cash of Rs 342,500 leaves roughly Rs 130,000 projected in 30 days."
        ),
    )

    body = _ask(gemini_client, "How is the month looking?").json()

    assert body["source"] == "gemini"
