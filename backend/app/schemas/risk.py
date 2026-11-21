"""Response shapes for `GET /api/risk/alerts` (Stage 6 Risk Radar).

Every value here is computed by `app.services.risk` from the database. `metric`
is a pre-formatted display string ("Rs 85,000", "+24%"), so the frontend prints
it verbatim and never runs it through a money formatter.
"""

from typing import Literal

from pydantic import BaseModel

# Severity drives ordering; tone drives colour.
Severity = Literal["high", "medium", "low"]
RiskTone = Literal["coral", "amber", "sage"]

# What kind of record an alert points at, so the UI can deep-link.
EvidenceKind = Literal["invoice", "transaction", "commitment"]


class EvidencePointer(BaseModel):
    """One record behind an alert."""

    kind: EvidenceKind
    id: str
    label: str


class RiskAlert(BaseModel):
    """A single detected risk, ready to render as a card."""

    id: str
    severity: Severity
    tone: RiskTone
    title: str
    subtitle: str
    metric: str
    body: str
    impact_label: str
    impact_value: str
    action_label: str
    evidence: list[EvidencePointer]


class RiskSummary(BaseModel):
    """The badge at the top of the Risk Radar screen."""

    attention_count: int
    note: str
    tag: str


class RiskResponse(BaseModel):
    """Everything the Risk Radar screen needs, in one request."""

    summary: RiskSummary
    alerts: list[RiskAlert]
    risk_score: int
