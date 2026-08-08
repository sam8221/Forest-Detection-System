"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: User Schemas

Purpose:
    Defines Pydantic schemas for user management and
    authentication.

Responsibilities:
    - Validate user input.
    - Validate login requests.
    - Serialize user responses.
    - Support JWT authentication.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
)

from app.models.enums import UserRole


# ---------------------------------------------------------
# Base Schema
# ---------------------------------------------------------
class UserBase(BaseModel):
    """
    Common user fields.
    """

    full_name: str = Field(
        ...,
        min_length=3,
        max_length=150,
        description="Full name of the user.",
    )

    email: EmailStr = Field(
        ...,
        description="User email address.",
    )


# ---------------------------------------------------------
# Create Schema
# ---------------------------------------------------------
class UserCreate(UserBase):
    """
    Used by administrators when creating users.
    """

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Temporary password.",
    )

    role: UserRole = Field(
        ...,
        description="System role.",
    )


# ---------------------------------------------------------
# Update Schema
# ---------------------------------------------------------
class UserUpdate(BaseModel):
    """
    Used when updating a user.
    """

    full_name: str | None = Field(
        default=None,
        min_length=3,
        max_length=150,
    )

    email: EmailStr | None = None

    role: UserRole | None = None

    is_active: bool | None = None


# ---------------------------------------------------------
# Change Password Schema
# ---------------------------------------------------------
class ChangePasswordRequest(BaseModel):
    """
    Used when changing a password.
    """

    current_password: str

    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )


# ---------------------------------------------------------
# Login Schema
# ---------------------------------------------------------
class UserLogin(BaseModel):
    """
    User authentication request.
    """

    email: EmailStr

    password: str


# ---------------------------------------------------------
# User Response Schema
# ---------------------------------------------------------
class UserResponse(UserBase):
    """
    User returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    role: UserRole

    is_active: bool

    must_change_password: bool

    last_login: datetime | None

    created_at: datetime

    updated_at: datetime


# ---------------------------------------------------------
# JWT Token Schema
# ---------------------------------------------------------
class Token(BaseModel):
    """
    JWT access token.
    """

    access_token: str

    token_type: str = "bearer"


# ---------------------------------------------------------
# JWT Payload Schema
# ---------------------------------------------------------
class TokenData(BaseModel):
    """
    Decoded JWT payload.
    """

    email: EmailStr | None = None

    role: UserRole | None = None
class UserSummary(BaseModel):
    id: int
    full_name: str
    email: EmailStr

    model_config = ConfigDict(from_attributes=True)