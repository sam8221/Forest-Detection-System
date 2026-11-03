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

from app.api.deps import (
    get_current_active_user,
    get_user_pending_password_change,
)
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
    Authenticate an officer and issue a JWT access token.

    Args:
        form_data:
            OAuth2 password-form credentials. The
            specification names the identifier field
            "username"; this system identifies officers by
            email address, so the email is carried in that
            field.
        db:
            Database session.

    Returns:
        Token:
            A bearer access token, carried in the
            Authorization header on subsequent requests.

    Raises:
        HTTPException:
            401 when the email is unknown or the password
            does not match.

    Security:
        The submitted password is compared against a stored
        hash, never against a stored password. The database
        holds no recoverable passwords, so a copy of the
        users table does not yield credentials, and the
        comparison is done by the hashing library so that it
        does not return early on the first differing
        character.

        The 401 message is deliberately the same for an
        unknown email and a wrong password. Distinguishing
        them would let an unauthenticated caller confirm
        which email addresses hold accounts, which for this
        system means confirming which officers can see
        detection locations.

    NOTE: A deactivated account is issued a token here,
    because authentication checks only the credentials. Every
    subsequent request is then refused with 403 by
    get_current_active_user, so access is withdrawn in
    practice, but the officer sees a successful sign-in
    followed by errors everywhere rather than being told the
    account is disabled. Rejecting an inactive account at
    this point would state the reason once, plainly.

    NOTE: must_change_password is set when an account is
    provisioned but is not enforced here. An officer is never
    required to replace the password their administrator
    chose, so until they change it voluntarily that
    administrator can sign in as them, and an action in the
    audit trail cannot be attributed to the officer alone.

    A successful sign-in is recorded twice, as FR-19
    requires: User.last_login is updated, and a LOGIN row is
    written to audit_logs with the user and a timestamp. Both
    happen in one transaction inside AuthService.login. A
    failed attempt writes neither, because it raises before a
    token is issued, so the trail records granted access
    rather than refused attempts.
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
        get_user_pending_password_change
    ),
):
    """
    Return the currently authenticated active user.

    Reachable while a password change is outstanding. The
    interface has to be able to say who is signed in before
    it can ask them to set a new password.

    The user's identity comes from the JWT access token.

    The response includes the officer's jurisdiction, with
    the district and province resolved to names, so the
    interface can show what the account covers without
    having to translate identifiers itself.
    """

    return UserResponse.from_user(current_user)


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
        get_user_pending_password_change
    ),
    db: Session = Depends(get_db),
):
    """
    Change the password of the authenticated user.

    Reachable while a password change is outstanding: this
    is the endpoint that clears it. Requiring compliance
    here would leave an account holding a temporary password
    with no way to replace it.

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