"""AI Financial Copilot router (Stage 8).

The copilot answers with Python-verified numbers only. Gemini rewrites those
numbers as prose; when it cannot, a deterministic reply is returned instead.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.copilot import ChatRequest, ChatResponse, SuggestionsResponse
from app.services.copilot import build_chat_response, build_suggestions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Copilot"])


@router.post("/copilot/chat", response_model=ChatResponse)
def copilot_chat(
    payload: ChatRequest, db: Session = Depends(get_db)
) -> ChatResponse:
    """Ask a question about the business; returns a reply plus citations.

    Message length is validated by `ChatRequest`, so an empty or oversized
    message is a 422 before this function runs.
    """
    try:
        return build_chat_response(db, payload.message, payload.history)
    except Exception:  # noqa: BLE001 - never leak internals to the client
        logger.exception("Copilot chat failed")
        raise HTTPException(status_code=500, detail="Copilot unavailable")


@router.get("/copilot/suggestions", response_model=SuggestionsResponse)
def copilot_suggestions() -> SuggestionsResponse:
    """Starter questions shown as chips and in the copilot panel."""
    return build_suggestions()
