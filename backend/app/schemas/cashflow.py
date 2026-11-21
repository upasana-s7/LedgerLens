"""Response shapes for `GET /api/cashflow/forecast` (Stage 4).

Same convention as the dashboard schemas: money is a plain JSON number in
rupees (the service keeps Decimals and converts only at this boundary), and
dates are ISO strings (`YYYY-MM-DD`).
"""

from pydantic import BaseModel

from app.schemas.dashboard import CashflowPoint


class CommitmentItem(BaseModel):
    """One known upcoming payment the forecast already subtracted."""

    label: str
    # Always positive: it is an amount we owe, not a signed movement.
    amount: float
    date: str


class DailyPoint(BaseModel):
    """Closing cash on one projected day."""

    date: str
    balance: float


class LowestBalance(BaseModel):
    """The tightest point of the projection (the "lowest point" callout)."""

    value: float
    date: str


class ForecastResponse(BaseModel):
    """Everything the Cash Flow screen needs, in one request."""

    opening_balance: float
    inflows_30d: float
    # Positive number describing money going OUT, even though expense
    # transactions are stored as negative amounts.
    outflows_30d: float
    # The nine-point monthly chart shares its shape with the dashboard.
    series: list[CashflowPoint]
    # The day-by-day projection the chart's tooltip and Stage 5 reuse.
    daily_series: list[DailyPoint]
    range_label: str
    commitments: list[CommitmentItem]
    assumptions: list[str]
    lowest_balance: LowestBalance
    # None when the balance never dips below the safety buffer.
    shortfall_date: str | None
    is_sample_data: bool
