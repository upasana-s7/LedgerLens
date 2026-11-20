"""Health check endpoint.

Used by developers and by deployment platforms to confirm the API is alive.
"""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["Health"])


@router.get("/health")
def health() -> dict:
    """Return a tiny status payload.

    Tells you the server is running and which version it is on.
    """
    return {
        "status": "ok",
        "service": settings.APP_NAME,
        "version": settings.VERSION,
    }
