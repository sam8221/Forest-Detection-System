"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
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

from app.database.session import get_db
from app.schemas.user import (
    ChangePasswordRequest,
    Token,
    UserLogin,
    UserResponse,
)

from app.services.auth_service import AuthService

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
)
def login(
    request: UserLogin,
    db: Session = Depends(get_db),
):
    """
    Authenticate a user and return a JWT access token.
    """

    auth_service = AuthService(db)

    try:
        return auth_service.login(
            email=request.email,
            password=request.password,
        )

    except ValueError as ex:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(ex),
        )
    @router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
     )
    def get_current_user(
    email: str,
    db: Session = Depends(get_db),
     ):
     """
    Return the currently authenticated user.

    NOTE:
    The email will later come from the JWT token.
    """

    auth_service = AuthService(db)

    user = auth_service.get_user_by_email(
        email=email,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    return user
@router.post(
    "/change-password",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
def change_password(
    email: str,
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
):
    """
    Change the password of the authenticated user.

    NOTE:
    The email will later come from the JWT token.
    """

    auth_service = AuthService(db)

    try:

        return auth_service.change_password(
            email=email,
            password_data=request,
        )

    except ValueError as ex:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ex),
        )