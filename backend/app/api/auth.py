"""
ForestWatch Zambia

Module: Authentication API

Purpose:
Provides authentication endpoints.

Responsibilities:
- User login
- Current user information
- Password management

Author:
Samuel Bikiloni

Project:
Web-Based Deforestation Detection and Alert System
Using Sentinel-2 Imagery in the Copperbelt, Zambia
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.database.session import get_db
from app.models.user import User
from app.schemas.user import (
    ChangePasswordRequest,
    Token,
    UserResponse,
)
from app.services.auth_service import AuthService


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# =========================================================
# LOGIN
# =========================================================

@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate a user using OAuth2 password form data
    and return a JWT access token.

    Swagger/OpenAPI sends:

        username = user's email
        password = user's password
    """

    auth_service = AuthService(db)

    try:
        return auth_service.login(
            email=form_data.username,
            password=form_data.password,
        )

    except ValueError as ex:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(ex),
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )


# =========================================================
# CURRENT USER
# =========================================================

@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def get_current_user(
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Return the currently authenticated active user.

    The user's identity comes from the JWT access token.
    """

    return current_user


# =========================================================
# CHANGE PASSWORD
# =========================================================

@router.post(
    "/change-password",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(
        get_current_active_user
    ),
    db: Session = Depends(get_db),
):
    """
    Change the password of the authenticated user.

    The user's identity comes from the JWT access token.
    """

    auth_service = AuthService(db)

    try:
        return auth_service.change_password(
            email=current_user.email,
            password_data=request,
        )

    except ValueError as ex:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )