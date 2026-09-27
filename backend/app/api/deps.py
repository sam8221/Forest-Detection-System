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

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.models.district import District
from app.models.enums import UserRole
from app.models.forest_area import ForestArea
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.jurisdiction import is_within_jurisdiction


settings = get_settings()


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