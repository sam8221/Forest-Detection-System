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
    - Delete users

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from app.api.deps import (
    get_admin_user,
    get_current_active_user,
)
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_admin_user
from app.database.session import get_db
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
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


# ---------------------------------------------------------
# Get All Users
# ---------------------------------------------------------
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


# ---------------------------------------------------------
# Get User By ID
# ---------------------------------------------------------
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
    """

    repository = UserRepository(db)

    user = repository.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user


# ---------------------------------------------------------
# Create User
# ---------------------------------------------------------
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
            user_data,
        )

    except ValueError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )


# ---------------------------------------------------------
# Update User
# ---------------------------------------------------------
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
    # ---------------------------------------------------------
# Deactivate User
# ---------------------------------------------------------
@router.delete(
    "/{user_id}",
    status_code=status.HTTP_200_OK,
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    """
    Deactivate a user account.

    Only Administrators can deactivate users.
    """

    repository = UserRepository(db)

    user = repository.get_by_id(user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    user.is_active = False

    repository.update(user)

    return {
        "message": "User account deactivated successfully."
    }
# ---------------------------------------------------------
# Current User Profile
# ---------------------------------------------------------
@router.get(
    "/profile",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def get_profile(
    current_user: User = Depends(
        get_current_active_user,
    ),
):
    """
    Return the currently authenticated user's profile.
    """

    return current_user