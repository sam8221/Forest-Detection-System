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
from app.services.sms_service import normalise_msisdn


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


def normalize_optional_phone_number(
    value: str | None,
) -> str | None:
    """Return a normalized Zambian number or preserve a blank as NULL."""

    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(
            "Phone number must be entered as text."
        )

    if not value.strip():
        return None

    normalized = normalise_msisdn(value)

    if normalized is None:
        raise ValueError(
            "Enter a valid Zambian mobile number, such as "
            "+260971234567."
        )

    return normalized


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

    phone_number: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "Optional Zambian mobile number. Valid numbers "
            "are stored in E.164 form."
        ),
    )

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        """Normalise an optional Zambian mobile number."""

        return normalize_optional_phone_number(value)


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

    phone_number: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "Optional Zambian mobile number. Null clears the "
            "saved number; valid numbers are stored in E.164."
        ),
    )

    role: UserRole | None = None

    is_active: bool | None = None

    province_id: int | None = None

    district_id: int | None = None

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        """Normalise a supplied number and allow explicit clearing."""

        return normalize_optional_phone_number(value)

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
# TEMPORARY PASSWORD SCHEMA
# =========================================================

class TemporaryPasswordResponse(BaseModel):
    """
    The result of an administrator resetting a password.

    The only place in this system where a password is
    returned in plain text. It is returned once, to the
    administrator who asked for the reset, because they have
    to pass it to the officer by some channel outside the
    system. It is not stored anywhere in this form: what the
    database holds is the bcrypt hash.

    The account fields are echoed back so the interface can
    name the officer the password belongs to. An
    administrator resetting several accounts in a row should
    not have to trust that the dialog in front of them
    refers to the row they clicked.
    """

    user_id: int

    email: EmailStr

    full_name: str

    temporary_password: str = Field(
        ...,
        description=(
            "The generated password, in plain text. Shown "
            "once and never returned again."
        ),
    )

    must_change_password: bool = Field(
        default=True,
        description=(
            "Always true. The officer is required to "
            "replace this password at their next sign-in."
        ),
    )


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


# =========================================================
# SMS NOTIFICATION SETTINGS
#
# An officer's own SMS settings, which they may change
# without an administrator. Registering a number is how an
# officer asks to be told about clearing in their own
# district, so making it depend on an administrator would
# leave the channel unused.
#
# Deliberately a small schema of its own rather than a reuse
# of UserUpdate: UserUpdate can change role, jurisdiction and
# active state, and must stay administrator-only. An officer
# editing their own notification settings may change these
# two fields and nothing else.
# =========================================================

class SmsSettingsUpdate(BaseModel):
    """What an officer may change about their own SMS alerts."""

    phone_number: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "Zambian mobile number. Accepts 0977123456, "
            "+260977123456, 260977123456 and 00260977123456, "
            "and is stored in E.164 form. An empty value "
            "clears the saved number."
        ),
    )

    sms_notifications_enabled: bool | None = Field(
        default=None,
        description=(
            "Whether to receive automatic deforestation "
            "alert SMS. Omitted leaves the setting unchanged."
        ),
    )

    @field_validator("phone_number", mode="before")
    @classmethod
    def validate_phone_number(cls, value: str | None) -> str | None:
        """Normalise the number and allow explicit clearing."""

        return normalize_optional_phone_number(value)


class SmsSettingsResponse(BaseModel):
    """The officer's SMS settings as they now stand."""

    phone_number: str | None = Field(
        default=None,
        description="Saved number in E.164 form, or null.",
    )

    sms_notifications_enabled: bool = Field(
        description=(
            "Whether automatic alert SMS are enabled. True "
            "while the preference column is absent, which "
            "is the behaviour that preceded it."
        ),
    )

    preference_supported: bool = Field(
        description=(
            "False until migration d9f4a7c1e835 is applied. "
            "The interface uses this to explain why the "
            "switch cannot be changed yet, rather than "
            "offering a control that silently does nothing."
        ),
    )

    automatic_sending_enabled: bool = Field(
        description=(
            "Whether the system would actually send an "
            "alert now. True only when SMS is switched on "
            "and the provider has accepted the configured "
            "credentials. A key being present in the "
            "configuration is not enough: an invalid key "
            "would otherwise show the channel as ready "
            "while every message was refused."
        ),
    )

    system_status: str = Field(
        description=(
            "Why the system can or cannot send: ACTIVE, "
            "DISABLED, MISSING_CREDENTIALS, "
            "INVALID_CREDENTIALS or PROVIDER_ERROR. The "
            "interface states these apart because the "
            "remedy differs: a disabled switch and a "
            "rejected key are both 'no SMS' but are fixed "
            "by different people doing different things."
        ),
    )

    system_detail: str | None = Field(
        default=None,
        description=(
            "One sentence explaining the status. Built from "
            "the provider's own words where it gave any, "
            "and never contains a credential."
        ),
    )

    model_config = ConfigDict(
        from_attributes=True,
    )


class SmsTestResponse(BaseModel):
    """The outcome of a test message the officer asked for."""

    submitted: bool = Field(
        description=(
            "Whether the provider accepted the message. "
            "Acceptance is not delivery: this system "
            "receives no delivery reports, so a true value "
            "must never be presented as 'delivered'."
        ),
    )

    status: str = Field(
        description="Recorded status, SUBMITTED or FAILED.",
    )

    detail: str | None = Field(
        default=None,
        description="Why the message failed, when it did.",
    )

    recipient_phone: str | None = Field(
        default=None,
        description="Number the message was addressed to.",
    )

    recorded: bool = Field(
        description=(
            "Whether the attempt was written to sms_queue. "
            "False until migration d9f4a7c1e835 makes "
            "sms_queue.alert_id nullable, because a test "
            "message belongs to no alert."
        ),
    )
