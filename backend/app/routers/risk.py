"""Cash-flow risk radar router.

Six deterministic rules live in `app.services.risk`; this router only wires
them to HTTP.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.risk import RiskResponse
from app.services.risk import build_risk_response

router = APIRouter(tags=["Risk"])


@router.get("/risk/alerts", response_model=RiskResponse)
def get_alerts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RiskResponse:
    """List risk alerts (high / medium / low) with their evidence."""
    try:
        return build_risk_response(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
