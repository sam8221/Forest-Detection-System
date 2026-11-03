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

import hashlib
import hmac
import secrets
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
# Temporary Passwords
# =========================================================

# The alphabet a generated password is drawn from.
#
# Characters that are read back wrongly over a phone call or
# copied off a screen are left out: no O or 0, no I, l or 1.
# An administrator has to pass this password to an officer by
# some channel outside the system, and a character pair that
# cannot be told apart turns a reset into a second support
# call.
TEMPORARY_PASSWORD_UPPERCASE = "ABCDEFGHJKLMNPQRSTUVWXYZ"
TEMPORARY_PASSWORD_LOWERCASE = "abcdefghijkmnopqrstuvwxyz"
TEMPORARY_PASSWORD_DIGITS = "23456789"

# Punctuation that survives being pasted into a form and
# typed on a phone keypad. Quotes, backslashes and angle
# brackets are left out because they are the characters most
# often mangled in transit.
TEMPORARY_PASSWORD_SYMBOLS = "!#$%&*+-=?@"

TEMPORARY_PASSWORD_ALPHABET = (
    TEMPORARY_PASSWORD_UPPERCASE
    + TEMPORARY_PASSWORD_LOWERCASE
    + TEMPORARY_PASSWORD_DIGITS
    + TEMPORARY_PASSWORD_SYMBOLS
)

# Sixteen characters from an alphabet of 67 is roughly 97
# bits of entropy, which is far beyond what a password
# expected to live for one sign-in needs. It costs nothing:
# the officer copies it rather than remembering it.
TEMPORARY_PASSWORD_LENGTH = 16


def generate_temporary_password(
    length: int = TEMPORARY_PASSWORD_LENGTH,
) -> str:
    """
    Generate a random temporary password.

    Drawn from secrets, which reads the operating system's
    cryptographic random source. random is deliberately not
    used: it is a Mersenne Twister seeded predictably enough
    that observing a few outputs reveals the rest, which for
    a password generator means an attacker who has seen one
    reset can anticipate the next.

    One character of each required class is placed first and
    the remainder drawn freely, then the whole thing is
    shuffled, so the result always satisfies the password
    policy without the class positions being predictable.

    Args:
        length:
            Characters to generate. Must leave room for one
            of each required class.

    Returns:
        str: A password satisfying validate_password_strength.

    Raises:
        ValueError: The requested length is too short.
    """

    if length < 8:
        raise ValueError(
            "A temporary password must be at least 8 "
            "characters."
        )

    characters = [
        secrets.choice(TEMPORARY_PASSWORD_UPPERCASE),
        secrets.choice(TEMPORARY_PASSWORD_LOWERCASE),
        secrets.choice(TEMPORARY_PASSWORD_DIGITS),
        secrets.choice(TEMPORARY_PASSWORD_SYMBOLS),
    ]

    characters.extend(
        secrets.choice(TEMPORARY_PASSWORD_ALPHABET)
        for _ in range(length - len(characters))
    )

    # Fisher-Yates, driven by secrets rather than
    # random.shuffle, so the ordering is as unpredictable as
    # the characters themselves.
    for position in range(len(characters) - 1, 0, -1):
        swap = secrets.randbelow(position + 1)

        characters[position], characters[swap] = (
            characters[swap],
            characters[position],
        )

    return "".join(characters)


# =========================================================
# Session Binding
# =========================================================

def password_fingerprint(password_hash: str) -> str:
    """
    Derive a token claim that changes with the password.

    Tokens in this system are stateless: there is no server
    side record of an issued token, so there is nothing to
    delete when an account's password is reset. Without
    something tying a token to the password it was issued
    under, a token handed out before a reset keeps working
    until it expires, and a reset performed because an
    account was compromised leaves the intruder signed in
    for up to an hour.

    Carrying this in the token closes that without a table
    of sessions to store, expire and clean up. The claim is
    checked on each request against the account's current
    password hash; the moment the hash changes, every token
    issued under the previous one stops verifying.

    The bcrypt hash itself is never placed in the token. A
    JWT payload is base64, not encrypted, so anyone holding
    the token could read it. An HMAC under the application
    secret gives a value that changes with the password but
    discloses nothing about it, and cannot be produced by
    anyone without the secret.

    Args:
        password_hash:
            The account's stored bcrypt hash.

    Returns:
        str: A short, stable fingerprint of that hash.
    """

    digest = hmac.new(
        SECRET_KEY.encode("utf-8"),
        password_hash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    # Truncated to keep the token small. Sixteen hex
    # characters is 64 bits, which is far more than is
    # needed to tell one password hash from another and is
    # not a secret an attacker can work backwards from.
    return digest[:16]


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