"""Request and response shapes for `POST /api/simulator/run` (Stage 5).

The ranges live on the fields themselves, so FastAPI rejects out-of-range
sliders with a 422 before any arithmetic runs. Every money value in the
response is a plain number in rupees, exactly like the dashboard and the
forecast.
"""

from typing import Literal

from pydantic import BaseModel, Field


class SimulatorRequest(BaseModel):
    """The two sliders on the What-If screen."""

    purchase_amount: float = Field(
        ..., ge=10000, le=200000, description="Planned purchase in rupees"
    )
    revenue_uplift_pct: float = Field(
        ..., ge=0, le=40, description="Expected revenue uplift, in percent"
    )


class SimulatorResponse(BaseModel):
    """One deterministic scenario result, ready to print."""

    # Closing balance of the 30-day forecast, before the scenario is applied.
    base_balance: float
    # What the purchase costs today (positive).
    scenario_cost: float
    # Extra cash the uplift generates over the same 30 days.
    additional_revenue: float
    # base_balance - scenario_cost + additional_revenue.
    projected_balance: float
    verdict: Literal["comfortable", "caution"]
    # Ready-to-show text for the verdict badge.
    verdict_label: str
    # The comfort threshold the verdict compares against.
    threshold: float
    explanation: str
    # "rules" until Stage 8 lets Gemini re-word verified numbers.
    explanation_source: Literal["rules", "gemini"]
