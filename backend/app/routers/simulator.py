"""What-If simulator router.

All the arithmetic lives in `app/services/simulator.py`; this route validates
the two sliders (Pydantic returns 422 for out-of-range values) and wires the
database session in.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.simulator import SimulatorRequest, SimulatorResponse
from app.services.simulator import build_simulation

router = APIRouter(tags=["Simulator"])


@router.post("/simulator/run", response_model=SimulatorResponse)
def run_simulation(
    payload: SimulatorRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SimulatorResponse:
    """Run one what-if scenario (purchase amount + revenue uplift)."""
    try:
        return build_simulation(db, payload)
    except ValueError as exc:
        # Raised when the database has no business profile to simulate against.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
