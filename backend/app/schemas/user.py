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
    model_validator,
)

from app.models.enums import UserRole


# =========================================================
# JURISDICTION VALIDATION
# =========================================================

def validate_role_jurisdiction(data):
    """
    Ensure an account's jurisdiction matches its role.

    Args:
        data:
            Schema carrying role, province_id and
            district_id.

    Returns:
        The same object when the combination is valid.

    Raises:
        ValueError:
            The jurisdiction does not match the role.

    Rules:

        DISTRICT_FORESTRY_OFFICER
            Must have a district. Without one the account
            can sign in but is refused every record, which
            looks to the officer like an empty database.

        PROVINCIAL_FORESTRY_OFFICER
            Must have a province, and must not have a
            district. A province already covers all of its
            districts, so setting both states the same
            authority twice and invites the two to
            disagree later.

        ADMIN
            Must have neither. Administration is national,
            and recording a district against it would
            suggest a limit that is not enforced.
    """

    role = data.role

    if role == UserRole.DISTRICT_FORESTRY_OFFICER:

        if not data.district_id:
            raise ValueError(
                "A District Forestry Officer must be "
                "assigned a district."
            )

        if data.province_id:
            raise ValueError(
                "A District Forestry Officer is assigned a "
                "district only. The province follows from "
                "the district."
            )

    elif role == UserRole.PROVINCIAL_FORESTRY_OFFICER:

        if not data.province_id:
            raise ValueError(
                "A Provincial Forestry Officer must be "
                "assigned a province."
            )

        if data.district_id:
            raise ValueError(
                "A Provincial Forestry Officer is assigned "
                "a province only, which already covers "
                "every district within it."
            )

    elif role == UserRole.ADMIN:

        if data.province_id or data.district_id:
            raise ValueError(
                "An Administrator is not assigned a "
                "jurisdiction, because administration is "
                "national."
            )

    return data


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

    An officer's jurisdiction is set here, when the account
    is provisioned. Without it the account can sign in but
    is refused every record, so leaving it out would create
    an officer who can see nothing.
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

    province_id: int | None = Field(
        default=None,
        description=(
            "Province a provincial officer is responsible "
            "for. Required for that role."
        ),
    )

    district_id: int | None = Field(
        default=None,
        description=(
            "District a district officer is responsible "
            "for. Required for that role."
        ),
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """
        Validate password strength during user creation.
        """

        return validate_password_strength(value)

    @model_validator(mode="after")
    def validate_jurisdiction(self) -> "UserCreate":
        """
        Ensure the jurisdiction matches the role.
        """

        return validate_role_jurisdiction(self)


# =========================================================
# USER UPDATE SCHEMA
# =========================================================

class UserUpdate(BaseModel):
    """
    Defines fields that administrators may update.

    Reassigning an officer changes what they can retrieve
    immediately, because jurisdiction is read from the
    account on every request rather than being carried in
    their access token.
    """

    full_name: str | None = Field(
        default=None,
        min_length=3,
        max_length=150,
    )

    email: EmailStr | None = None

    role: UserRole | None = None

    is_active: bool | None = None

    province_id: int | None = None

    district_id: int | None = None

    @model_validator(mode="after")
    def validate_jurisdiction(self) -> "UserUpdate":
        """
        Ensure the jurisdiction matches the role.

        Only checked when a role is supplied. A request that
        changes an unrelated field, such as a name, must not
        be forced to restate the jurisdiction.
        """

        if self.role is None:
            return self

        return validate_role_jurisdiction(self)


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

    The jurisdiction fields tell the interface which
    district or province the signed-in officer is
    responsible for, so it can show them what their account
    actually covers.

    They are for DISPLAY ONLY. Access is enforced on the
    server, in the repository layer, against the same fields
    read from the database. Nothing the interface does with
    these values can widen what an officer is able to
    retrieve.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    role: UserRole

    is_active: bool

    must_change_password: bool

    last_login: datetime | None

    province_id: int | None = None

    district_id: int | None = None

    province_name: str | None = None

    district_name: str | None = None

    created_at: datetime

    updated_at: datetime

    @classmethod
    def from_user(cls, user) -> "UserResponse":
        """
        Build a response, resolving jurisdiction names.

        Args:
            user:
                User record, with its district and province
                relationships available.

        Returns:
            The populated response.

        Identifiers alone are not useful in an interface. An
        officer needs to see "Kitwe", not district 10, so
        the names are resolved here rather than making the
        interface fetch every district to translate one
        number.
        """

        district = getattr(user, "district", None)

        province = getattr(user, "province", None)

        # -------------------------------------------------
        # A district officer's province is implied by their
        # district, so fall back to it when the province is
        # not set directly on the account.
        # -------------------------------------------------

        if province is None and district is not None:
            province = getattr(district, "province", None)

        response = cls.model_validate(user)

        response.district_name = (
            district.name
            if district is not None
            else None
        )

        response.province_name = (
            province.name
            if province is not None
            else None
        )

        if response.province_id is None and province is not None:
            response.province_id = province.id

        return response


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