"""One run of the What-If simulator.

Inputs and results are stored as JSON so the numbers a user was shown can be
reproduced exactly, even after the calculation code changes.
"""

import datetime as dt

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SimulationRun(Base):
    """A saved scenario, e.g. "₹50,000 stock order with 15% uplift"."""

    __tablename__ = "simulation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # JSON, e.g. {"purchase_amount": 50000, "revenue_uplift_pct": 15}
    inputs_json: Mapped[str] = mapped_column(Text)
    # JSON with the computed balances and the verdict.
    results_json: Mapped[str] = mapped_column(Text)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
