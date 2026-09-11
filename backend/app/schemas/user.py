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
    - Enforce password security requirements.
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
    field_validator,
)

from app.models.enums import UserRole


# =========================================================
# PASSWORD VALIDATION
# =========================================================

def validate_password_strength(value: str) -> str:
    """
    Enforce the ForestWatch Zambia password security policy.

    Password requirements:
        - Minimum 8 characters.
        - Maximum 128 characters.
        - At least one uppercase letter.
        - At least one lowercase letter.
        - At least one number.
        - At least one special character.
    """

    if not any(
        character.isupper()
        for character in value
    ):
        raise ValueError(
            "Password must contain at least one uppercase letter."
        )

    if not any(
        character.islower()
        for character in value
    ):
        raise ValueError(
            "Password must contain at least one lowercase letter."
        )

    if not any(
        character.isdigit()
        for character in value
    ):
        raise ValueError(
            "Password must contain at least one number."
        )

    if not any(
        not character.isalnum()
        for character in value
    ):
        raise ValueError(
            "Password must contain at least one special character."
        )

    return value


# =========================================================
# BASE USER SCHEMA
# =========================================================

class UserBase(BaseModel):
    """
    Defines the common information shared by user schemas.
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


# =========================================================
# USER CREATION SCHEMA
# =========================================================

class UserCreate(UserBase):
    """
    Defines the information required to create a new user.
    """

    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Temporary password meeting the system security policy.",
    )

    role: UserRole = Field(
        ...,
        description="System role assigned to the user.",
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """
        Validate password strength during user creation.
        """

        return validate_password_strength(value)


# =========================================================
# USER UPDATE SCHEMA
# =========================================================

class UserUpdate(BaseModel):
    """
    Defines fields that administrators may update.
    """

    full_name: str | None = Field(
        default=None,
        min_length=3,
        max_length=150,
    )

    email: EmailStr | None = None

    role: UserRole | None = None

    is_active: bool | None = None


# =========================================================
# CHANGE PASSWORD SCHEMA
# =========================================================

class ChangePasswordRequest(BaseModel):
    """
    Validates authenticated password-change requests.
    """

    current_password: str = Field(
        ...,
        min_length=1,
        description="Current account password.",
    )

    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="New password meeting the system security policy.",
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """
        Validate password strength during password changes.
        """

        return validate_password_strength(value)


# =========================================================
# LOGIN SCHEMA
# =========================================================

class UserLogin(BaseModel):
    """
    Defines the credentials submitted during authentication.
    """

    email: EmailStr

    password: str


# =========================================================
# USER RESPONSE SCHEMA
# =========================================================

class UserResponse(UserBase):
    """
    Defines the user information returned by the API.
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


# =========================================================
# JWT TOKEN SCHEMA
# =========================================================

class Token(BaseModel):
    """
    Defines the JWT access-token response.
    """

    access_token: str

    token_type: str = "bearer"


# =========================================================
# JWT PAYLOAD SCHEMA
# =========================================================

class TokenData(BaseModel):
    """
    Defines the decoded JWT payload.
    """

    email: EmailStr | None = None

    role: UserRole | None = None


# =========================================================
# USER SUMMARY SCHEMA
# =========================================================

class UserSummary(BaseModel):
    """
    Defines a lightweight user representation.
    """

    id: int

    full_name: str

    email: EmailStr

    model_config = ConfigDict(
        from_attributes=True,
    )