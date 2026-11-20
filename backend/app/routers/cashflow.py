"""Cash-flow forecast router.

The forecast engine arrives in Stage 4 (deterministic Python + Pandas).
"""

from fastapi import APIRouter

from app.routers import not_implemented

router = APIRouter(tags=["Cash Flow"])


@router.get("/cashflow/forecast")
def get_forecast(days: int = 90) -> dict:
    """Balance history + forward projection, commitments and assumptions."""
    raise not_implemented(4)
