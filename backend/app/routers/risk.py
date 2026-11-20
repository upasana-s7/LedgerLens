"""Cash-flow risk radar router.

Alert rules arrive in Stage 6: deterministic thresholds, no AI guessing.
"""

from fastapi import APIRouter

from app.routers import not_implemented

router = APIRouter(tags=["Risk"])


@router.get("/risk/alerts")
def get_alerts() -> dict:
    """List risk alerts (high / medium / low) with their evidence."""
    raise not_implemented(6)
