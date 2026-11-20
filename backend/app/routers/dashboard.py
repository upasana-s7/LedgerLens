"""Dashboard router - headline KPIs, cash-flow chart, AI CFO card, risks.

Logic arrives in Stage 3. See docs/API_CONTRACT.md for the response shape.
"""

from fastapi import APIRouter

from app.routers import not_implemented

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard")
def get_dashboard() -> dict:
    """KPIs + cash-flow series + insight + AI CFO summary + recent activity."""
    raise not_implemented(3)
