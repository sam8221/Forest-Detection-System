"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Satellite Images API

Purpose:
    Provides endpoints for searching, downloading and
    managing Sentinel-2 satellite images.

Responsibilities:
    - Search real Sentinel-2 imagery from Copernicus.
    - Download selected Sentinel-2 products.
    - Register downloaded satellite images.
    - Retrieve satellite images.
    - Retrieve images by forest area.
    - Retrieve latest image.
    - Mark images as processed.
    - Delete satellite images.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.2.0
===========================================================
"""

import logging
import time
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)

from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError

from geoalchemy2.shape import to_shape

from sqlalchemy.orm import Session

from app.api.deps import (
    get_admin_user,
    get_current_active_user,
)

from app.database.session import SessionLocal, get_db

from app.models.forest_area import ForestArea
from app.models.satellite_download_job import SatelliteDownloadJob
from app.models.user import User

from app.repositories.forest_area_repository import (
    ForestAreaRepository,
)

from app.repositories.satellite_image_repository import (
    SatelliteImageRepository,
)

from app.schemas.satellite_image import (
    SatelliteImageCreate,
    SatelliteImageAnalysisResponse,
    SatelliteImageResponse,
)
from app.schemas.satellite_download import SatelliteDownloadJobResponse

from app.services.copernicus_service import (
    CopernicusAuthenticationError,
    CopernicusAuthenticationServiceError,
    CopernicusAuthorizationError,
    CopernicusService,
)

from app.services.sentinel_service import (
    SentinelService,
)
from app.services.analysis_service import AnalysisService
from app.services.satellite_image_selection_service import (
    SatelliteImageSelectionService,
)
from app.services.satellite_download_job_service import (
    SatelliteDownloadJobService,
)


router = APIRouter(
    prefix="/satellite-images",
    tags=["Satellite Images"],
)

logger = logging.getLogger(__name__)


def _satellite_download_failure_message(exc: Exception) -> str:
    """Return a safe user-facing message for a failed acquisition."""

    if isinstance(
        exc,
        (
            CopernicusAuthenticationError,
            CopernicusAuthenticationServiceError,
            CopernicusAuthorizationError,
        ),
    ):
        return str(exc)
    return (
        "The download failed or the product did not pass validation. "
        "Retry the acquisition."
    )


def _raise_if_download_job_table_missing(exc: SQLAlchemyError, db: Session) -> None:
    """Translate an unapplied download-job migration into a safe 503."""

    original = getattr(exc, "orig", None)
    sqlstate = (
        getattr(original, "sqlstate", None)
        or getattr(original, "pgcode", None)
    )
    message = str(original or exc).lower()
    missing_table = (
        sqlstate == "42P01"
        or "no such table: satellite_download_jobs" in message
        or 'relation "satellite_download_jobs" does not exist' in message
    )
    if not missing_table:
        raise exc

    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Satellite download tracking is unavailable because its database "
            "migration has not been applied. Apply the pending Alembic migrations "
            "from the backend directory."
        ),
    ) from exc


def _execute_satellite_download_job(
    job_id: str,
    forest_area_id: int,
    download_request: dict,
) -> None:
    """Run a queued Copernicus transfer with an independent DB session."""

    db = SessionLocal()
    job_service = SatelliteDownloadJobService(db)

    try:
        job = db.get(SatelliteDownloadJob, job_id)
        if job is None:
            return

        forest = (
            db.query(ForestArea)
            .filter(ForestArea.id == forest_area_id)
            .first()
        )
        if forest is None:
            raise RuntimeError("The forest area is no longer available.")

        last_persisted_at = 0.0
        last_integer_percentage: int | None = None

        def report_progress(
            progress_status: str,
            downloaded_bytes: int,
            total_bytes: int | None,
        ) -> None:
            nonlocal last_persisted_at, last_integer_percentage

            percentage = None
            if total_bytes is not None and total_bytes > 0:
                percentage = min(
                    99.9,
                    max(0.0, downloaded_bytes / total_bytes * 100),
                )

            now = time.monotonic()
            current_integer_percentage = (
                int(percentage) if percentage is not None else None
            )
            should_persist = (
                progress_status != "DOWNLOADING"
                or current_integer_percentage != last_integer_percentage
                or now - last_persisted_at >= 1.0
            )
            if not should_persist:
                return

            # By job id, on its own session. This runs on the
            # transfer threads while the main thread is inside
            # the download holding `db`, and one SQLAlchemy
            # Session cannot be shared that way.
            SatelliteDownloadJobService.record_progress(
                job_id,
                status=progress_status,
                downloaded_bytes=downloaded_bytes,
                total_bytes=total_bytes,
                transfer_complete=progress_status == "VALIDATING",
            )
            last_persisted_at = now
            last_integer_percentage = current_integer_percentage

        image = SentinelService(db).download_product(
            forest_area=forest,
            product_id=download_request["product_id"],
            product_name=download_request["product_name"],
            tile_id=download_request["tile_id"],
            acquisition_date=download_request["acquisition_date"],
            cloud_cover=download_request["cloud_cover"],
            progress_callback=report_progress,
        )

        job_service.complete(job, image.id)
    except Exception as exc:
        # Keep provider details and request internals out of API-visible
        # errors; the class name is enough for server-side diagnosis.
        logger.exception(
            "Satellite download job %s failed (%s)",
            job_id,
            type(exc).__name__,
        )
        try:
            job_service.fail(
                job_id,
                _satellite_download_failure_message(exc),
            )
        except Exception as status_error:
            db.rollback()
            logger.error(
                "Could not save failed status for satellite download job %s (%s)",
                job_id,
                type(status_error).__name__,
            )
    finally:
        db.close()


def _analysis_candidate_responses(images, db):
    """Add filesystem-backed readiness without persisting derived state."""

    analysis_service = AnalysisService(db)
    result = []
    for image in images:
        locally_available = (
            analysis_service._usable_local_image(image.id) is not None
            if image.is_active and image.is_downloaded
            else False
        )
        is_ready, reason = SatelliteImageSelectionService.analysis_readiness(
            image,
            locally_available,
        )
        response = SatelliteImageResponse.model_validate(image).model_dump()
        response["is_ready_for_analysis"] = is_ready
        response["readiness_reason"] = reason
        result.append(response)
    return result


# =========================================================
# DOWNLOAD REQUEST SCHEMA
# =========================================================

class SatelliteDownloadRequest(BaseModel):
    """
    Request data for downloading one Sentinel-2 product.
    """

    product_id: str = Field(
        ...,
        min_length=10,
        max_length=150,
    )

    product_name: str = Field(
        ...,
        min_length=3,
        max_length=255,
    )

    tile_id: str = Field(
        ...,
        min_length=3,
        max_length=20,
    )

    acquisition_date: str

    cloud_cover: float = Field(
        ...,
        ge=0,
        le=100,
    )


# =========================================================
# SEARCH REAL SENTINEL-2 IMAGERY
# =========================================================

@router.get(
    "/forest/{forest_area_id}/search",
)
def search_sentinel_images_for_forest(
    forest_area_id: int,
    start_date: str,
    end_date: str,
    cloud_cover: float = 30.0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Search the real Copernicus Data Space
    catalogue for Sentinel-2 imagery covering
    a specific ForestWatch forest area.
    """

    # -----------------------------------------------------
    # Validate dates
    # -----------------------------------------------------

    try:

        start = datetime.strptime(
            start_date,
            "%Y-%m-%d",
        ).date()

        end = datetime.strptime(
            end_date,
            "%Y-%m-%d",
        ).date()

    except ValueError:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Dates must use YYYY-MM-DD format."
            ),
        )

    if start > end:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "start_date cannot be later "
                "than end_date."
            ),
        )

    # -----------------------------------------------------
    # Validate cloud coverage
    # -----------------------------------------------------

    if cloud_cover < 0 or cloud_cover > 100:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "cloud_cover must be between "
                "0 and 100."
            ),
        )

    # -----------------------------------------------------
    # Validate limit
    # -----------------------------------------------------

    if limit < 1 or limit > 100:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "limit must be between "
                "1 and 100."
            ),
        )

    # -----------------------------------------------------
    # Find forest area
    # -----------------------------------------------------

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id_for_user(
            forest_area_id=forest_area_id,
            user=current_user,
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    # -----------------------------------------------------
    # Check geometry
    # -----------------------------------------------------

    if forest.geometry is None:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "The selected forest area "
                "does not have a valid geometry."
            ),
        )

    # -----------------------------------------------------
    # Convert PostGIS geometry to WKT
    # -----------------------------------------------------

    try:

        geometry_wkt = to_shape(
            forest.geometry
        ).wkt

    except Exception as exc:

        logger.error(
            "Unable to convert forest geometry for Sentinel-2 search (%s).",
            type(exc).__name__,
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Unable to process the selected forest boundary.",
        ) from exc

    # -----------------------------------------------------
    # Search Copernicus
    # -----------------------------------------------------

    copernicus = CopernicusService()

    try:

        products = (
            copernicus.search_products(
                start_date=start_date,
                end_date=end_date,
                cloud_cover=cloud_cover,
                geometry_wkt=geometry_wkt,
                limit=limit,
            )
        )

    except Exception as exc:

        logger.error(
            "Copernicus Sentinel-2 catalogue search failed (%s).",
            type(exc).__name__,
        )

        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "Unable to retrieve Sentinel-2 "
                "imagery from Copernicus."
            ),
        ) from exc

    # -----------------------------------------------------
    # Format results
    # -----------------------------------------------------

    results = []

    for product in products:

        try:

            metadata = (
                copernicus.get_product_metadata(
                    product
                )
            )

        except Exception as exc:

            logger.error(
                "Copernicus Sentinel-2 product metadata lookup failed (%s).",
                type(exc).__name__,
            )

            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Unable to retrieve Sentinel-2 imagery "
                    "from Copernicus."
                ),
            ) from exc

        results.append(
            {
                "product_id": metadata[
                    "product_id"
                ],

                "product_name": metadata[
                    "product_name"
                ],

                "satellite": "Sentinel-2",

                "tile_id": metadata[
                    "tile_id"
                ],

                "acquisition_date": metadata[
                    "acquisition_date"
                ],

                "cloud_cover_percentage": (
                    metadata[
                        "cloud_cover"
                    ]
                ),

                "processing_level": (
                    metadata[
                        "processing_level"
                    ]
                ),

                "online": metadata[
                    "online"
                ],

                "content_length": metadata[
                    "content_length"
                ],

                "footprint": metadata[
                    "geo_footprint"
                ],
            }
        )

    return {
        "forest_area": {
            "id": forest.id,
            "forest_code": (
                forest.forest_code
            ),
            "name": forest.name,
            "area_hectares": (
                forest.area_hectares
            ),
        },

        "search": {
            "start_date": start_date,
            "end_date": end_date,
            "cloud_cover": cloud_cover,
            "limit": limit,
        },

        "count": len(results),

        "products": results,
    }


# =========================================================
# DOWNLOAD REAL SENTINEL-2 PRODUCT
# =========================================================

@router.post(
    "/forest/{forest_area_id}/download",
    response_model=SatelliteDownloadJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def download_sentinel_product(
    forest_area_id: int,
    request: SatelliteDownloadRequest,
    background_tasks: BackgroundTasks,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Queue one Copernicus product download and return its job ID.
    """

    # -----------------------------------------------------
    # Find forest area
    # -----------------------------------------------------

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id_for_user(
            forest_area_id=forest_area_id,
            user=current_user,
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    # -----------------------------------------------------
    # Check duplicate
    # -----------------------------------------------------

    repository = (
        SatelliteImageRepository(db)
    )

    existing = (
        repository.get_by_product_id(
            request.product_id
        )
    )

    # Refused only when the registered product is actually
    # complete. A row whose local files are missing an input the
    # analysis opens must be re-acquirable: it is registered, so
    # the catalogue showed it as acquired, and it was rejected
    # here, so nothing could replace it. An officer had five such
    # products and no way to act on any of them.
    if existing is not None and SentinelService(db).local_product_is_complete(
        existing
    ):

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This Sentinel-2 product "
                "has already been downloaded."
            ),
        )

    # -----------------------------------------------------
    # Validate acquisition date
    # -----------------------------------------------------

    try:

        acquisition_date = datetime.strptime(
            request.acquisition_date[:10],
            "%Y-%m-%d",
        ).date()

    except ValueError:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "acquisition_date must contain "
                "a valid YYYY-MM-DD date."
            ),
        )

    try:
        job, created = SatelliteDownloadJobService(db).create_or_get_active(
            forest_area_id=forest.id,
            product_id=request.product_id,
            product_name=request.product_name,
            started_by=current_user.id,
        )
    except SQLAlchemyError as exc:
        _raise_if_download_job_table_missing(exc, db)

    if created:
        background_tasks.add_task(
            _execute_satellite_download_job,
            job.job_id,
            forest.id,
            {
                "product_id": request.product_id,
                "product_name": request.product_name,
                "tile_id": request.tile_id,
                "acquisition_date": acquisition_date,
                "cloud_cover": request.cloud_cover,
            },
        )
        response.status_code = status.HTTP_202_ACCEPTED
    else:
        response.status_code = status.HTTP_200_OK

    return job


@router.get(
    "/downloads",
    response_model=list[SatelliteDownloadJobResponse],
)
def get_satellite_download_jobs(
    forest_area_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List recent download jobs for an authorised forest area."""

    forest = ForestAreaRepository(db).get_by_id_for_user(
        forest_area_id=forest_area_id,
        user=current_user,
    )
    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    try:
        query = db.query(SatelliteDownloadJob).filter(
            SatelliteDownloadJob.forest_area_id == forest.id
        )
        active_jobs = query.filter(
            SatelliteDownloadJob.status.in_(
                ("PREPARING", "DOWNLOADING", "VALIDATING")
            )
        ).all()
        recent_jobs = query.order_by(
            SatelliteDownloadJob.created_at.desc()
        ).limit(50).all()
    except SQLAlchemyError as exc:
        _raise_if_download_job_table_missing(exc, db)

    # Return each product's newest job and include every active download,
    # even if older concurrent work falls outside the recent history window.
    newest_by_product = {}
    for job in sorted(
        [*active_jobs, *recent_jobs],
        key=lambda item: item.created_at,
        reverse=True,
    ):
        newest_by_product.setdefault(job.product_id, job)
    return list(newest_by_product.values())


@router.get(
    "/downloads/{job_id}",
    response_model=SatelliteDownloadJobResponse,
)
def get_satellite_download_job(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Retrieve one download job after checking forest-area access."""

    try:
        job = db.get(SatelliteDownloadJob, job_id)
    except SQLAlchemyError as exc:
        _raise_if_download_job_table_missing(exc, db)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite download job not found.",
        )

    forest = ForestAreaRepository(db).get_by_id_for_user(
        forest_area_id=job.forest_area_id,
        user=current_user,
    )
    if forest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite download job not found.",
        )

    return job


# =========================================================
# GET ALL IMAGES
# =========================================================

@router.get(
    "",
    response_model=list[SatelliteImageAnalysisResponse],
)
def get_satellite_images(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Return all registered satellite images.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    return _analysis_candidate_responses(
        repository.get_all_for_user(current_user),
        db,
    )


# =========================================================
# GET IMAGES BY FOREST AREA
# =========================================================

@router.get(
    "/forest/{forest_area_id}",
    response_model=list[SatelliteImageAnalysisResponse],
)
def get_images_by_forest_area(
    forest_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Return all downloaded images belonging
    to a forest area.
    """

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id_for_user(
            forest_area_id=forest_area_id,
            user=current_user,
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    repository = (
        SatelliteImageRepository(db)
    )

    return _analysis_candidate_responses(
        repository.get_by_forest_area(forest_area_id),
        db,
    )


# =========================================================
# GET LATEST IMAGE
# =========================================================

@router.get(
    "/forest/{forest_area_id}/latest",
    response_model=SatelliteImageResponse,
)
def get_latest_image(
    forest_area_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Return the newest downloaded satellite
    image for a forest area.
    """

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id_for_user(
            forest_area_id=forest_area_id,
            user=current_user,
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_latest_image(
            forest_area_id
        )
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No satellite images found.",
        )

    return image


# =========================================================
# GET IMAGE BY ID
# =========================================================

@router.get(
    "/{image_id}",
    response_model=SatelliteImageResponse,
)
def get_satellite_image(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Retrieve one registered satellite image.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_by_id_for_user(
            image_id=image_id,
            user=current_user,
        )
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    return image


# =========================================================
# REGISTER SATELLITE IMAGE
# =========================================================

@router.post(
    "",
    response_model=SatelliteImageResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_satellite_image(
    request: SatelliteImageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Register an already downloaded Sentinel-2 image.
    """

    forest_repository = (
        ForestAreaRepository(db)
    )

    forest = (
        forest_repository.get_by_id(
            request.forest_area_id
        )
    )

    if forest is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Forest area not found.",
        )

    repository = (
        SatelliteImageRepository(db)
    )

    existing = (
        repository.get_by_product_id(
            request.product_id
        )
    )

    if existing is not None:

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Satellite image already exists."
            ),
        )

    service = SentinelService(db)

    image = (
        service.register_satellite_image(
            forest_area=forest,
            product_id=request.product_id,
            tile_id=request.tile_id,
            acquisition_date=(
                request.acquisition_date
            ),
            cloud_cover=(
                request.cloud_cover_percentage
            ),
            file_name=request.file_name,
            storage_path=request.storage_path,
            file_size_mb=request.file_size_mb,
        )
    )

    return image


# =========================================================
# MARK IMAGE AS PROCESSED
# =========================================================

@router.put(
    "/{image_id}/processed",
    response_model=SatelliteImageResponse,
)
def mark_image_processed(
    image_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Mark a satellite image as processed.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_by_id_for_user(
            image_id=image_id,
            user=current_user,
        )
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    service = SentinelService(db)

    image = (
        service.mark_as_processed(
            image
        )
    )

    return image


# =========================================================
# DELETE SATELLITE IMAGE
# =========================================================

@router.delete(
    "/{image_id}",
    status_code=status.HTTP_200_OK,
)
def delete_satellite_image(
    image_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(
        get_admin_user
    ),
):
    """
    Permanently delete a satellite image.

    Only administrators can perform this action.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_by_id_for_user(
            image_id=image_id,
            user=current_user,
        )
    )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    repository.delete(image)

    return {
        "message": (
            "Satellite image deleted successfully."
        )
    }


# =========================================================
# GET IMAGE BY PRODUCT ID
# =========================================================

@router.get(
    "/product/{product_id}",
    response_model=SatelliteImageResponse,
)
def get_image_by_product_id(
    product_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_active_user
    ),
):
    """
    Retrieve a satellite image by
    Sentinel product ID.

    Scoped to the officer's jurisdiction. A Sentinel product
    identifier is predictable from the catalogue, so without
    the check this route would answer questions about
    imagery held for districts the officer does not cover,
    whatever the other routes refuse. See FR-04.
    """

    repository = (
        SatelliteImageRepository(db)
    )

    image = (
        repository.get_by_product_id(
            product_id
        )
    )

    # Resolved first, then re-fetched through the scoped
    # lookup: the same 404 covers "no such product" and
    # "not yours", so neither can be told from the other.
    if image is not None:
        image = repository.get_by_id_for_user(
            image_id=image.id,
            user=current_user,
        )

    if image is None:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Satellite image not found.",
        )

    return image
