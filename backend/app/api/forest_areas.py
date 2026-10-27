"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Forest Areas API

Purpose:
    Provides REST API endpoints for managing monitored
    forest areas and initiating forest analysis.

Responsibilities:
    - Retrieve active forest areas.
    - Retrieve individual forest areas.
    - Create forest areas.
    - Update forest areas.
    - Deactivate forest areas.
    - Retrieve satellite imagery for forest areas.
    - Initiate deforestation analysis.

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

import logging

from geoalchemy2 import WKTElement

from sqlalchemy import func, select
from sqlalchemy.exc import (
    DatabaseError,
    DataError,
    IntegrityError,
)
from sqlalchemy.orm import Session

from app.api.deps import (
    get_current_active_user,
    get_forestry_officer,
)

from app.database.session import get_db

from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage
from app.models.user import User
from app.repositories.forest_area_repository import (
    ForestAreaRepository,
)

from app.schemas.forest_area import (
    ForestAreaCreate,
    ForestAreaResponse,
    ForestAreaUpdate,
)

from app.schemas.analysis import AnalysisJobResponse

from app.services.analysis_service import AnalysisService


# =========================================================
# ROUTER CONFIGURATION
# =========================================================

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/forest-areas",
    tags=["Forest Areas"],
)


# =========================================================
# RESPONSE BUILDER
# =========================================================

def build_forest_area_response(
    forest: ForestArea,
) -> dict:
    """
    Build a JSON-compatible Forest Area response.

    The helper adds district information from the
    SQLAlchemy relationship so the frontend receives
    both the district identifier and readable district
    information.
    """

    return {
        "id": forest.id,
        "forest_code": forest.forest_code,
        "name": forest.name,
        "district_id": forest.district_id,
        "district_name": (
            forest.district.name
            if forest.district
            else None
        ),
        "district_code": (
            forest.district.code
            if forest.district
            else None
        ),
        "geometry": forest.geometry,
        "protected_status": forest.protected_status,
        "monitoring_frequency": (
            forest.monitoring_frequency
        ),
        "priority_level": forest.priority_level,
        "area_hectares": forest.area_hectares,
        "description": forest.description,
        "created_by": forest.created_by,
        "is_active": forest.is_active,
        "created_at": forest.created_at,
        "updated_at": forest.updated_at,
    }


# =========================================================
# BOUNDARY VALIDATION
# =========================================================

def parse_and_validate_boundary(
    db: Session,
    geometry_wkt: str,
):
    """
    Turn submitted WKT into a PostGIS element, refusing a
    boundary that cannot be read or is not a valid polygon.

    Args:
        db:
            Database session. PostGIS does the parsing and
            the validity test, so a session is needed.
        geometry_wkt:
            Boundary as submitted, expected to be a WKT
            POLYGON in EPSG:4326.

    Returns:
        A WKTElement safe to store.

    Raises:
        HTTPException 422:
            The text is not a geometry PostGIS can read, or
            it is a polygon whose ring is invalid.

    Why both checks happen here rather than at each caller:

        WKTElement does not parse anything. It holds the
        text and defers to ST_GeomFromText, so neither
        malformed text nor a self-intersecting ring is
        caught by constructing it.

        An invalid boundary gives undefined results from
        ST_Contains and ST_Intersects, which is what
        detection clipping and jurisdiction testing are
        built on, so it must never reach the table.

        Create validated the boundary and update did not,
        which meant the check was bypassed simply by
        registering a valid area and then editing it. One
        helper, called from both, is what keeps the two
        paths from drifting apart again.
    """

    try:
        geometry = WKTElement(
            geometry_wkt,
            srid=4326,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "The boundary could not be read as a WKT "
                "polygon. Draw it on the map, or supply it "
                "as POLYGON((lon lat, ...))."
            ),
        ) from exc

    # -----------------------------------------------------
    # Ask PostGIS to read it and judge it
    #
    # Unreadable text raises here rather than returning
    # false, and the failed statement leaves the session in
    # an aborted transaction, so it is rolled back before
    # the error is raised. Without that rollback every later
    # statement on this session fails too, and the officer
    # sees a message about a boundary they have already
    # corrected.
    # -----------------------------------------------------

    try:
        valid, reason = db.execute(
            select(
                func.ST_IsValid(geometry),
                func.ST_IsValidReason(geometry),
            )
        ).one()

    except DatabaseError as exc:
        db.rollback()

        logger.info(
            "Rejected an unreadable boundary: %s",
            geometry_wkt[:120],
        )

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "The boundary could not be read as a WKT "
                "polygon. Draw it on the map, or supply it "
                "as POLYGON((lon lat, ...))."
            ),
        ) from exc

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "The boundary is not a valid polygon: "
                f"{reason}. Redraw it without crossing "
                "its own edges."
            ),
        )

    return geometry


# =========================================================
# GET ALL FOREST AREAS
# =========================================================

@router.get(
    "",
    response_model=list[ForestAreaResponse],
)
def get_forest_areas(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Return the active Forest Areas the officer may see.

    Args:
        db:
            Database session.
        current_user:
            The authenticated officer. Their jurisdiction
            decides which rows the query can return.

    Returns:
        list[ForestAreaResponse]:
            Active forest areas inside the officer's
            district or province, ordered by name. Empty
            when no jurisdiction is assigned.

    The filter is applied in the repository, so an area
    outside the officer's jurisdiction is not returned by
    this endpoint under any request. See FR-04.
    """

    forests = ForestAreaRepository(
        db
    ).get_all_active_for_user(current_user)

    return [
        build_forest_area_response(forest)
        for forest in forests
    ]


# =========================================================
# GET ONE FOREST AREA
# =========================================================

@router.get(
    "/{forest_area_id}",
    response_model=ForestAreaResponse,
)
def get_forest_area(
    forest_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Retrieve one Forest Area the officer may see.

    Args:
        forest_area_id:
            Identifier requested.
        db:
            Database session.
        current_user:
            The authenticated officer.

    Returns:
        ForestAreaResponse:
            The forest area, when it exists inside the
            officer's jurisdiction.

    Raises:
        HTTPException:
            404 when the area does not exist, or lies
            outside the officer's jurisdiction.

    The two cases return the same 404 on purpose. Answering
    403 would confirm that a forest area is registered in a
    district the officer does not cover, which is itself
    information about where the department is watching.

    Requesting the identifier directly is the case FR-04
    exists for, so the jurisdiction filter is part of the
    query rather than a check on the row after loading it.
    """

    forest = ForestAreaRepository(
        db
    ).get_by_id_for_user(
        forest_area_id=forest_area_id,
        user=current_user,
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    return build_forest_area_response(forest)


# =========================================================
# CREATE FOREST AREA
# =========================================================

@router.post(
    "",
    response_model=ForestAreaResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_forest_area(
    forest_data: ForestAreaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Create a new Forest Area.

    The forest boundary is stored in PostGIS as a
    POLYGON using WGS84/SRID 4326.
    """

    data = forest_data.model_dump()

    geometry_wkt = data.pop("geometry")

    geometry = parse_and_validate_boundary(
        db=db,
        geometry_wkt=geometry_wkt,
    )

    forest = ForestArea(
        **data,
        geometry=geometry,
        created_by=current_user.id,
    )

    db.add(forest)

    try:
        db.commit()
        db.refresh(forest)

    except IntegrityError as exc:
        # A constraint the officer can do something about.
        #
        # These were reported as 500 with the raw psycopg
        # message and the INSERT statement attached, which
        # told the officer nothing they could act on and put
        # the schema and SQL in front of the browser. A
        # duplicate forest code is the common case and simply
        # means "choose another code".
        db.rollback()

        constraint = getattr(
            getattr(exc, "orig", None), "diag", None
        )

        name = getattr(constraint, "constraint_name", "") or ""

        if "forest_code" in name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "That forest code is already in use. "
                    "Forest codes identify an area uniquely, "
                    "so please choose a different one."
                ),
            ) from exc

        if "district_id" in name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "That district does not exist. Choose a "
                    "district from the list."
                ),
            ) from exc

        logger.exception(
            "Forest area creation violated a constraint for "
            "user %s",
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The forest area could not be saved because "
                "it conflicts with an existing record."
            ),
        ) from exc

    except DataError as exc:
        # A value the column cannot hold.
        #
        # The schema limits now match the column widths, so
        # this should not be reachable from the registration
        # form. It stays as a safety net: if the two drift
        # apart again, the officer is told which field is
        # wrong instead of being shown the opaque "could not
        # be saved" that sent this bug unreported for weeks.
        db.rollback()

        logger.exception(
            "Forest area creation rejected a field value "
            "for user %s",
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "One of the values is too long or out of "
                "range for the field it is stored in. The "
                "forest code allows up to 20 characters and "
                "the name up to 150."
            ),
        ) from exc

    except Exception as exc:
        db.rollback()

        # Logged in full; the officer is told only that it
        # failed. The previous message returned the database
        # error and the SQL to the browser.
        logger.exception(
            "Forest area creation failed for user %s",
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The forest area could not be saved.",
        ) from exc

    return build_forest_area_response(forest)


# =========================================================
# UPDATE FOREST AREA
# =========================================================

@router.put(
    "/{forest_area_id}",
    response_model=ForestAreaResponse,
    status_code=status.HTTP_200_OK,
)
def update_forest_area(
    forest_area_id: int,
    forest_data: ForestAreaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Update an existing Forest Area.

    Scoped to the officer's jurisdiction, so an officer
    cannot alter the record of a forest area in a district
    they do not cover. FR-04 governs writes as well as
    reads: editing a boundary or a monitoring setting in
    another district would change what that district's
    officers are shown.
    """

    forest = ForestAreaRepository(db).get_by_id_for_user(
        forest_area_id=forest_area_id,
        user=current_user,
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    update_data = forest_data.model_dump(
        exclude_unset=True,
    )

    # -----------------------------------------------------
    # Convert updated WKT geometry to a PostGIS element.
    # -----------------------------------------------------

    # A replacement boundary is held to the same standard as
    # one supplied at registration. It was not before, so a
    # self-intersecting ring that create refused could be
    # stored by registering a valid area and then editing
    # it, which left the validity check on create worth
    # nothing.

    if "geometry" in update_data:

        geometry_wkt = update_data.pop(
            "geometry"
        )

        update_data["geometry"] = (
            parse_and_validate_boundary(
                db=db,
                geometry_wkt=geometry_wkt,
            )
        )

    # -----------------------------------------------------
    # Apply validated field updates.
    # -----------------------------------------------------

    for field, value in update_data.items():
        setattr(
            forest,
            field,
            value,
        )

    try:
        db.commit()
        db.refresh(forest)

    except DataError as exc:
        # A value the column cannot hold, the same class of
        # failure the create path reports. Named here so the
        # officer knows which field to shorten.
        db.rollback()

        logger.exception(
            "Forest area %s update rejected a field value "
            "for user %s",
            forest_area_id,
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "One of the values is too long or out of "
                "range for the field it is stored in. The "
                "name allows up to 150 characters."
            ),
        ) from exc

    except Exception as exc:
        db.rollback()

        # Logged in full; the officer is told only that it
        # failed. This previously returned str(exc), which
        # puts the psycopg message and the UPDATE statement
        # in front of the browser — the schema and the SQL
        # of a restricted system, handed to whoever provoked
        # the error. The create path was corrected for this;
        # update was missed.
        logger.exception(
            "Forest area %s update failed for user %s",
            forest_area_id,
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The forest area could not be updated.",
        ) from exc

    return build_forest_area_response(forest)


# =========================================================
# DEACTIVATE FOREST AREA
# =========================================================

@router.delete(
    "/{forest_area_id}",
    status_code=status.HTTP_200_OK,
)
def delete_forest_area(
    forest_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Deactivate a Forest Area.

    The record is retained in the database so historical
    analysis and detection records remain available.

    Scoped to the officer's jurisdiction, so an officer
    cannot deactivate a forest area in a district they do
    not cover. Deactivation removes the area from the lists
    its own district's officers work from, which is why the
    restriction matters more here than on a read.
    """

    forest = ForestAreaRepository(db).get_by_id_for_user(
        forest_area_id=forest_area_id,
        user=current_user,
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    forest.is_active = False

    try:
        db.commit()

    except Exception as exc:
        db.rollback()

        # Same reasoning as the update path: the database
        # error is logged, not returned.
        logger.exception(
            "Forest area %s deactivation failed for user %s",
            forest_area_id,
            current_user.id,
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "The forest area could not be deactivated."
            ),
        ) from exc

    return {
        "message": (
            "Forest area deactivated successfully."
        )
    }


# =========================================================
# GET SATELLITE IMAGES
# =========================================================

@router.get(
    "/{forest_area_id}/images",
)
def get_satellite_images(
    forest_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Return satellite images associated with a Forest Area.

    Only direct SatelliteImage fields are returned to avoid
    unnecessary relationship loading and PostGIS geometry
    serialization problems.

    Scoped to the officer's jurisdiction. The imagery
    holdings for an area disclose which ground the
    department has acquired coverage of, and over which
    dates, so they are restricted on the same basis as the
    detections drawn from them. See FR-04.
    """

    # -----------------------------------------------------
    # Verify that the Forest Area exists and that this
    # officer covers it.
    # -----------------------------------------------------

    forest = ForestAreaRepository(db).get_by_id_for_user(
        forest_area_id=forest_area_id,
        user=current_user,
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    # -----------------------------------------------------
    # Retrieve satellite images.
    # -----------------------------------------------------

    images = (
        db.query(SatelliteImage)
        .filter(
            SatelliteImage.forest_area_id
            == forest_area_id
        )
        .order_by(
            SatelliteImage.acquisition_date.desc()
        )
        .all()
    )

    # -----------------------------------------------------
    # Convert ORM objects into JSON-safe dictionaries.
    # -----------------------------------------------------

    result = []

    for image in images:

        result.append(
            {
                "id": image.id,
                "forest_area_id": (
                    image.forest_area_id
                ),
                "product_id": image.product_id,
                "tile_id": image.tile_id,
                "satellite_name": (
                    image.satellite_name
                ),
                "acquisition_date": (
                    image.acquisition_date
                ),
                "processing_level": (
                    image.processing_level
                ),
            }
        )

    return result


# =========================================================
# RUN FOREST ANALYSIS
# =========================================================

@router.post(
    "/{forest_area_id}/run-analysis",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_analysis(
    forest_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_forestry_officer),
):
    """
    Start a deforestation analysis job for a Forest Area.
    """

    # -----------------------------------------------------
    # Verify that the Forest Area exists and that this
    # officer covers it.
    #
    # FR-04 restricts reading a detection and ordering the
    # work that produces one alike: without this an officer
    # could commission processing over another district and
    # read the result through the job they submitted.
    # -----------------------------------------------------

    forest = ForestAreaRepository(db).get_by_id_for_user(
        forest_area_id=forest_area_id,
        user=current_user,
    )

    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    # -----------------------------------------------------
    # Initialize the analysis service.
    # -----------------------------------------------------

    service = AnalysisService(db)

    # -----------------------------------------------------
    # Start the forest analysis process.
    # -----------------------------------------------------

    try:

        job = service.run_analysis(
            forest_area_id=forest_area_id,
            started_by=current_user.id,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    except Exception as exc:

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(exc)}",
        )

    return job