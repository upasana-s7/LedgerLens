"""API routers, one file per feature area.

Each router is registered in `app/main.py` under the `/api` prefix.
"""

from fastapi import HTTPException


def not_implemented(stage: int) -> HTTPException:
    """Build the standard "planned for a later stage" error.

    Used by every placeholder endpoint so the frontend team can build against
    the real URLs today and see a clear 501 until the logic lands.

    Example: `raise not_implemented(3)` returns
        501 {"detail": "Not implemented yet (planned for Stage 3)"}
    """
    return HTTPException(
        status_code=501,
        detail=f"Not implemented yet (planned for Stage {stage})",
    )
