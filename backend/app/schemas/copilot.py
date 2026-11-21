"""Request/response shapes for the Stage 8 Virtual CFO copilot.

Two endpoints share these models:

* `POST /api/copilot/chat` takes a question plus a short history and returns
  prose, three follow-up questions, and citations that point at real records.
* `GET /api/copilot/suggestions` returns the fixed starter questions.

`source` tells the client where the prose came from: `"gemini"` when the model
answered, `"fallback"` when deterministic Python did. Both are valid replies, so
the UI never needs to show an error for a fallback.
"""

from typing import Literal

from pydantic import BaseModel, Field

ChatRole = Literal["user", "assistant"]
CitationKind = Literal["invoice", "transaction", "alert"]
ReplySource = Literal["gemini", "fallback"]


class ChatTurn(BaseModel):
    """One earlier turn of the conversation."""

    role: ChatRole
    text: str


class ChatRequest(BaseModel):
    """A question from the copilot input box."""

    message: str = Field(min_length=1, max_length=2000)
    # Default is a fresh list per request (never a shared mutable default).
    history: list[ChatTurn] = Field(default_factory=list)


class Citation(BaseModel):
    """A record the reply relied on, ready to render as a clickable chip."""

    kind: CitationKind
    id: str
    label: str


class ChatResponse(BaseModel):
    """One copilot answer."""

    reply: str
    # Always exactly three chips, taken from the suggestions endpoint.
    suggested_questions: list[str]
    # May be empty: general questions often cite nothing specific.
    citations: list[Citation]
    source: ReplySource


class SuggestionsResponse(BaseModel):
    """The static starter questions for the copilot panel."""

    # Short buttons above the input, exactly three.
    chips: list[str]
    # Empty-state prompts, exactly three.
    panel: list[str]
