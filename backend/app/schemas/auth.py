"""Request and response bodies for authentication (Stage 11).

The password is accepted on the way in and never returned: `UserResponse` only
carries the public fields the frontend needs to greet the user.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Body of `POST /api/auth/register`."""

    name: str
    email: EmailStr
    # 8 characters is the lowest we accept; Pydantic answers 422 below that.
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    """Body of `POST /api/auth/login`."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """The signed-in user, as returned by register / login / me."""

    # Allows `UserResponse.model_validate(user_row)` straight from the ORM.
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


class UserUpdate(BaseModel):
    """Body of `PATCH /api/auth/me`. Both fields are optional."""

    name: Optional[str] = None
    email: Optional[str] = None
