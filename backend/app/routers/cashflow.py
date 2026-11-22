"""Cash-flow forecast router.

All the arithmetic lives in `app/services/forecast.py`; this route only
validates the horizon and wires the database session in.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.cashflow import ForecastResponse
from app.services.forecast import build_forecast

router = APIRouter(tags=["Cash Flow"])


@router.get("/cashflow/forecast", response_model=ForecastResponse)
def get_forecast(
    days: int = Query(90, ge=30, le=180, description="Projection horizon in days"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ForecastResponse:
    """Balance history + forward projection, commitments and assumptions."""
    try:
        return build_forecast(db, days=days)
    except ValueError as exc:
        # Raised when the database has no business profile to forecast from.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
