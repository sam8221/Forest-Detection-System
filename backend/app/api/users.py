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
)
from app.database.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    ChangePasswordRequest,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services.auth_service import AuthService


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
        get_current_active_user
    ),
):
    """
    Return the currently authenticated user's profile.
    """

    return current_user


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
        get_current_active_user
    ),
    db: Session = Depends(get_db),
):
    """
    Change the password of the currently
    authenticated user.

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