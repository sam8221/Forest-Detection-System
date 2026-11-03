"""
ForestWatch Zambia

Module: API Dependencies

Purpose:
Provides reusable authentication dependencies for FastAPI endpoints.

Responsibilities:
- Decode JWT tokens.
- Retrieve authenticated users.
- Enforce role-based access.
- Enforce jurisdiction-scoped access.

Author:
Samuel Bikiloni

Project:
Web-Based Deforestation Detection and Alert System
Using Sentinel-2 Imagery in the Copperbelt, Zambia
"""

import logging

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import password_fingerprint
from app.database.session import get_db
from app.models.district import District
from app.models.enums import UserRole
from app.models.forest_area import ForestArea
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.jurisdiction import is_within_jurisdiction


settings = get_settings()

logger = logging.getLogger(__name__)


# =========================================================
# AUTHENTICATION FAILURE MESSAGES
# =========================================================

# An expired token is told apart from an invalid one.
#
# This gives nothing away. A JWT payload is base64, not
# encrypted, so the holder of the token can already read its
# expiry; saying so reveals nothing they could not work out
# from the token in their own browser. What it buys is an
# officer who is told to sign in again instead of being
# shown a sentence about credentials they did not know they
# had.
#
# Everything else stays deliberately vague. Which part of a
# token failed, and whether an account exists for the
# address inside it, are not the caller's business.
SESSION_EXPIRED_DETAIL = (
    "Your session has expired. Please sign in again."
)

INVALID_CREDENTIALS_DETAIL = "Could not validate credentials."

# Shown when a token was issued under a password that has
# since been changed or reset. Told apart from an expired
# token because the officer's response differs: signing in
# again works, but only with the new password.
PASSWORD_CHANGED_DETAIL = (
    "Your password has changed since you signed in. "
    "Please sign in again."
)

# Shown while an account still holds a temporary password.
PASSWORD_CHANGE_REQUIRED_DETAIL = (
    "A new password must be set before continuing."
)


# =========================================================
# OAuth2 configuration
# =========================================================

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
)

# Same scheme, but does not reject a request that arrives
# without an Authorization header. Used by map imagery,
# which may carry its token as a query parameter instead.
optional_oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login",
    auto_error=False,
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
        detail=INVALID_CREDENTIALS_DETAIL,
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
            logger.warning(
                "Rejected a token carrying no subject."
            )

            raise credentials_exception

    except ExpiredSignatureError:
        # The ordinary end of a session rather than a fault,
        # so it is logged as information. Left at warning it
        # would fill the log with routine events and bury the
        # rejections that do deserve attention.
        logger.info(
            "Rejected an expired token; the officer is "
            "asked to sign in again."
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=SESSION_EXPIRED_DETAIL,
            headers={
                "WWW-Authenticate": "Bearer",
            },
        ) from None

    except JWTError as exc:
        # A token that is malformed, signed with the wrong
        # key or using an unexpected algorithm. Worth a
        # warning: it is not what a working client produces.
        logger.warning(
            "Rejected an invalid token: %s",
            exc,
        )

        raise credentials_exception from exc

    repository = UserRepository(db)

    user = repository.get_by_email(email)

    if user is None:
        # The token verified, so it was issued by this
        # system, but the account it names is gone. The
        # caller is told no more than for any other invalid
        # token; the log records which address it was.
        logger.warning(
            "Rejected a valid token for an account that no "
            "longer exists: %s",
            email,
        )

        raise credentials_exception

    # -----------------------------------------------------
    # The token must have been issued under the password
    # currently in force
    #
    # Tokens are stateless, so a password reset has nothing
    # to delete. Each token instead carries a fingerprint of
    # the password hash it was issued under, and it is
    # checked here. A token issued before a reset therefore
    # stops working the moment the reset happens, rather
    # than lasting out its hour.
    #
    # A token with no fingerprint at all was issued before
    # this check existed. It is refused rather than trusted:
    # accepting it would leave a way to present a token that
    # no reset can revoke.
    # -----------------------------------------------------

    presented = payload.get("pwd")

    if presented != password_fingerprint(user.password_hash):
        logger.info(
            "Rejected a token issued under a previous "
            "password for %s.",
            email,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=PASSWORD_CHANGED_DETAIL,
            headers={
                "WWW-Authenticate": "Bearer",
            },
        )

    return user


# =========================================================
# GET CURRENT ACTIVE USER
# =========================================================

def get_user_pending_password_change(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Ensure the authenticated user is active.

    Deliberately does NOT check whether a password change is
    outstanding, and is therefore used by exactly two
    endpoints: the one that tells an officer who they are,
    and the one that sets a new password. An account holding
    a temporary password has to be able to reach both, or it
    cannot carry out the one action being demanded of it.

    Everything else depends on get_current_active_user
    below, which adds that check.
    """

    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive account.",
        )

    return current_user


# =========================================================
# GET CURRENT ACTIVE USER
# =========================================================

def get_current_active_user(
    current_user: User = Depends(
        get_user_pending_password_change
    ),
) -> User:
    """
    Ensure the user is active and holds a chosen password.

    An administrator who resets a password knows it. Until
    the officer replaces it, that administrator can act as
    them, and nothing in the audit trail distinguishes the
    two. Requiring the change before the account can do
    anything else is what makes a reset a handover rather
    than a shared credential.

    The check lives here, in the dependency the whole API
    already uses, rather than on the role dependencies
    alone. Placed on the role checks it would stop an
    officer registering a forest area while leaving the
    dashboard, the detections and the alerts open to an
    account whose password its administrator knows.

    Enforced on the server rather than in the interface. A
    screen that declines to show the rest of the system is a
    suggestion; a request the server refuses is the control.

    403 rather than 401: the credentials are entirely valid.
    What is missing is a step the officer has to take, and
    signing in again would not help.
    """

    if current_user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=PASSWORD_CHANGE_REQUIRED_DETAIL,
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
    Ensure the user is an Administrator or a Forestry
    Officer of either jurisdiction level.

    This checks the user's ROLE only. It does not check
    whether the record being acted upon falls inside that
    officer's jurisdiction; that is enforced separately by
    require_jurisdiction and by the repository layer.
    """

    if current_user.role not in (
        UserRole.ADMIN,
        UserRole.PROVINCIAL_FORESTRY_OFFICER,
        UserRole.DISTRICT_FORESTRY_OFFICER,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forestry Officer privileges required.",
        )

    return current_user


# =========================================================
# MAP IMAGERY ACCESS
# =========================================================

def get_map_imagery_user(
    access_token: str | None = Query(
        default=None,
        description=(
            "Access token, for map layers that cannot send "
            "an Authorization header."
        ),
    ),
    header_token: str | None = Depends(
        optional_oauth2_scheme
    ),
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate a request for map imagery.

    Accepts the access token either in the Authorization
    header or as a query parameter.

    Why a query parameter is allowed here:

        A map draws imagery by pointing an <img> tag at a
        URL. That request carries no headers the page can
        set, so a tile or image layer cannot authenticate
        the usual way.

        The alternative is leaving imagery unauthenticated,
        which is worse: each request spends Copernicus quota
        from the department's account, and this system is
        not public.

    The trade-off, stated plainly: a token in a URL can be
    recorded in server logs, proxy logs and browser history,
    where a header would not be. It is accepted only on this
    imagery endpoint, never for data. Tokens are short-lived,
    which limits what a recorded one is worth.

    Clients that CAN set headers should, and do: the
    OpenLayers map fetches imagery with the header and hands
    the result to the map as a blob.
    """

    token = header_token or access_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
        )

        email = payload.get("sub")

        if not email:
            raise credentials_exception

    except JWTError as exc:
        raise credentials_exception from exc

    user = UserRepository(db).get_by_email(email)

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive account.",
        )

    return user


# =========================================================
# JURISDICTION OVER A FOREST AREA
# =========================================================

def require_forest_area_jurisdiction(
    forest_area_id: int,
    current_user: User = Depends(
        get_current_active_user
    ),
    db: Session = Depends(get_db),
) -> ForestArea:
    """
    Ensure the user's jurisdiction covers a forest area.

    Args:
        forest_area_id:
            Forest area the request is acting upon. Taken
            from the endpoint path.

    Returns:
        The forest area, so the endpoint does not have to
        load it a second time.

    Raises:
        HTTPException 404:
            The forest area does not exist.

        HTTPException 403:
            The forest area lies outside the user's
            jurisdiction.

    This satisfies requirement FR-04 for endpoints addressed
    by a single record. An officer who requests a record
    outside their district by typing its ID directly is
    refused here, before any data is returned.

    The decision itself lives in
    app.services.jurisdiction.is_within_jurisdiction, which
    is shared with the repository-level filtering applied to
    list endpoints.
    """

    # -----------------------------------------------------
    # Load the forest area and the province containing it
    # -----------------------------------------------------

    result = (
        db.query(ForestArea, District)
        .join(
            District,
            District.id
            == ForestArea.district_id,
        )
        .filter(
            ForestArea.id
            == forest_area_id,
        )
        .first()
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    forest_area, district = result

    # -----------------------------------------------------
    # Apply the jurisdiction rule
    # -----------------------------------------------------

    permitted = is_within_jurisdiction(
        role=current_user.role,

        user_district_id=current_user.district_id,

        user_province_id=current_user.province_id,

        target_district_id=forest_area.district_id,

        target_province_id=district.province_id,
    )

    if not permitted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This forest area is outside your "
                "assigned jurisdiction."
            ),
        )

    return forest_area