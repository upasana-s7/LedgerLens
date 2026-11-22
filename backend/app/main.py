"""LedgerLens API entry point.

Run it from the backend/ folder:
    uvicorn app.main:app --reload

Then open http://127.0.0.1:8000/docs for interactive API documentation.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.seed.seed_data import seed_if_empty
from app.routers import (
    auth,
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run once when the server starts, and once when it shuts down.

    On the way up we create any missing tables and, if AUTO_SEED is on, fill
    an empty database with the synthetic demo data. Seeding is skipped when
    the database already holds data, so restarts never duplicate rows.
    """
    init_db()
    if settings.AUTO_SEED:
        seed_if_empty()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
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
# to call this API. Since Stage 11 the session lives in an HttpOnly cookie, so
# `allow_credentials=True` is required for the browser to send it.
#
# Browsers reject `allow_origins=["*"]` together with credentials, so the
# allowed origins stay an explicit list (Vite 5173/4173, plus the dev-only
# 5174/5175 regex).
#
# In production the frontend is deployed separately (e.g. on Vercel), so its
# public URL comes from FRONTEND_URL and is added to the list here.
allowed_origins = list(settings.CORS_ORIGINS)
if settings.FRONTEND_URL not in allowed_origins:
    allowed_origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,  # dev only: Vite 5174/5175...
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routes - everything lives under /api so the frontend has one base URL
# ---------------------------------------------------------------------------
app.include_router(health.router, prefix="/api")  # public: no auth required
app.include_router(auth.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(transactions.router, prefix="/api")
app.include_router(cashflow.router, prefix="/api")
app.include_router(simulator.router, prefix="/api")
app.include_router(risk.router, prefix="/api")
app.include_router(receivables.router, prefix="/api")
app.include_router(invoices.router, prefix="/api")
app.include_router(copilot.router, prefix="/api")
