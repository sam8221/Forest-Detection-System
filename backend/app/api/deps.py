"""
ForestWatch Zambia

Module: API Dependencies

Purpose:
Provides reusable authentication dependencies for FastAPI endpoints.

Responsibilities:
- Decode JWT tokens.
- Retrieve authenticated users.
- Enforce role-based access.

Author:
Samuel Bikiloni

Project:
Web-Based Deforestation Detection and Alert System
Using Sentinel-2 Imagery in the Copperbelt, Zambia
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository


settings = get_settings()


# =========================================================
# OAuth2 configuration
# =========================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
)


# =========================================================
# GET CURRENT USER
# =========================================================

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Retrieve the authenticated user from the JWT token.
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )

        email: str | None = payload.get("sub")

        if email is None:
            raise credentials_exception

    except JWTError:
        raise credentials_exception

    repository = UserRepository(db)

    user = repository.get_by_email(email)

    if user is None:
        raise credentials_exception

    return user


# =========================================================
# GET CURRENT ACTIVE USER
# =========================================================

def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Ensure the authenticated user is active.
    """

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive account.",
        )

    return current_user


# =========================================================
# ADMIN USER
# =========================================================

def get_admin_user(
    current_user: User = Depends(
        get_current_active_user
    ),
) -> User:
    """
    Ensure the user is an Administrator.
    """

    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required.",
        )

    return current_user


# =========================================================
# FORESTRY OFFICER
# =========================================================

def get_forestry_officer(
    current_user: User = Depends(
        get_current_active_user
    ),
) -> User:
    """
    Ensure the user is either an Administrator
    or a Forestry Officer.
    """

    if current_user.role not in (
        UserRole.ADMIN,
        UserRole.FORESTRY_OFFICER,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forestry Officer privileges required.",
        )

    return current_user