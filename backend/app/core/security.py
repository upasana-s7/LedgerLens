"""The `get_current_user` dependency: the one gate in front of the API.

Every financial route depends on it, so a request without a valid session
cookie stops here with a 401 and never touches the financial services.

Note on scope: knowing *who* is calling is all we check. The Bloom & Bean data
is shared, so no route filters rows by user id.
"""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.services.auth import decode_access_token

# Name of the HttpOnly cookie that carries the signed token.
COOKIE_NAME = "access_token"


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    """Build the standard 401 (with the header browsers expect on auth errors)."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    """Return the signed-in `User`, or raise 401.

    Three ways to fail, all 401 so the frontend's single "not logged in" path
    handles them:
      1. no `access_token` cookie,
      2. a cookie that is not a valid, unexpired token signed by us,
      3. a token that points at a user who no longer exists.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise _unauthorized()

    payload = decode_access_token(token)
    if payload is None:
        raise _unauthorized("Invalid or expired session")

    subject = payload.get("sub")
    try:
        user_id = int(subject)
    except (TypeError, ValueError):
        raise _unauthorized("Invalid or expired session") from None

    user = db.get(User, user_id)
    if user is None:
        raise _unauthorized("Invalid or expired session")

    return user
