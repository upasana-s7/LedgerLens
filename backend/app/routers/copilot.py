"""AI Financial Copilot router.

Arrives in Stage 8. The copilot answers with Python-verified numbers only.
"""

from fastapi import APIRouter

from app.routers import not_implemented

router = APIRouter(tags=["Copilot"])


@router.post("/copilot/chat")
def copilot_chat() -> dict:
    """Ask a question about the business; returns a reply plus citations."""
    raise not_implemented(8)


@router.get("/copilot/suggestions")
def copilot_suggestions() -> dict:
    """Starter questions shown as chips and in the copilot panel."""
    raise not_implemented(8)
