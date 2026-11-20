"""What-If simulator router.

The scenario maths arrives in Stage 5. All numbers are computed in Python.
"""

from fastapi import APIRouter

from app.routers import not_implemented

router = APIRouter(tags=["Simulator"])


@router.post("/simulator/run")
def run_simulation() -> dict:
    """Run one what-if scenario (purchase amount + revenue uplift)."""
    raise not_implemented(5)
