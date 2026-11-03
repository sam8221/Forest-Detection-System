"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Users API

Purpose:
    Provides endpoints for managing system users.

Responsibilities:
    - List users
    - Retrieve user details
    - Create users
    - Update users
    - Activate and deactivate users
    - Retrieve current user profile
    - Change current user password

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    get_admin_user,
    get_current_active_user,
    get_user_pending_password_change,
)
from app.database.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    TemporaryPasswordResponse,
    ChangePasswordRequest,
    SmsSettingsResponse,
    SmsSettingsUpdate,
    SmsTestResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services.auth_service import AuthService
from app.services.sms_registration import (
    SmsRegistrationError,
    send_registration_test_sms,
    sms_settings_for,
    update_sms_settings,
)


# ---------------------------------------------------------
# Router
# ---------------------------------------------------------

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)


# =========================================================
# CURRENT USER PROFILE
# =========================================================
# IMPORTANT:
# This route is BEFORE /{user_id}
# =========================================================

@router.get(
    "/profile",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def get_profile(
    current_user: User = Depends(
        get_user_pending_password_change
    ),
):
    """
    Return the currently authenticated user's profile.

    Reachable while a password change is outstanding, so the
    interface can identify the officer it is asking to set a
    new password.
    """

    return current_user


# =========================================================
# OWN SMS NOTIFICATION SETTINGS
#
# An officer manages their own number and preference. These
# three routes are deliberately scoped to the signed-in
# account: the subject is always current_user, never an id
# taken from the request, so no officer can register a
# number against someone else's account or send a message to
# a number its holder never agreed to.
#
# Changing another officer's number remains an administrator
# action through PUT /users/{user_id}.
# =========================================================

@router.get(
    "/profile/sms",
    response_model=SmsSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def get_sms_settings(
    current_user: User = Depends(get_current_active_user),
):
    """Return the signed-in officer's SMS notification settings."""

    return sms_settings_for(current_user)


@router.put(
    "/profile/sms",
    response_model=SmsSettingsResponse,
    status_code=status.HTTP_200_OK,
)
def update_own_sms_settings(
    changes: SmsSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Save the signed-in officer's number or preference.

    The number is validated and normalised to E.164 by the
    request schema, so an invalid number is refused with 422
    before it reaches the database and no malformed value is
    ever stored.
    """

    try:
        user = update_sms_settings(
            db=db,
            user=current_user,
            changes=changes,
        )

    except SmsRegistrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return sms_settings_for(user)


@router.post(
    "/profile/sms/test",
    response_model=SmsTestResponse,
    status_code=status.HTTP_200_OK,
)
def send_own_test_sms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Send the welcome message to the officer's saved number.

    Only ever sent because this was called: nothing else in
    the system sends this message.

    A 200 means the provider accepted the submission, which
    is not the same as delivery. The response says so, and
    the interface must not report delivery, because this
    system receives no delivery reports.
    """

    try:
        return send_registration_test_sms(
            db=db,
            user=current_user,
        )

    except SmsRegistrationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# =========================================================
# CHANGE CURRENT USER PASSWORD
# =========================================================

@router.put(
    "/profile/password",
    status_code=status.HTTP_200_OK,
)
def change_password(
    password_data: ChangePasswordRequest,
    current_user: User = Depends(
        get_user_pending_password_change
    ),
    db: Session = Depends(get_db),
):
    """
    Change the password of the currently
    authenticated user.

    Reachable while a password change is outstanding: this
    is the endpoint that clears it.

    The current password must be correct
    before the new password is saved.
    """

    auth_service = AuthService(db)

    try:
        auth_service.change_password(
            email=current_user.email,
            password_data=password_data,
        )

        return {
            "message": "Password changed successfully."
        }

    except ValueError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )


# =========================================================
# GET ALL USERS
# =========================================================

@router.get(
    "",
    response_model=list[UserResponse],
    status_code=status.HTTP_200_OK,
)
def get_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Return all registered users.

    Only Administrators can access this endpoint.
    """

    repository = UserRepository(db)

    return repository.get_all()


# =========================================================
# GET USER BY ID
# =========================================================

@router.get(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Retrieve a user by ID.

    Only Administrators can access this endpoint.
    """

    repository = UserRepository(db)

    user = repository.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user


# =========================================================
# CREATE USER
# =========================================================

@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    user_data: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Create a new user.

    The optional phone_number is validated and normalised by
    UserCreate before it reaches the authentication service.

    Only Administrators can create users.
    """

    auth_service = AuthService(db)

    try:
        return auth_service.register_user(
            user_data
        )

    except ValueError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )


# =========================================================
# UPDATE USER
# =========================================================

@router.put(
    "/{user_id}",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Update an existing user.

    Administrators may set phone_number to a valid Zambian
    mobile number or null to clear it. The request schema
    normalises and validates supplied values.

    Only Administrators can update users.
    """

    auth_service = AuthService(db)

    try:
        return auth_service.update_user(
            user_id=user_id,
            user_data=user_data,
        )

    except ValueError as ex:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ex),
        )


# =========================================================
# ACTIVATE USER
# =========================================================
# Withdrawing and restoring access are separate, named
# actions rather than a field on the update endpoint, so
# that each one is a deliberate request and can be recorded
# as its own entry in the audit trail.
# =========================================================

@router.post(
    "/{user_id}/activate",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def activate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_admin_user),
):
    """
    Restore a deactivated account.

    The officer can sign in again and sees the records of
    the jurisdiction still assigned to their account.

    Only Administrators can activate users.
    """

    auth_service = AuthService(db)

    try:
        return auth_service.set_account_active(
            user_id=user_id,
            is_active=True,
            performed_by=current_admin,
        )

    except ValueError as ex:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ex),
        )


# =========================================================
# RESET A USER'S PASSWORD
# =========================================================

@router.post(
    "/{user_id}/reset-password",
    response_model=TemporaryPasswordResponse,
    status_code=status.HTTP_200_OK,
)
def reset_user_password(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_admin_user),
):
    """
    Issue a generated temporary password for an account.

    For an officer who cannot sign in. The administrator
    does not choose the password and cannot supply one: the
    system generates it from a cryptographic random source.
    A password an administrator chooses tends to follow a
    pattern across accounts, and one they remember is one
    they can go on using.

    The generated password is returned here, once, because
    the administrator has to pass it to the officer by
    telephone or in person. It is never stored in this form
    and never appears in a log or in the audit trail; the
    database holds only the bcrypt hash.

    Three things follow from the reset, and together they
    make it a handover rather than a shared credential:

        Every token issued under the previous password stops
        working immediately, so a session already open on
        the account ends. This matters when the reason for
        the reset is that the account may be in someone
        else's hands.

        The account must set a new password before it can do
        anything else, which is refused on the server rather
        than merely prompted for in the interface.

        Once that new password is set, this temporary one no
        longer authenticates: the stored hash has been
        replaced.

    An audit entry naming the administrator, the officer and
    the time is written as FR-19 requires. The password is
    not part of it.

    Only Administrators can reset passwords.
    """

    repository = UserRepository(db)

    user = repository.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    auth_service = AuthService(db)

    temporary_password = auth_service.reset_password(
        user=user,
        performed_by=current_admin,
    )

    return TemporaryPasswordResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        temporary_password=temporary_password,
        must_change_password=user.must_change_password,
    )


# =========================================================
# DEACTIVATE USER
# =========================================================

@router.post(
    "/{user_id}/deactivate",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def deactivate_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_admin_user),
):
    """
    Withdraw an account's access.

    The account is kept rather than deleted, because the
    detections it verified and the alerts it acted on stay
    attributed to it.

    Refused when it would leave nobody able to administer
    the system.

    Only Administrators can deactivate users.
    """

    auth_service = AuthService(db)

    try:
        return auth_service.set_account_active(
            user_id=user_id,
            is_active=False,
            performed_by=current_admin,
        )

    except ValueError as ex:

        # "User not found" is a missing record; the other
        # refusals are requests the administrator is not
        # permitted to make, which is a different answer.
        is_missing = "not found" in str(ex).lower()

        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
                if is_missing
                else status.HTTP_409_CONFLICT
            ),
            detail=str(ex),
        )
