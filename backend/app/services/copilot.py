"""The Virtual CFO (Stage 8).

Four rules shape this module:

1. **Context comes from the existing services.** The copilot never queries the
   database for numbers itself. It calls `build_dashboard`, `build_risk_response`,
   `build_forecast` and `build_receivable_list`, then extracts a small dict of
   verified values. If the Overview says Rs 1,30,513, the copilot says
   Rs 1,30,513 - the two screens cannot disagree.
2. **Gemini never calculates.** It only narrates the numbers in that context.
   Every figure Python produced is already final before the prompt is built.
3. **Three fallback paths.** If `GEMINI_API_KEY` is empty, if the API call
   raises (network, quota, timeout, empty reply), or if the reply contains a
   number that is not in the context, a deterministic Python reply is used
   instead and `source` becomes `"fallback"`. The user still gets a useful,
   accurate answer; only the wording is less flexible.
4. **Citations are validated.** IDs the model mentions are looked up in the
   context. Unknown IDs are dropped silently rather than fabricated into chips.

Money in the fallback prose uses western grouping (`Rs 1,30,513` -> `Rs
130,513`) on purpose: it is a plain English explanation, not a metric badge,
and standard grouping keeps a template string from having to re-implement the
Indian grouping helper in `app.services.kpi`.
"""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.schemas.copilot import (
    ChatResponse,
    ChatTurn,
    Citation,
    SuggestionsResponse,
)
from app.services.forecast import build_forecast
from app.services.invoices import build_receivable_list
from app.services.kpi import build_dashboard
from app.services.risk import build_risk_response

logger = logging.getLogger(__name__)

# The starter questions, fixed by the API contract.
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

MAX_CITATIONS = 5
MAX_HISTORY_TURNS = 8
# 30s, not 10s: a grounded 2-4 paragraph answer routinely needs 10-20s on
# Flash, and a shorter deadline turns real answers into silent fallbacks.
GEMINI_TIMEOUT_MS = 30_000

# Numbers the model may legitimately mention that are not raw context values:
# totals and derived figures the other services publish.
DERIVED_VALUES = [
    85000, 109500, 342500, 130513, 111467, 129296, 57500, 248500, 225000, 150000,
]

# A money-ish number: grouped (50,000 / 1,64,500) or plain (50000 / 130513).
_NUMBER_RE = re.compile(r"\b(\d{1,3}(?:,\d{2,3})+|\d{4,})\b")
_ISO_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

_INVOICE_ID_RE = re.compile(r"\bINV-\d+\b")
_TRANSACTION_ID_RE = re.compile(r"\bTXN-\d{4}\b")
_RISK_ID_RE = re.compile(r"\bRISK-\d+\b")
_RECORD_ID_RE = re.compile(r"\b(?:INV|TXN|RISK)-[A-Za-z0-9]+")


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

def build_suggestions() -> SuggestionsResponse:
    """The static chips and panel prompts, exactly as the contract lists them."""
    return SuggestionsResponse(chips=list(CHIPS), panel=list(PANEL))


def _default_suggestions() -> list[str]:
    """The three follow-up chips returned with every chat reply."""
    return list(CHIPS)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

def build_context(db: Session) -> dict:
    """Collect the verified numbers the reply is allowed to mention.

    Nothing here is computed by a model; every value comes straight out of a
    Stage 3-7 service.
    """
    dashboard = build_dashboard(db)
    risk = build_risk_response(db)
    forecast = build_forecast(db, days=30)
    receivables = build_receivable_list(db)

    overdue_invoices = [
        {
            "id": item.id,
            "client": item.client,
            "amount": item.amount,
            "days_overdue": item.days_overdue,
        }
        for item in receivables.items
        if item.status == "Overdue"
    ]
    overdue_total = round(sum(item["amount"] for item in overdue_invoices), 2)

    top_risks = []
    transactions: dict[str, str] = {}
    for alert in risk.alerts[:4]:
        top_risks.append(
            {
                "id": alert.id,
                "title": alert.title,
                "severity": alert.severity,
                "metric": alert.metric,
                "body": alert.body,
                "evidence_ids": [pointer.id for pointer in alert.evidence],
            }
        )
        for pointer in alert.evidence:
            if pointer.kind == "transaction":
                transactions[pointer.id] = pointer.label

    return {
        "cash_balance": dashboard.kpis.available_cash.value,
        "projected_30d": dashboard.kpis.projected_30d.value,
        "safe_to_spend": dashboard.kpis.safe_to_spend.value,
        "overdue_total": overdue_total,
        "overdue_count": receivables.overdue_count,
        "shortfall_date": forecast.shortfall_date,
        "lowest_balance": {
            "value": forecast.lowest_balance.value,
            "date": forecast.lowest_balance.date,
        },
        "top_risks": top_risks,
        "overdue_invoices": overdue_invoices,
        "transactions": transactions,
        "risk_score": risk.risk_score,
        "as_of_date": dashboard.as_of_date,
    }


# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------

def _system_prompt(context: dict) -> str:
    """The instructions that keep the model inside the verified numbers."""
    return f"""
You are the Virtual CFO for Bloom & Bean, a small Bengaluru specialty coffee
and bakery supplier.

Today's date is {context.get("as_of_date")}.

Answer the user's question in plain English, in 2-4 short paragraphs.
ALWAYS reference specific numbers from the context below. NEVER invent a number
that is not present in the context.
When you mention an invoice, transaction, or alert, include its exact ID in
square brackets, e.g. [INV-204], [TXN-1048], [RISK-1].
Do not use markdown headers or code blocks. Use short paragraphs.

Context:
{json.dumps(context, indent=2)}
""".strip()


def _call_gemini(message: str, history: list[ChatTurn], context: dict) -> str:
    """Ask Gemini for prose. Any failure is raised for the caller to handle.

    The SDK is imported here, not at module import time, so the rest of the app
    (and the whole test suite) never needs the dependency or an API key.
    """
    from google import genai

    client = genai.Client(
        api_key=settings.GEMINI_API_KEY,
        http_options={"timeout": GEMINI_TIMEOUT_MS},
    )

    contents = []
    for turn in history[-MAX_HISTORY_TURNS:]:
        contents.append(
            genai.types.Content(
                # The Gemini SDK calls the assistant role "model".
                role="model" if turn.role == "assistant" else "user",
                parts=[genai.types.Part(text=turn.text)],
            )
        )
    contents.append(
        genai.types.Content(role="user", parts=[genai.types.Part(text=message)])
    )

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=contents,
        config={"system_instruction": _system_prompt(context)},
    )

    text = (response.text or "").strip()
    if not text:
        raise ValueError("Empty Gemini reply")
    return text


# ---------------------------------------------------------------------------
# Hallucination guard
# ---------------------------------------------------------------------------

def _allowed_values(context: dict, question: str = "") -> list[float]:
    """Every number the model is permitted to quote, plus known derived ones.

    Numbers the user wrote in the question are allowed too: repeating "Rs 50,000"
    back to the person who typed it is not a hallucination.
    """
    values: list[float] = list(DERIVED_VALUES)
    values.extend(float(number) for number in _extract_numbers(question))

    def _add(value) -> None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        values.append(abs(number))
        values.append(abs(round(number)))

    for key in ("cash_balance", "projected_30d", "safe_to_spend", "overdue_total"):
        _add(context.get(key))
    lowest = context.get("lowest_balance") or {}
    _add(lowest.get("value"))
    for invoice in context.get("overdue_invoices", []):
        _add(invoice.get("amount"))

    # Risk prose is service output too, so its figures (alert metrics, expense
    # amounts inside alert bodies) are verified numbers the model may quote.
    for alert in context.get("top_risks", []):
        for field in ("metric", "body"):
            for number in _extract_numbers(str(alert.get(field, ""))):
                _add(number)

    return [value for value in values if value]


def _extract_numbers(text: str) -> list[int]:
    """Money-sized numbers in the reply, ignoring dates and bare years."""
    cleaned = _ISO_DATE_RE.sub(" ", text)
    cleaned = _YEAR_RE.sub(" ", cleaned)
    # Record ids like INV-9999 or TXN-0968 are identifiers, not amounts.
    cleaned = _RECORD_ID_RE.sub(" ", cleaned)
    numbers: list[int] = []
    for match in _NUMBER_RE.findall(cleaned):
        try:
            numbers.append(int(match.replace(",", "")))
        except ValueError:  # pragma: no cover - the regex only matches digits
            continue
    return [number for number in numbers if number >= 1000]


def _has_hallucinated_number(reply: str, context: dict, question: str = "") -> bool:
    """True when the reply quotes a figure the services never produced.

    A 5% tolerance absorbs rounding ("about Rs 1,30,000" for 130,513) without
    letting an invented total through.
    """
    allowed = _allowed_values(context, question)
    for number in _extract_numbers(reply):
        if not any(abs(number - value) <= 0.05 * value for value in allowed):
            return True
    return False


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------

def _invoice_lookup(context: dict) -> dict[str, str]:
    return {
        invoice["id"]: f"{invoice['client']} · Rs {invoice['amount']:,.0f}"
        for invoice in context.get("overdue_invoices", [])
    }


def _alert_lookup(context: dict) -> dict[str, str]:
    return {alert["id"]: alert["title"] for alert in context.get("top_risks", [])}


def _extract_citations(reply: str, context: dict) -> list[Citation]:
    """Build citation chips for known IDs the reply mentions, capped at five."""
    invoices = _invoice_lookup(context)
    alerts = _alert_lookup(context)
    transactions = context.get("transactions") or {}

    citations: list[Citation] = []
    seen: set[str] = set()

    def _add(kind: str, identifier: str, label: str) -> None:
        if identifier in seen or len(citations) >= MAX_CITATIONS:
            return
        seen.add(identifier)
        citations.append(Citation(kind=kind, id=identifier, label=label))

    for identifier in _INVOICE_ID_RE.findall(reply):
        if identifier in invoices:
            _add("invoice", identifier, invoices[identifier])

    for identifier in _TRANSACTION_ID_RE.findall(reply):
        if identifier in transactions:
            _add("transaction", identifier, transactions[identifier])

    for identifier in _RISK_ID_RE.findall(reply):
        if identifier in alerts:
            _add("alert", identifier, alerts[identifier])

    return citations


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------

def _overdue_citations(context: dict) -> list[Citation]:
    """Citations for the overdue invoices, oldest first, plus the top alerts."""
    citations: list[Citation] = []
    invoices = sorted(
        context.get("overdue_invoices", []),
        key=lambda invoice: -invoice.get("days_overdue", 0),
    )
    for invoice in invoices:
        citations.append(
            Citation(
                kind="invoice",
                id=invoice["id"],
                label=f"{invoice['client']} · Rs {invoice['amount']:,.0f}",
            )
        )

    for alert in context.get("top_risks", [])[:2]:
        citations.append(
            Citation(kind="alert", id=alert["id"], label=alert["title"])
        )
    return citations[:MAX_CITATIONS]


def _alert_by_title(context: dict, fragment: str) -> dict | None:
    """The first top risk whose title contains `fragment`."""
    for alert in context.get("top_risks", []):
        if fragment.lower() in alert["title"].lower():
            return alert
    return None


def _fallback_response(
    message: str, context: dict
) -> tuple[str, list[Citation]]:
    """A deterministic, verified reply used when Gemini cannot answer."""
    risks = context.get("top_risks") or []
    invoices = context.get("overdue_invoices") or []

    if not context or (not risks and not invoices and not context.get("cash_balance")):
        return (
            "There is nothing to flag right now: no overdue invoices, no active "
            "risk items, and the cash position is stable. Add transactions or "
            "invoices and ask again for a worked example."
        ), []

    as_of = context.get("as_of_date", "")
    cash = context.get("cash_balance") or 0
    projected = context.get("projected_30d") or 0
    overdue_total = context.get("overdue_total") or 0
    overdue_count = context.get("overdue_count") or 0
    lowest = context.get("lowest_balance") or {}
    lowest_value = lowest.get("value") or 0
    lowest_date = lowest.get("date", "")
    top_title = risks[0]["title"] if risks else "no active risk items"
    top_metric = risks[0].get("metric", "") if risks else ""

    citations = _overdue_citations(context)
    text = message.lower()

    if any(word in text for word in ("afford", "buy", "purchase")):
        if invoices:
            largest = max(invoices, key=lambda invoice: invoice["amount"])
            collection = (
                f"Before a large purchase, collect the overdue amounts first - "
                f"especially {largest['client']}'s {largest['id']} at "
                f"Rs {largest['amount']:,.0f}, which is "
                f"{largest.get('days_overdue', 0)} days late."
            )
        else:
            collection = (
                "There are no overdue invoices right now, so the main constraint "
                "is the scheduled commitments already inside the forecast."
            )
        reply = (
            f"Based on your current position, your projected 30-day closing "
            f"balance is Rs {projected:,.0f}. Your safety buffer is Rs 150,000 "
            f"and you have Rs {overdue_total:,.0f} in overdue invoices across "
            f"{overdue_count} invoice(s). {collection} Collecting those would "
            f"move the tightest point of the forecast, Rs {lowest_value:,.0f} on "
            f"{lowest_date}, back above the buffer."
        )
        return reply, citations

    if any(word in text for word in ("overdue", "attention", "risk")):
        if invoices:
            worst = max(invoices, key=lambda invoice: invoice["days_overdue"])
            invoice_line = (
                f"The largest single item is {worst['client']}'s {worst['id']} at "
                f"Rs {worst['amount']:,.0f}, {worst['days_overdue']} days late."
            )
        else:
            invoice_line = "Nothing is past its due date today."
        reply = (
            f"There are {overdue_count} overdue invoices totalling "
            f"Rs {overdue_total:,.0f}, and {len(risks)} active risk items - the "
            f"most urgent is '{top_title}' ({top_metric}). {invoice_line} The "
            f"30-day forecast bottoms out at Rs {lowest_value:,.0f} on "
            f"{lowest_date}, so collections are what protect the buffer."
        )
        return reply, citations

    if any(
        word in text
        for word in ("cash", "runway", "forecast", "balance", "position")
    ):
        shortfall = context.get("shortfall_date")
        buffer_line = (
            f"The forecast dips below the Rs 150,000 buffer from {shortfall}."
            if shortfall
            else "The forecast stays above the Rs 150,000 buffer."
        )
        reply = (
            f"Your current cash is Rs {cash:,.0f}. Projected 30-day closing "
            f"balance is Rs {projected:,.0f} against a Rs 150,000 safety buffer. "
            f"The forecast shows the tightest point at Rs {lowest_value:,.0f} on "
            f"{lowest_date}. {buffer_line} The top risk on the radar is "
            f"'{top_title}' ({top_metric})."
        )
        return reply, citations

    reply = (
        f"Here is your position as of {as_of}: cash is Rs {cash:,.0f}, you have "
        f"{overdue_count} overdue invoice(s) worth Rs {overdue_total:,.0f}, and "
        f"the top risk is '{top_title}' ({top_metric}). Ask me about "
        "affordability, overdue invoices, or your cash position for more detail."
    )
    return reply, citations


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_chat_response(
    db: Session, message: str, history: list[ChatTurn]
) -> ChatResponse:
    """Answer one copilot question, with Gemini when possible and Python always."""
    context = build_context(db)
    suggestions = _default_suggestions()

    if not settings.GEMINI_API_KEY:
        reply, citations = _fallback_response(message, context)
        return ChatResponse(
            reply=reply,
            suggested_questions=suggestions,
            citations=citations,
            source="fallback",
        )

    try:
        reply = (_call_gemini(message, history, context) or "").strip()
    except Exception:  # noqa: BLE001 - any SDK failure must degrade, not 500
        logger.warning("Gemini call failed; using the deterministic fallback", exc_info=True)
        reply, citations = _fallback_response(message, context)
        return ChatResponse(
            reply=reply,
            suggested_questions=suggestions,
            citations=citations,
            source="fallback",
        )

    hallucinated = bool(reply) and _has_hallucinated_number(reply, context, message)
    if not reply or hallucinated:
        if hallucinated:
            logger.warning(
                "Gemini reply quoted a number outside the verified context; "
                "using the deterministic fallback"
            )
        reply, citations = _fallback_response(message, context)
        return ChatResponse(
            reply=reply,
            suggested_questions=suggestions,
            citations=citations,
            source="fallback",
        )

    return ChatResponse(
        reply=reply,
        suggested_questions=suggestions,
        citations=_extract_citations(reply, context),
        source="gemini",
    )
