"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Security

Purpose:
    Provides authentication and security utilities for the
    ForestWatch Zambia.

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
# Passwords are NEVER stored as plain text, and never
# encrypted either: encryption is reversible, and a key that
# can decrypt the whole users table is a key that can be
# stolen. A hash cannot be reversed at all, so a copy of the
# database yields no credentials.
#
# bcrypt is used rather than a general-purpose hash such as
# SHA-256 for two reasons. It salts each password
# automatically, so two officers who choose the same
# password do not produce the same stored value and a
# precomputed table cannot be used against either. It is
# also deliberately slow, with a tunable work factor, so
# guessing at scale is expensive rather than limited only by
# how fast the hardware can hash.
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
    Hash a plain-text password for storage.

    Args:
        password:
            The password as typed by the officer. Held in
            memory only for the duration of this call and
            never written to the database or to a log.

    Returns:
        str:
            A bcrypt hash containing the algorithm
            identifier, the work factor and the generated
            salt alongside the digest. The salt is part of
            the stored value, so no separate salt column is
            needed and verification can read the parameters
            back from the hash itself.
    """
    return pwd_context.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """
    Verify that a plain password matches its stored hash.

    Args:
        plain_password:
            Password entered at the sign-in form.

        hashed_password:
            The bcrypt hash held against the account.

    Returns:
        bool:
            True when the password matches, otherwise
            False.

    Raises:
        passlib.exc.UnknownHashError:
            The stored value is not a recognisable hash,
            for example an empty string or a password that
            was written to the column unhashed. This
            propagates as a 500 rather than a failed
            sign-in, so a damaged account record presents
            as a server fault. Callers that must tolerate
            such a record should catch it explicitly.

    Security:
        The comparison is performed by bcrypt, which
        re-hashes the submitted password using the salt and
        work factor read from the stored value and compares
        the digests in constant time. It does not return
        early at the first differing byte, so the time taken
        does not reveal how much of a guess was correct.
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