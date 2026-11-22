"""Authentication router (Stage 11).

Four things a user can do: register, log in, read/update their profile, and
log out. A successful register/login also sets the session cookie, so the
frontend never has to store a token itself (and cannot: the cookie is
HttpOnly, invisible to JavaScript).

Cookie flags explained:
  httponly=True   -> JavaScript cannot read it (blocks token theft via XSS)
  samesite="lax"  -> not sent on cross-site sub-requests (blocks most CSRF)
  secure=False    -> allowed over plain http, which localhost dev uses.
                     MUST become True behind HTTPS in production.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import COOKIE_NAME, get_current_user
from app.models.user import User
from app.schemas.auth import UserCreate, UserLogin, UserResponse, UserUpdate
from app.services.auth import (
    create_access_token,
    get_password_hash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# Matches ACCESS_TOKEN_EXPIRE_MINUTES (1440 minutes by default = 24 hours).
# The cookie and the token expire together.
COOKIE_MAX_AGE = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def _set_session_cookie(response: Response, user: User) -> None:
    """Sign a token for `user` and attach it to the response as a cookie."""
    token = create_access_token({"sub": str(user.id)})
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=COOKIE_MAX_AGE,
    )


def _find_user_by_email(db: Session, email: str) -> User | None:
    """Case-insensitive lookup, so "A@x.com" and "a@x.com" are one account."""
    return db.scalar(select(User).where(User.email == email.strip().lower()))


@router.post("/register", response_model=UserResponse)
def register(
    payload: UserCreate, response: Response, db: Session = Depends(get_db)
) -> UserResponse:
    """Create an account and sign it in straight away."""
    email = payload.email.strip().lower()

    if _find_user_by_email(db, email) is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email already exists",
        )

    user = User(
        name=payload.name.strip(),
        email=email,
        hashed_password=get_password_hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    _set_session_cookie(response, user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse)
def login(
    payload: UserLogin, response: Response, db: Session = Depends(get_db)
) -> UserResponse:
    """Sign in with email + password and start a session cookie."""
    user = _find_user_by_email(db, payload.email)

    # One message for both failures, so the response cannot be used to find
    # out which emails have accounts.
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    _set_session_cookie(response, user)
    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
def read_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Who am I? Used by the frontend on load to restore the session."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Change the display name and/or the email of the signed-in account."""
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Name cannot be empty",
            )
        current_user.name = name

    if payload.email is not None:
        email = payload.email.strip().lower()
        if email != current_user.email:
            existing = _find_user_by_email(db, email)
            if existing is not None and existing.id != current_user.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="An account with this email already exists",
                )
            current_user.email = email

    db.commit()
    db.refresh(current_user)
    return UserResponse.model_validate(current_user)


@router.post("/logout")
def logout(response: Response) -> dict:
    """Drop the session cookie. Safe to call even when not signed in."""
    response.delete_cookie(key=COOKIE_NAME)
    return {"detail": "Logged out"}
