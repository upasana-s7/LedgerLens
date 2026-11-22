"""Password hashing and session tokens (Stage 11).

Two independent pieces:

1. **Passwords** are hashed with bcrypt through passlib. A hash is one-way and
   salted, so a leaked database still does not reveal the passwords.
2. **Sessions** are JSON Web Tokens signed with `settings.SECRET_KEY`. The
   token holds only the user id (`sub`) and an expiry (`exp`); the cookie that
   carries it is HttpOnly so page JavaScript cannot read it.
"""

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import settings

# bcrypt is the scheme; `deprecated="auto"` lets a future scheme be added
# without invalidating hashes already in the database.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HS256 = HMAC-SHA256, the standard symmetric choice for a single backend.
ALGORITHM = "HS256"


def get_password_hash(password: str) -> str:
    """Turn a plain password into a bcrypt hash for storage."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a typed password against a stored hash."""
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        # A malformed/unknown hash in the database is a mismatch, not a crash.
        return False


def create_access_token(data: dict) -> str:
    """Sign `data` (usually `{"sub": "<user id>"}`) and add an expiry."""
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Return the token's claims, or `None` if it is invalid or expired."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        # Bad signature, wrong algorithm, expired, not a JWT at all, ...
        return None
