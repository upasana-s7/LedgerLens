"""LedgerLens API entry point.

Run it from the backend/ folder:
    uvicorn app.main:app --reload

Then open http://127.0.0.1:8000/docs for interactive API documentation.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import (
    cashflow,
    copilot,
    dashboard,
    health,
    invoices,
    receivables,
    risk,
    simulator,
    transactions,
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "AI financial decision intelligence for Indian SMBs. "
        "Sample business: Bloom & Bean (fictional, Bengaluru). "
        "All money values are numbers in INR."
    ),
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# The React frontend runs on a different port, so the browser needs permission
# to call this API. `allow_credentials=False` because we do not use cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,  # dev only: Vite 5174/5175...
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes - everything lives under /api so the frontend has one base URL
# ---------------------------------------------------------------------------
app.include_router(health.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(cashflow.router, prefix="/api")
app.include_router(simulator.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
app.include_router(receivables.router, prefix="/api")
app.include_router(invoices.router, prefix="/api")
app.include_router(copilot.router, prefix="/api")
