"""
===========================================================
Forest Detection System
-----------------------------------------------------------
Module: Security

Purpose:
    Provides authentication and security utilities for the
    Forest Detection System.

Responsibilities:
    - Hash user passwords.
    - Verify hashed passwords.
    - Create JWT access tokens.
    - Decode and validate JWT tokens.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from datetime import datetime, timedelta, UTC
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# ---------------------------------------------------------
# Load application settings
# ---------------------------------------------------------
settings = get_settings()

# ---------------------------------------------------------
# Password hashing configuration
#
# bcrypt is the recommended password hashing algorithm.
# Passwords are NEVER stored as plain text.
# ---------------------------------------------------------
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

# ---------------------------------------------------------
# JWT Configuration
# ---------------------------------------------------------
SECRET_KEY = settings.secret_key
ALGORITHM = settings.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.access_token_expire_minutes


# =========================================================
# Password Hashing
# =========================================================
def hash_password(password: str) -> str:
    """
    Hash a plain-text password.

    Args:
        password:
            User password.

    Returns:
        Secure bcrypt hash.
    """
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify that a plain password matches
    its stored hash.

    Args:
        plain_password:
            Password entered by the user.

        hashed_password:
            Password stored in the database.

    Returns:
        True if valid, otherwise False.
    """
    return pwd_context.verify(
        plain_password,
        hashed_password,
    )


# =========================================================
# JWT Token Creation
# =========================================================
def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        data:
            Data to include inside the token.

        expires_delta:
            Optional custom expiration period.

    Returns:
        Encoded JWT token.
    """

    payload = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    payload["exp"] = expire

    return jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


# =========================================================
# JWT Token Validation
# =========================================================
def decode_access_token(token: str) -> dict[str, Any] | None:
    """
    Decode and validate a JWT token.

    Args:
        token:
            JWT access token.

    Returns:
        Token payload if valid,
        otherwise None.
    """

    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        return payload

    except JWTError:
        return None