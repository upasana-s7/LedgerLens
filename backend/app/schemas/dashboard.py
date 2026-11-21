"""Response shapes for `GET /api/dashboard`.

These mirror the JSON in docs/API_CONTRACT.md exactly. Every money value is a
plain number in rupees; `change`, `note`, `tone`, `insight` and the AI CFO
text are ready-to-print display strings chosen by the backend.
"""

from typing import Literal

from pydantic import BaseModel

from app.schemas.transaction import TransactionResponse

# Design tokens shared with the frontend CSS variables.
Tone = Literal["green", "sage", "amber", "coral"]
RiskTone = Literal["coral", "amber", "sage"]


class Workspace(BaseModel):
    """Who the numbers belong to."""

    name: str
    type: str
    city: str
    is_sample_data: bool


class Period(BaseModel):
    """The month the dashboard is showing."""

    label: str
    start: str
    end: str


class KpiCard(BaseModel):
    """One headline number with its caption and colour token."""

    value: float
    change: str
    note: str
    tone: Tone


class DashboardKpis(BaseModel):
    """The four KPI cards on the Overview screen."""

    available_cash: KpiCard
    projected_30d: KpiCard
    overdue_receivables: KpiCard
    safe_to_spend: KpiCard


class CashflowPoint(BaseModel):
    """One month on the cash-flow chart.

    `actual` is None for months that have not happened yet - never 0, which
    would drag the chart line down to zero.
    """

    month: str
    month_iso: str
    actual: float | None
    forecast: float


class AiCfo(BaseModel):
    """The "AI CFO" card. `source` is "rules" until Gemini writes the prose."""

    tag: str
    title: str
    body: str
    updated_at: str
    source: Literal["rules", "gemini"]


class RiskItem(BaseModel):
    """A short risk line shown on the dashboard."""

    tone: RiskTone
    title: str
    detail: str


class DashboardResponse(BaseModel):
    """Everything the Overview screen needs, in one request."""

    workspace: Workspace
    period: Period
    as_of_date: str
    kpis: DashboardKpis
    cashflow_series: list[CashflowPoint]
    series_range_label: str
    insight: str
    ai_cfo: AiCfo
    risk_items: list[RiskItem]
    recent_transactions: list[TransactionResponse]
