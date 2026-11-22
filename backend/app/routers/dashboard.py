"""Dashboard router - headline KPIs, cash-flow chart, AI CFO card, risks.

All numbers are computed in `app/services/kpi.py`; this route just wires the
database session in and returns the response model.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.dashboard import DashboardResponse
from app.services.kpi import build_dashboard

router = APIRouter(tags=["Dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    """KPIs + cash-flow series + insight + AI CFO summary + recent activity."""
    return build_dashboard(db)
