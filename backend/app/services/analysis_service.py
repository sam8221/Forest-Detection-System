"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analysis Service

Purpose:
    Coordinates the complete automated deforestation
    detection workflow using Sentinel-2 imagery.

Workflow:

    Forest Area
        ↓
    Copernicus Sentinel-2 search
        ↓
    Newest suitable image
        ↓
    Download/register if new
        ↓
    Select previous + latest image
        ↓
    NDVI analysis
        ↓
    Vegetation change detection
        ↓
    Deforestation detection
        ↓
    Alert generation
        ↓
    Analysis completed

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    2.0.0
===========================================================
"""

from __future__ import annotations

import errno
import hashlib
import logging
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree import ElementTree
from zipfile import BadZipFile, LargeZipFile, ZipFile

import rasterio
from rasterio.windows import Window

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import is_level_2a
from app.models.analysis_job import AnalysisJob
from app.models.enums import (
    AnalysisJobStatus,
    AnalysisJobType,
)
from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage

from app.services.alert_service import AlertService
from app.services.boundary_comparison_service import (
    BoundaryComparisonService,
    read_matching_manifest,
    validate_stored_forest_boundary,
    write_comparison_manifest,
)
from app.services.cloud_mask_service import CloudMaskService
from app.services.comparison_figure_service import ComparisonFigureService
from app.services.detection_service import DetectionService
from app.services.persistence_service import PersistenceService
from app.services.satellite_image_selection_service import (
    SatelliteImageSelectionService,
)
from app.services.sentinel_processor_service import (
    SentinelProcessorService,
)
from app.services.sentinel_service import SentinelService
from app.services.storage_paths import (
    JOBS_DIRECTORY,
    forest_area_root,
    job_output_root,
    shared_extract_root,
)

logger = logging.getLogger(__name__)


class AnalysisOutputStorageError(RuntimeError):
    """Safe message for failures preparing a job's output storage."""


def public_analysis_error_message(error_message: str | None) -> str | None:
    """Avoid returning absolute local paths in analysis-job API responses."""

    if error_message is None:
        return None
    if re.search(r"\b[A-Za-z]:[\\/]", error_message):
        return (
            "The analysis could not access a required input or output file. "
            "Check the selected products and backend storage, then retry."
        )
    return error_message


class AnalysisService:
    """
    Coordinates the complete Sentinel-2 deforestation
    detection workflow.
    """

    def __init__(
        self,
        db: Session,
    ) -> None:
        """
        Initialize the analysis service.

        Args:
            db:
                Database session, shared with the detection
                and alert services created here so that a
                whole run commits or rolls back together.

        Thresholds are read from application settings rather
        than declared here, so this service and
        DetectionService apply the same minimum detectable
        area and NDVI threshold.
        """

        self.db = db

        self.settings = get_settings()

        self.detection_service = (
            DetectionService(db)
        )

        self.alert_service = (
            AlertService(db)
        )

        self.image_selection_service = (
            SatelliteImageSelectionService(db)
        )

        self.sentinel_service = (
            SentinelService(db)
        )

        # -----------------------------------------------------
        # Raster processing services
        #
        # These turn a downloaded Sentinel-2 ZIP into the
        # cloud-masked NDVI and persistence rasters that
        # DetectionService reads.
        # -----------------------------------------------------

        self.processor_service = (
            SentinelProcessorService()
        )

        self.cloud_mask_service = (
            CloudMaskService()
        )

        self.persistence_service = (
            PersistenceService()
        )

        self.boundary_comparison_service = (
            BoundaryComparisonService()
        )
        self.comparison_figure_service = ComparisonFigureService()

    # =========================================================
    # CREATE ANALYSIS JOB
    # =========================================================

    def default_seasonal_windows(
        self,
    ) -> tuple[date, date, date, date]:
        """
        Return the default baseline and comparison windows.

        Returns:
            baseline_start, baseline_end,
            comparison_start, comparison_end

        The comparison window is the most recent period for
        which imagery is likely to exist. The baseline is the
        SAME calendar window one year earlier.

        Comparing the same months in different years is what
        separates real clearing from the seasonal cycle: in
        miombo woodland NDVI falls province-wide every dry
        season, so a baseline taken from the preceding months
        would report deforestation almost everywhere.
        """

        comparison_end = date.today()

        comparison_start = (
            comparison_end
            - timedelta(
                days=self.settings.image_search_days
            )
        )

        # -----------------------------------------------------
        # Shift both ends back by one year
        #
        # timedelta(days=365) is used rather than replacing
        # the year, because replacing the year fails on
        # 29 February.
        # -----------------------------------------------------

        one_year = timedelta(days=365)

        return (
            comparison_start - one_year,
            comparison_end - one_year,
            comparison_start,
            comparison_end,
        )

    def create_analysis_job(
        self,
        forest_area_id: int,
        satellite_image_id: int,
        started_by: int | None,
        job_type: AnalysisJobType,
        previous_satellite_image_id: int | None = None,
        baseline_start: date | None = None,
        baseline_end: date | None = None,
        comparison_start: date | None = None,
        comparison_end: date | None = None,
    ) -> AnalysisJob:
        """
        Create a new analysis job in the PENDING state.

        Args:
            forest_area_id:
                Forest area to analyse.
            satellite_image_id:
                Product representing the comparison period.
            started_by:
                Officer who requested the run, or None when
                raised by the scheduler rather than a person.
            job_type:
                MANUAL for an officer's request, AUTOMATIC
                for a scheduled run.
            previous_satellite_image_id:
                Product representing the baseline period,
                when a specific one is being compared.
            baseline_start:
                First date of the baseline window.
            baseline_end:
                Last date of the baseline window.
            comparison_start:
                First date of the comparison window.
            comparison_end:
                Last date of the comparison window.

        Returns:
            AnalysisJob:
                The saved job, PENDING until the worker
                picks it up.

        Seasonal windows:
            The four window arguments decide which periods
            are compared, and getting them wrong invalidates
            the result rather than merely degrading it.

            Miombo woodland across the Copperbelt sheds
            leaves every dry season, so NDVI falls over the
            entire province whether or not anything was
            cleared. Comparing adjacent months would
            therefore report deforestation everywhere, and
            the figure would be a measurement of the season
            rather than of clearing.

            The windows must instead be EQUIVALENT SEASONAL
            PERIODS IN DIFFERENT YEARS, for example May to
            July 2024 against May to July 2025, so that both
            observations sit at the same point in the
            growth cycle and the difference between them is
            attributable to change on the ground.

            When the windows are not supplied, equivalent
            windows one year apart are derived from
            default_seasonal_windows, so a caller that omits
            them still gets a seasonally valid comparison
            rather than an adjacent-month one.

            NOTE: Seasonal equivalence is not enforced.
            SeasonalWindowRequest checks that the four dates
            are supplied together, that each window is
            correctly ordered, and that the two do not
            overlap, but not that they cover the same part
            of the year in different years. Baseline
            January to March 2025 against comparison May to
            July 2025 satisfies every current rule, and
            would report the dry-season leaf fall across the
            whole area as deforestation. Comparing the
            month-and-day of the two windows, and requiring
            different years, would make the defence
            structural rather than conventional.
        """

        # -----------------------------------------------------
        # Fill in any window not supplied
        # -----------------------------------------------------

        if None in (
            baseline_start,
            baseline_end,
            comparison_start,
            comparison_end,
        ):

            (
                default_baseline_start,
                default_baseline_end,
                default_comparison_start,
                default_comparison_end,
            ) = self.default_seasonal_windows()

            baseline_start = (
                baseline_start
                or default_baseline_start
            )

            baseline_end = (
                baseline_end
                or default_baseline_end
            )

            comparison_start = (
                comparison_start
                or default_comparison_start
            )

            comparison_end = (
                comparison_end
                or default_comparison_end
            )

        # -----------------------------------------------------
        # Validate the windows
        # -----------------------------------------------------

        if baseline_start > baseline_end:
            raise ValueError(
                "Baseline window start date cannot be "
                "after its end date."
            )

        if comparison_start > comparison_end:
            raise ValueError(
                "Comparison window start date cannot be "
                "after its end date."
            )

        if baseline_end >= comparison_start:
            raise ValueError(
                "The baseline window must end before the "
                "comparison window begins, otherwise the "
                "two periods overlap and the comparison "
                "is not measuring change over time."
            )

        # The Copperbelt's wet/dry cycle changes vegetation
        # seasonally. Compare equivalent calendar windows so
        # normal seasonal leaf loss is not treated as clearing.
        baseline_start_boundary = (
            baseline_start.month,
            baseline_start.day,
        )
        comparison_start_boundary = (
            comparison_start.month,
            comparison_start.day,
        )
        baseline_end_boundary = (
            baseline_end.month,
            baseline_end.day,
        )
        comparison_end_boundary = (
            comparison_end.month,
            comparison_end.day,
        )

        if (
            baseline_start_boundary != comparison_start_boundary
            or baseline_end_boundary != comparison_end_boundary
        ):
            raise ValueError(
                "Baseline and comparison windows must cover the same "
                "calendar season (matching start and end month/day) "
                "in different years."
            )

        if (
            baseline_start.year >= comparison_start.year
            or baseline_end.year >= comparison_end.year
        ):
            raise ValueError(
                "The comparison window must be in a later year than "
                "the baseline window."
            )

        # An explicitly selected observation pair is governed
        # by its real acquisition dates, not the automatic
        # seasonal windows. Validate the pair here as well as
        # at the API boundary so internal callers cannot create
        # an ambiguous job.
        if previous_satellite_image_id is not None:
            previous_image = self.db.get(
                SatelliteImage, previous_satellite_image_id
            )
            recent_image = self.db.get(
                SatelliteImage, satellite_image_id
            )
            if previous_image is None or recent_image is None:
                raise ValueError("The selected Sentinel-2 observation was not found.")
            self.image_selection_service.validate_explicit_pair(
                previous_image, recent_image, forest_area_id
            )
            baseline_start = baseline_end = previous_image.acquisition_date
            comparison_start = comparison_end = recent_image.acquisition_date

        job = AnalysisJob(
            forest_area_id=forest_area_id,

            previous_satellite_image_id=(
                previous_satellite_image_id
            ),

            satellite_image_id=(
                satellite_image_id
            ),

            started_by=started_by,

            job_type=job_type,

            status=AnalysisJobStatus.PENDING,

            ndvi_threshold=(
                self.settings.ndvi_threshold
            ),

            baseline_start=baseline_start,

            baseline_end=baseline_end,

            comparison_start=comparison_start,

            comparison_end=comparison_end,
        )

        self.db.add(job)

        self.db.commit()

        self.db.refresh(job)

        try:
            # Create the job-specific output root before the API
            # reports that background processing has started.
            self.prepare_job_output_directory(job)
            self.db.commit()
        except AnalysisOutputStorageError as exc:
            self.db.rollback()
            failed_job = self.db.get(AnalysisJob, job.id)
            if failed_job is not None:
                self.fail_analysis(failed_job, str(exc))
            raise

        return job

    def prepare_job_output_directory(self, job: AnalysisJob) -> Path:
        """Create and record this job's output root under configured storage."""
        stage = "configured_root"

        def ensure_directory(directory: Path) -> None:
            if directory.exists() and not directory.is_dir():
                raise NotADirectoryError(
                    errno.ENOTDIR,
                    "A file occupies a path where an analysis directory is required.",
                    str(directory),
                )
            directory.mkdir(parents=True, exist_ok=True)
            if not directory.is_dir():
                raise NotADirectoryError(
                    errno.ENOTDIR,
                    "The prepared analysis output path is not a directory.",
                    str(directory),
                )

        try:
            storage_root = Path(
                self.settings.satellite_image_storage_path
            ).expanduser().resolve()
            if storage_root.exists() and not storage_root.is_dir():
                raise NotADirectoryError(
                    "The configured imagery storage root is not a directory."
                )
            ensure_directory(storage_root)

            stage = "job_path"
            area_root = forest_area_root(
                forest_area_id=job.forest_area_id,
                storage_root=storage_root,
            )
            jobs_root = area_root / JOBS_DIRECTORY
            output_root = job_output_root(
                forest_area_id=job.forest_area_id,
                job_id=job.id,
                storage_root=storage_root,
            )
            ensure_directory(area_root)
            ensure_directory(jobs_root)
            ensure_directory(output_root)

            stage = "write_probe"
            # Directory creation alone does not prove that the backend
            # can write there. Create and immediately remove a private
            # probe; this does not create an analysis result.
            with NamedTemporaryFile(
                prefix="forestwatch-write-check-",
                dir=output_root,
            ):
                pass
        except (OSError, ValueError) as exc:
            logger.exception(
                "Could not prepare analysis storage (stage=%s, job_id=%s, forest_area_id=%s)",
                stage,
                job.id,
                job.forest_area_id,
            )
            if stage == "configured_root":
                if isinstance(exc, PermissionError):
                    message = (
                        "The account running the backend cannot write to the configured imagery storage root. "
                        "Grant that account write and delete access, then retry."
                    )
                elif isinstance(exc, (FileExistsError, NotADirectoryError)):
                    message = (
                        "A file occupies the configured imagery storage root path. "
                        "Configure a directory as SATELLITE_IMAGE_STORAGE_ROOT, then retry."
                    )
                else:
                    message = (
                        "The configured imagery storage root is unavailable. "
                        "Set SATELLITE_IMAGE_STORAGE_ROOT to an accessible directory, then retry."
                    )
            elif isinstance(exc, PermissionError):
                message = (
                    "The account running the backend cannot create or write to this analysis job's folder. "
                    "Grant that account write and delete access to the configured imagery storage, then retry."
                )
            elif isinstance(exc, (FileExistsError, NotADirectoryError)):
                message = (
                    "A file occupies a path where this analysis job needs a directory. "
                    "Move the conflicting file aside, then retry."
                )
            elif isinstance(exc, OSError) and (
                exc.errno == errno.ENOSPC or getattr(exc, "winerror", None) == 112
            ):
                message = (
                    "The configured imagery storage volume is out of free space. "
                    "Free disk space, then retry."
                )
            elif stage == "write_probe":
                message = (
                    "The analysis output folder exists, but the backend cannot write to it. "
                    "Grant the backend process write and delete access to the configured storage folder, then retry."
                )
            else:
                message = (
                    "The backend can access the configured storage root but could not create this analysis job's output folder. "
                    "Check folder permissions and available disk space, then retry."
                )
            raise AnalysisOutputStorageError(message) from exc

        job.output_directory = str(output_root)
        return output_root

    # =========================================================
    # START ANALYSIS
    # =========================================================

    def start_analysis(
        self,
        job: AnalysisJob,
    ) -> None:
        """
        Move a job from PENDING to RUNNING.

        Args:
            job:
                The job being started.

        Returns:
            None. The job is updated in place and committed.

        started_at is recorded here so that duration can be
        measured when the job finishes, and so a job left
        RUNNING by a stopped process can be recognised at
        the next startup and closed as FAILED rather than
        appearing to be work still in progress.
        """

        job.status = (
            AnalysisJobStatus.RUNNING
        )

        job.started_at = (
            datetime.now(UTC)
        )

        self.db.commit()

        self.db.refresh(job)

    # =========================================================
    # COMPLETE ANALYSIS
    # =========================================================

    def verify_required_outputs(
        self,
        job: AnalysisJob,
    ) -> None:
        """
        Check a job really produced what a completed run must.

        Args:
            job:
                The job about to be marked COMPLETED.

        Returns:
            None when every required output is present and
            belongs to this job and its selected pair.

        Raises:
            ValueError:
                The job never started, its output directory
                is not the one recorded against it, its
                comparison manifest is absent or belongs to
                another job, pair or boundary, or the figure
                export the manifest names is missing or no
                longer matches its recorded checksum.

        Called by complete_analysis, inside the try block in
        execute, so a missing output FAILS the job with a
        message rather than completing it quietly.
        """

        if job.started_at is None:
            raise ValueError(
                "This analysis was never started, so it cannot be recorded "
                "as completed."
            )

        # Only a selected-pair run writes a comparison
        # manifest. execute always sets both image ids
        # before processing, so a run reaching this point
        # without them did not go through that path.
        if job.previous_satellite_image_id is None:
            return

        forest = (
            self.db.query(ForestArea)
            .filter(ForestArea.id == job.forest_area_id)
            .first()
        )

        if forest is None:
            raise ValueError(
                "The forest area this analysis belongs to is no longer available."
            )

        boundary = validate_stored_forest_boundary(forest.geometry)

        # Same settings the writer used. Letting storage_paths
        # read the configuration again here would allow the
        # writer and this check to resolve different roots.
        root = job_output_root(
            job.forest_area_id,
            job.id,
            storage_root=Path(self.settings.satellite_image_storage_path),
        )
        recorded_root = (
            Path(job.output_directory).resolve()
            if job.output_directory
            else None
        )

        if recorded_root is None or recorded_root != root.resolve():
            raise ValueError(
                "This analysis does not point to its own output directory, so "
                "its results cannot be attributed to it."
            )

        manifest = read_matching_manifest(
            root / "comparison" / "manifest.json",
            forest_area_id=job.forest_area_id,
            job_id=job.id,
            previous_image_id=job.previous_satellite_image_id,
            recent_image_id=job.satellite_image_id,
            boundary=boundary,
        )

        if manifest is None:
            raise ValueError(
                "This analysis did not produce a comparison manifest for its own "
                "forest boundary and selected observation pair."
            )

        figure = manifest.get("figure")
        variant = figure.get("desktop") if isinstance(figure, dict) else None

        if not isinstance(variant, dict):
            raise ValueError(
                "This analysis did not produce its four-panel comparison figure."
            )

        figure_path = root / "comparison" / "scientific_comparison.png"

        if not figure_path.is_file():
            raise ValueError(
                "The four-panel comparison figure recorded for this analysis is "
                "missing from its output directory."
            )

        # The manifest records the checksum the figure was
        # written with. A mismatch means the file on disk is
        # not the one this run produced, so serving it under
        # this job would misattribute the imagery.
        if (
            hashlib.sha256(figure_path.read_bytes()).hexdigest()
            != variant.get("sha256")
        ):
            raise ValueError(
                "The four-panel comparison figure on disk does not match the one "
                "this analysis recorded."
            )

    # =========================================================
    # COMPLETE ANALYSIS
    # =========================================================

    def complete_analysis(
        self,
        job: AnalysisJob,
        cloud_cover: float,
        vegetation_change: float,
        ndvi_threshold: float,
    ) -> None:
        """
        Move a job to COMPLETED and record its results.

        Args:
            job:
                The job being completed.
            cloud_cover:
                Percentage of the scene masked as cloud,
                0.0 to 100.0, recorded so an officer can
                see how much ground was actually observed.
            vegetation_change:
                Confirmed change for the run, in hectares.
            ndvi_threshold:
                The NDVI decline threshold this run applied,
                stored on the job so a past result stays
                interpretable after the configured default
                is changed.

        Returns:
            None. The job is updated in place and committed.

        A job that finishes with ZERO detections is
        COMPLETED, not FAILED. The distinction matters to
        the officer reading it: a completed run found
        nothing and the area is clear as far as the imagery
        shows, whereas a failed run means the question was
        never answered and something needs fixing. Recording
        an empty result as a failure would also remove from
        the record every occasion on which the system looked
        and correctly found nothing, which is the evidence
        the specificity figure rests on.

        A job is NOT completed merely because its rasters and
        figure were written. verify_required_outputs below is
        called first, so a run that produced no manifest, or
        one belonging to a different pair, fails instead of
        presenting itself to the officer as a finished
        analysis. Job 75 reached COMPLETED with no start
        time and no detection step precisely because nothing
        checked, and it was indistinguishable in the jobs
        list from the runs that did the work.
        """

        self.verify_required_outputs(job)

        completed_at = (
            datetime.now(UTC)
        )

        job.completed_at = completed_at

        job.status = (
            AnalysisJobStatus.COMPLETED
        )

        # A job that completes carries no error.
        #
        # The queue worker holds a PostgreSQL advisory lock for
        # the duration of a run. Recovery checks that lock before
        # failing RUNNING rows, so a second API process cannot
        # label this live job abandoned. Clearing a prior error
        # here keeps a successful retry's terminal record clear.
        job.error_message = None

        if job.started_at is not None:

            job.duration_seconds = (
                completed_at
                - job.started_at
            ).total_seconds()

        job.cloud_cover_percentage = (
            cloud_cover
        )

        job.vegetation_change_percentage = (
            vegetation_change
        )

        job.ndvi_threshold = (
            ndvi_threshold
        )

        self.db.commit()

        self.db.refresh(job)

    # =========================================================
    # FAIL ANALYSIS
    # =========================================================

    def fail_analysis(
        self,
        job: AnalysisJob,
        error_message: str,
    ) -> None:
        """
        Move a job to FAILED and record why.

        Args:
            job:
                The job that did not finish.
            error_message:
                Why it stopped. Truncated to 500 characters,
                so a long traceback cannot overflow the
                column and lose the record of the failure
                along with it.

        Returns:
            None. The job is updated in place and committed.

        A failed job is never revived. Resubmitting creates
        a new job, so the failure stays in the record rather
        than being overwritten by the successful retry, and
        the trail shows that the first attempt did not
        answer the question.

        FAILED means the analysis could not be carried out,
        which is different from an analysis that ran and
        found nothing. See complete_analysis.
        """

        completed_at = (
            datetime.now(UTC)
        )

        job.completed_at = completed_at

        job.status = (
            AnalysisJobStatus.FAILED
        )

        job.error_message = (
            str(error_message)[:500]
        )

        if job.started_at is not None:

            job.duration_seconds = (
                completed_at
                - job.started_at
            ).total_seconds()

        self.db.commit()

        self.db.refresh(job)

    # =========================================================
    # AUTOMATIC SENTINEL ACQUISITION
    # =========================================================

    def _usable_local_image(
        self,
        image_id: int | None,
    ) -> SatelliteImage | None:
        """
        Return a named observation if it can be used offline.

        Args:
            image_id:
                Identifier recorded on the job, or None.

        Returns:
            The image when it is active, marked downloaded
            and its product is readable on disk. None
            otherwise, which sends the caller to Copernicus
            instead.

        The archive or extracted SAFE tree is checked for the
        metadata, RGB/NDVI bands and SCL required by this
        analysis. The downloaded flag alone is not evidence
        that a usable local product exists.
        """

        if image_id is None:
            return None

        image = self.db.get(SatelliteImage, image_id)

        if image is None:
            return None

        if (
            not image.is_active
            or not image.is_downloaded
            or not is_level_2a(image.processing_level)
        ):
            return None

        if self._local_product_has_required_files(image):
            return image

        return None

    def _local_archive_path(self, image: SatelliteImage) -> Path | None:
        """Resolve the real local archive, then fall back to configured storage."""

        file_name = Path(image.file_name)
        if not image.file_name or file_name.name != image.file_name:
            return None

        recorded_value = getattr(image, "storage_path", None)
        if recorded_value:
            recorded_path = Path(recorded_value).expanduser()
            if (
                recorded_path.name.casefold() == file_name.name.casefold()
                and recorded_path.is_file()
            ):
                return recorded_path.resolve()

        storage_root = Path(
            self.settings.satellite_image_storage_path
        ).expanduser().resolve()
        return storage_root / str(image.forest_area_id) / file_name

    def _extracted_product_directory(
        self,
        image: SatelliteImage,
    ) -> Path:
        """Return this product's isolated extraction directory."""

        extracted_root = shared_extract_root(
            forest_area_id=image.forest_area_id,
            satellite_image_id=image.id,
            storage_root=Path(
                self.settings.satellite_image_storage_path
            ).expanduser().resolve(),
        )
        product_name = Path(image.file_name).stem
        if not product_name.casefold().endswith(".safe"):
            product_name += ".SAFE"
        return extracted_root / product_name

    @staticmethod
    def _extracted_product_has_required_files(
        product_directory: Path,
    ) -> bool:
        """Check that an extracted SAFE tree contains every required input."""

        if not product_directory.is_dir():
            return False
        metadata = list(product_directory.rglob("MTD_MSIL2A.xml"))
        if not any(path.is_file() and path.stat().st_size > 0 for path in metadata):
            return False
        required_patterns = (
            "*_B02_10m.jp2",
            "*_B03_10m.jp2",
            "*_B04_10m.jp2",
            "*_B08_10m.jp2",
            "*_SCL_20m.jp2",
        )
        for pattern in required_patterns:
            if not any(
                path.is_file() and path.stat().st_size > 0
                for path in product_directory.rglob(pattern)
            ):
                return False
        return True

    @staticmethod
    def _archive_input_members(
        archive_path: Path,
    ) -> dict[str, str] | None:
        """Return required SAFE archive members when its structure is complete."""

        required_suffixes = {
            "metadata": "/MTD_MSIL2A.xml",
            "B02": "_B02_10m.jp2",
            "B03": "_B03_10m.jp2",
            "B04": "_B04_10m.jp2",
            "B08": "_B08_10m.jp2",
            "SCL": "_SCL_20m.jp2",
        }
        try:
            with ZipFile(archive_path) as archive:
                files = [item for item in archive.infolist() if not item.is_dir()]
                members: dict[str, str] = {}
                for label, suffix in required_suffixes.items():
                    match = next(
                        (
                            item
                            for item in files
                            if item.filename.casefold().endswith(suffix.casefold())
                            and item.file_size > 0
                        ),
                        None,
                    )
                    if match is None:
                        return None
                    members[label] = match.filename
                return members
        except (OSError, BadZipFile, LargeZipFile):
            return None

    def _local_product_has_required_files(
        self,
        image: SatelliteImage,
    ) -> bool:
        """Check the configured archive or its exact extracted SAFE tree."""

        file_name = Path(image.file_name)
        if not image.file_name or file_name.name != image.file_name:
            return False
        extracted = self._extracted_product_directory(image)
        if self._extracted_product_has_required_files(extracted):
            return True
        archive_path = self._local_archive_path(image)
        return bool(
            archive_path is not None
            and archive_path.is_file()
            and self._archive_input_members(archive_path) is not None
        )

    @staticmethod
    def _readable_raster_sample(path: str | Path) -> None:
        """Open a required raster and read one real pixel from it."""

        with rasterio.open(path) as raster:
            if raster.width < 1 or raster.height < 1:
                raise ValueError("Raster dimensions must be positive.")
            sample = raster.read(1, window=Window(0, 0, 1, 1))
            if sample.size != 1:
                raise ValueError("Raster did not return a readable sample.")

    def validate_local_image_inputs(self, image: SatelliteImage) -> None:
        """Validate all selected L2A inputs before creating an analysis job."""

        if (
            not image.is_active
            or not image.is_downloaded
            or not is_level_2a(image.processing_level)
        ):
            raise ValueError(
                "The selected observation must be active, downloaded and Sentinel-2 Level-2A."
            )

        extracted = self._extracted_product_directory(image)
        if self._extracted_product_has_required_files(extracted):
            members = {
                "metadata": next(extracted.rglob("MTD_MSIL2A.xml")),
                "B02": self.processor_service.find_band(extracted, "B02"),
                "B03": self.processor_service.find_band(extracted, "B03"),
                "B04": self.processor_service.find_band(extracted, "B04"),
                "B08": self.processor_service.find_band(extracted, "B08"),
                "SCL": self.cloud_mask_service.find_scl_band(extracted),
            }
            if any(
                image.tile_id.casefold() not in Path(members[label]).name.casefold()
                for label in ("B02", "B03", "B04", "B08", "SCL")
            ):
                raise ValueError(
                    "The selected product bands do not match the registered Sentinel-2 tile."
                )
            try:
                ElementTree.parse(members["metadata"])
                for label in ("B02", "B03", "B04", "B08", "SCL"):
                    self._readable_raster_sample(members[label])
                self.processor_service.determine_crs(
                    members["B04"],
                    members["B08"],
                )
            except (OSError, ValueError, ElementTree.ParseError) as exc:
                raise ValueError(
                    "The selected Sentinel-2 product has unreadable bands or invalid Level-2A metadata. Reacquire that product before analysis."
                ) from exc
            return

        archive_path = self._local_archive_path(image)
        members = (
            self._archive_input_members(archive_path)
            if archive_path is not None and archive_path.is_file()
            else None
        )
        if archive_path is None or members is None:
            raise ValueError(
                "The selected Sentinel-2 product is incomplete or missing required bands or Level-2A metadata. Reacquire that product before analysis."
            )
        if any(
            image.tile_id.casefold() not in Path(members[label]).name.casefold()
            for label in ("B02", "B03", "B04", "B08", "SCL")
        ):
            raise ValueError(
                "The selected product bands do not match the registered Sentinel-2 tile."
            )

        try:
            with ZipFile(archive_path) as archive:
                ElementTree.fromstring(archive.read(members["metadata"]))
            raster_paths = {
                label: f"/vsizip/{archive_path.as_posix()}/{member}"
                for label, member in members.items()
                if label != "metadata"
            }
            for label in ("B02", "B03", "B04", "B08", "SCL"):
                self._readable_raster_sample(raster_paths[label])
            # The existing processor uses the MGRS tile name when these
            # JP2 inputs do not declare a CRS. Validate that same fallback
            # directly because pathlib normalizes GDAL's /vsizip/ URI on
            # Windows and cannot safely reopen it through determine_crs.
            self.processor_service.get_crs_from_tile(raster_paths["B04"])
        except (OSError, ValueError, ElementTree.ParseError, BadZipFile) as exc:
            raise ValueError(
                "The selected Sentinel-2 product has unreadable bands or invalid Level-2A metadata. Reacquire that product before analysis."
            ) from exc

    def acquire_latest_satellite_image(
        self,
        forest_area_id: int,
    ):
        """
        Obtain the newest suitable Sentinel-2 product.

        Args:
            forest_area_id:
                Forest area whose boundary defines the area
                searched.

        Returns:
            SatelliteImage:
                The registered product record.

        Raises:
            ValueError:
                The forest area does not exist.
            RuntimeError:
                Copernicus cannot be reached or returns no
                product within the cloud-cover limit.

        A product already held locally is reused rather than
        downloaded again. Level-2A tiles are roughly a
        gigabyte, and processing happens on this server
        rather than a provider's, so re-fetching one would
        cost both the department's quota and the run's time
        for a file already on disk.
        """

        forest = (
            self.db.query(ForestArea)
            .filter(
                ForestArea.id
                == forest_area_id,

                ForestArea.is_active.is_(True),
            )
            .first()
        )

        if forest is None:

            raise ValueError(
                "Forest area not found."
            )

        image = (
            self.sentinel_service
            .discover_latest_image(
                forest_area=forest,

                max_cloud_cover=(
                    self.settings
                    .max_cloud_cover_percentage
                ),

                search_days=(
                    self.settings.image_search_days
                ),
            )
        )

        if image is None:

            raise ValueError(
                "No suitable Sentinel-2 image was "
                "found for this forest area."
            )

        return image

    # =========================================================
    # SELECT CURRENT IMAGE PAIR
    # =========================================================

    def select_current_image_pair(
        self,
        forest_area_id: int,
    ):
        """
        Select the baseline and comparison products to use.

        Args:
            forest_area_id:
                Forest area being analysed.

        Returns:
            tuple:
                The baseline product and the comparison
                product, in that order.

        Raises:
            ValueError:
                No compatible pair is held, for example when
                only one product exists or the candidates do
                not share a tile.

        Compatibility means more than two different dates.
        The pair must cover the same ground on the same
        grid, or their pixels cannot be differenced; and
        they should sit in equivalent seasonal windows in
        different years, or the comparison measures the dry
        season rather than clearing. See create_analysis_job
        for why that second condition governs whether the
        result means anything.
        """

        (
            previous_image,
            latest_image,
        ) = (
            self.image_selection_service
            .select_image_pair(
                forest_area_id=forest_area_id
            )
        )

        return (
            previous_image,
            latest_image,
        )

    # =========================================================
    # RUN COMPLETE ANALYSIS
    # =========================================================

    def run_analysis(
        self,
        forest_area_id: int,
        started_by: int | None = None,
    ) -> AnalysisJob:
        """
        Create and run an analysis from start to finish.

        Args:
            forest_area_id:
                Forest area to analyse.
            started_by:
                Officer who requested the run, or None for a
                scheduled run with no person behind it.

        Returns:
            AnalysisJob:
                The finished job, COMPLETED or FAILED.

        Raises:
            ValueError:
                The forest area does not exist, or no
                compatible image pair is available.
            RuntimeError:
                Copernicus cannot be reached.

        Steps:
            1. Copernicus image discovery.
            2. New image download if required.
            3. Previous/latest image selection.
            4. Analysis job creation.
            5. NDVI/detection processing.
            6. Alert generation.

        This runs the whole pipeline SYNCHRONOUSLY and
        returns only when it is finished. A cloud-free
        composite over a district takes minutes, so callers
        serving an HTTP request should create the job and
        let the background worker call execute instead,
        rather than holding the officer's request open for
        the duration.
        """

        # -----------------------------------------------------
        # Acquire newest Sentinel-2 image
        # -----------------------------------------------------

        self.acquire_latest_satellite_image(
            forest_area_id=forest_area_id
        )

        # -----------------------------------------------------
        # Select compatible image pair
        # -----------------------------------------------------

        (
            previous_image,
            latest_image,
        ) = self.select_current_image_pair(
            forest_area_id=forest_area_id
        )

        # -----------------------------------------------------
        # Create job
        # -----------------------------------------------------

        job = self.create_analysis_job(
            forest_area_id=forest_area_id,

            previous_satellite_image_id=(
                previous_image.id
            ),

            satellite_image_id=(
                latest_image.id
            ),

            started_by=started_by,

            job_type=(
                AnalysisJobType.AUTOMATIC
            ),
        )

        # -----------------------------------------------------
        # Execute
        # -----------------------------------------------------

        self.execute(job)

        return job

    # =========================================================
    # SUMMARISE VEGETATION CHANGE
    # =========================================================

    @staticmethod
    def summarise_vegetation_change(
        detections: list,
    ) -> float:
        """
        Reduce a run's detections to one percentage for the
        analysis job record.

        Args:
            detections:
                Detections created by this run.

        Returns:
            The area-weighted mean NDVI loss, or 0.0 when
            nothing was detected.

        Weighting by area means a large clearing influences
        the figure more than a small one. A plain average
        would let a marginal half-hectare patch carry the
        same weight as a fifty-hectare clearing.
        """

        if not detections:
            return 0.0

        total_area = sum(
            detection.detected_area_hectares or 0.0
            for detection in detections
        )

        if total_area <= 0.0:
            return 0.0

        weighted_total = sum(
            (detection.vegetation_loss_percentage or 0.0)
            * (detection.detected_area_hectares or 0.0)
            for detection in detections
        )

        return round(weighted_total / total_area, 2)

    # =========================================================
    # RESOLVE A JOB'S SEASONAL WINDOWS
    # =========================================================

    def resolve_job_windows(
        self,
        job: AnalysisJob,
    ) -> tuple[date, date, date, date]:
        """
        Return the seasonal windows an analysis job compares.

        Args:
            job:
                Analysis job being executed.

        Returns:
            baseline_start, baseline_end,
            comparison_start, comparison_end

        Jobs created before seasonal windows existed have
        none stored. Rather than failing, those fall back to
        the standard pair of equivalent windows one year
        apart, which is the comparison the job was always
        intended to make.
        """

        if None in (
            job.baseline_start,
            job.baseline_end,
            job.comparison_start,
            job.comparison_end,
        ):
            return self.default_seasonal_windows()

        return (
            job.baseline_start,
            job.baseline_end,
            job.comparison_start,
            job.comparison_end,
        )

    # =========================================================
    # PREPARE CLOUD-MASKED NDVI FOR ONE IMAGE
    # =========================================================

    def prepare_masked_ndvi(
        self,
        image: SatelliteImage,
        working_directory: Path,
        extract_directory: Path | None = None,
        bounds_wgs84: tuple[float, float, float, float] | None = None,
    ) -> Path:
        """
        Turn a downloaded Sentinel-2 product into a
        cloud-masked NDVI raster.

        Args:
            image:
                Registered satellite image whose storage_path
                points at the downloaded product ZIP.

            working_directory:
                Directory that receives the extracted product
                and every raster derived from it.

        Returns:
            Path to the cloud-masked NDVI GeoTIFF.

        Steps:

            1. Extract the product and calculate NDVI from
               the B04 (red) and B08 (near-infrared) bands.
            2. Locate the 20 m Scene Classification Layer.
            3. Resample the SCL onto the 10 m NDVI grid and
               mask out cloud, cloud shadow, cirrus, snow and
               defective pixels.

        An image whose masked NDVI already exists on disk is
        not processed again. A baseline image is shared by
        every later comparison against it, so reprocessing it
        each time would repeat minutes of work for no gain.
        """

        masked_ndvi_path = (
            working_directory
            / "masked_ndvi"
            / "ndvi_masked.tif"
        )

        # -----------------------------------------------------
        # Reuse previously processed output
        #
        # The file is checked directly rather than trusting
        # the is_processed flag alone, so clearing the storage
        # directory is enough to force a clean reprocess.
        # -----------------------------------------------------

        if masked_ndvi_path.exists():
            return masked_ndvi_path

        # -----------------------------------------------------
        # Extract product and calculate NDVI
        # -----------------------------------------------------

        archive_path = self._local_archive_path(image)
        if archive_path is None:
            raise ValueError(
                "The selected Sentinel-2 product has an invalid local filename."
            )

        processing_result = self.processor_service.process_product(
            zip_path=archive_path,
            working_directory=working_directory,
            extract_directory=extract_directory,
            bounds_wgs84=bounds_wgs84,
        )

        ndvi_path = Path(
            processing_result["ndvi"]
        )

        # -----------------------------------------------------
        # Locate the Scene Classification Layer
        # -----------------------------------------------------

        # The SCL lives beside the other bands, so it is
        # looked for wherever the product was extracted.
        scl_band_path = (
            self.cloud_mask_service.find_scl_band(
                extract_directory
                if extract_directory is not None
                else working_directory / "extracted"
            )
        )

        # -----------------------------------------------------
        # Apply the cloud mask
        # -----------------------------------------------------

        cloud_mask_result = (
            self.cloud_mask_service.process(
                scl_band_path=scl_band_path,

                ndvi_path=ndvi_path,

                working_directory=working_directory,
            )
        )

        # -----------------------------------------------------
        # Record that this product has been processed
        # -----------------------------------------------------

        self.sentinel_service.mark_as_processed(
            image
        )

        return Path(
            cloud_mask_result["masked_ndvi"]
        )

    # =========================================================
    # RUN THE RASTER PIPELINE FOR AN IMAGE PAIR
    # =========================================================

    def prepare_analysis_rasters(
        self,
        job: AnalysisJob,
        previous_image: SatelliteImage,
        latest_image: SatelliteImage,
    ) -> dict[str, str | float]:
        """
        Produce every raster the detection step depends on.

        Args:
            job:
                Analysis job being executed.

            previous_image:
                Baseline Sentinel-2 image.

            latest_image:
                Comparison Sentinel-2 image.

        Returns:
            The persistence result, containing the confirmed
            deforestation mask path and its statistics.

        The directory names below are not arbitrary:
        DetectionService.execute_detection reads exactly
        these locations, so both sides must agree.
        """

        # Outputs belong to the JOB, not to the forest area.
        #
        # Writing them under the area meant every analysis
        # overwrote the one before it, so only the newest
        # rasters survived and an older job reported the
        # newest rasters under its own observation dates.
        # The job identifier is fixed before processing
        # starts, so this directory is immutable: a later
        # analysis of the same area cannot reach it.
        forest_area_directory = self.prepare_job_output_directory(job)

        # -----------------------------------------------------
        # Resolve the boundary before any raster is read
        #
        # Every stage below is confined to the ground this
        # boundary covers. A Sentinel-2 tile is 10,980 x
        # 10,980 pixels; a Copperbelt forest area is a small
        # part of one, so computing NDVI and the cloud mask
        # over the whole tile spent minutes on pixels that
        # the boundary clip then discarded.
        # -----------------------------------------------------

        forest = job.forest_area
        if forest is None:
            forest = self.db.get(ForestArea, job.forest_area_id)
        boundary = validate_stored_forest_boundary(
            forest.geometry if forest is not None else None
        )
        boundary_bounds = tuple(boundary.bounds)

        # -----------------------------------------------------
        # Cloud-masked NDVI for the baseline date
        # -----------------------------------------------------

        previous_masked_ndvi = (
            self.prepare_masked_ndvi(
                image=previous_image,

                bounds_wgs84=boundary_bounds,

                working_directory=(
                    forest_area_directory
                    / "processing_previous"
                ),

                # Shared per product, not copied per job.
                extract_directory=shared_extract_root(
                    forest_area_id=previous_image.forest_area_id,
                    satellite_image_id=previous_image.id,
                    storage_root=self.settings.satellite_image_storage_path,
                ),
            )
        )

        # -----------------------------------------------------
        # Cloud-masked NDVI for the comparison date
        # -----------------------------------------------------

        latest_masked_ndvi = (
            self.prepare_masked_ndvi(
                image=latest_image,

                # The same window, so both dates keep one
                # identical grid and can be subtracted.
                bounds_wgs84=boundary_bounds,

                working_directory=(
                    forest_area_directory
                    / "processing"
                ),

                extract_directory=shared_extract_root(
                    forest_area_id=latest_image.forest_area_id,
                    satellite_image_id=latest_image.id,
                    storage_root=self.settings.satellite_image_storage_path,
                ),
            )
        )

        # -----------------------------------------------------
        # Apply the exact forest boundary to each observation
        # before the shared change-detection implementation
        # sees either raster. Both inputs retain one identical
        # cropped grid, with outside and cloudy pixels as NoData.
        # -----------------------------------------------------

        comparison_directory = forest_area_directory / "comparison"
        previous_comparison_ndvi = comparison_directory / "previous_ndvi.tif"
        recent_comparison_ndvi = comparison_directory / "recent_ndvi.tif"
        grid_metadata = self.boundary_comparison_service.mask_ndvi_pair(
            previous_path=previous_masked_ndvi,
            recent_path=latest_masked_ndvi,
            boundary=boundary,
            previous_output=previous_comparison_ndvi,
            recent_output=recent_comparison_ndvi,
        )
        change_metadata = (
            self.boundary_comparison_service.write_recent_minus_previous_ndvi_change(
                previous_path=previous_comparison_ndvi,
                recent_path=recent_comparison_ndvi,
                output_path=(
                    comparison_directory
                    / "ndvi_change_recent_minus_previous.tif"
                ),
            )
        )

        previous_preview = self.boundary_comparison_service.render_rgb_preview(
            extracted_directory=shared_extract_root(
                forest_area_id=previous_image.forest_area_id,
                satellite_image_id=previous_image.id,
                storage_root=self.settings.satellite_image_storage_path,
            ),
            valid_mask_path=(
                forest_area_directory
                / "processing_previous"
                / "cloud_mask"
                / "valid_pixel_mask.tif"
            ),
            boundary=boundary,
            output_path=comparison_directory / "previous_rgb.png",
        )
        recent_preview = self.boundary_comparison_service.render_rgb_preview(
            extracted_directory=shared_extract_root(
                forest_area_id=latest_image.forest_area_id,
                satellite_image_id=latest_image.id,
                storage_root=self.settings.satellite_image_storage_path,
            ),
            valid_mask_path=(
                forest_area_directory
                / "processing"
                / "cloud_mask"
                / "valid_pixel_mask.tif"
            ),
            boundary=boundary,
            output_path=comparison_directory / "recent_rgb.png",
        )

        # -----------------------------------------------------
        # Confirm vegetation loss across both dates
        #
        # A pixel is only confirmed when it was cloud-free on
        # BOTH dates and its NDVI decline reaches the job's
        # threshold, which removes changes that are really
        # just cloud in one of the two images.
        # -----------------------------------------------------

        ndvi_threshold = (
            job.ndvi_threshold
            or self.settings.ndvi_threshold
        )

        result = self.persistence_service.process(
            previous_ndvi_path=previous_comparison_ndvi,

            latest_ndvi_path=recent_comparison_ndvi,

            working_directory=(
                forest_area_directory
                / "persistence"
            ),

            threshold=ndvi_threshold,
        )

        comparison_imagery = {
            "previous": {
                "product_id": previous_image.product_id,
                "tile_id": previous_image.tile_id,
                "processing_level": previous_image.processing_level,
                "acquisition_date": previous_image.acquisition_date.isoformat(),
                "cloud_cover_percentage": previous_image.cloud_cover_percentage,
                **previous_preview,
            },
            "recent": {
                "product_id": latest_image.product_id,
                "tile_id": latest_image.tile_id,
                "processing_level": latest_image.processing_level,
                "acquisition_date": latest_image.acquisition_date.isoformat(),
                "cloud_cover_percentage": latest_image.cloud_cover_percentage,
                **recent_preview,
            },
            "grid": grid_metadata,
            "ndvi_change": change_metadata,
            "mean_previous_ndvi": grid_metadata["mean_previous_ndvi"],
            "mean_recent_ndvi": grid_metadata["mean_recent_ndvi"],
            "mean_ndvi_change": grid_metadata["mean_ndvi_change"],
            "affected_area_hectares": result["affected_area_hectares"],
            "valid_comparison_pixels": result["valid_pixels"],
            "confirmed_pixels": result["confirmed_pixels"],
            "ndvi_threshold": result["threshold"],
        }
        figure_metadata = self.comparison_figure_service.render(
            previous_rgb_path=comparison_directory / "previous_rgb.png",
            previous_ndvi_path=previous_comparison_ndvi,
            recent_ndvi_path=recent_comparison_ndvi,
            difference_path=(
                comparison_directory / "ndvi_change_recent_minus_previous.tif"
            ),
            output_directory=comparison_directory,
            forest_area_id=job.forest_area_id,
            forest_area_name=forest.name,
            job_id=job.id,
            previous_image_id=previous_image.id,
            recent_image_id=latest_image.id,
            imagery=comparison_imagery,
        )
        write_comparison_manifest(
            comparison_directory / "manifest.json",
            forest_area_id=job.forest_area_id,
            job_id=job.id,
            previous_image_id=previous_image.id,
            recent_image_id=latest_image.id,
            boundary=boundary,
            imagery=comparison_imagery,
            figure=figure_metadata,
        )
        return result

    # =========================================================
    # EXECUTE ANALYSIS
    # =========================================================

    def report_progress(
        self,
        job: AnalysisJob,
        message: str,
    ) -> None:
        """
        Record which stage an analysis has reached.

        Args:
            job:
                Analysis job being executed.

            message:
                What is happening now, in the words an
                officer would use.

        A full run downloads two Sentinel-2 products of
        several hundred megabytes each, extracts them,
        computes NDVI over roughly 120 million pixels twice,
        masks cloud and compares the two dates. That takes
        many minutes.

        Without this the job simply sat at RUNNING for the
        whole period with nothing to show, which is
        indistinguishable from having hung. Recording the
        stage is what separates "this is working" from
        "this is stuck".

        Written on its own transaction so progress survives
        even if a later stage fails.
        """

        job.execution_log = message

        try:
            self.db.commit()

        except Exception:
            # Progress reporting must never be the reason an
            # analysis fails.
            self.db.rollback()

    def execute(
        self,
        job: AnalysisJob,
    ) -> None:
        """
        Execute a queued analysis job in the background.

        Args:
            job:
                The PENDING job to run.

        Returns:
            None. The outcome is recorded on the job itself,
            which the officer polls, rather than returned:
            by the time this finishes, the request that
            created the job has long since been answered.

        Steps:
            1. Find the forest.
            2. Check Copernicus again.
            3. Download newest imagery if available.
            4. Select previous/latest images.
            5. Update the analysis job.
            6. Run detection.
            7. Generate alert.
            8. Complete the job.

        Raises:
            Exception:
                Whatever the pipeline raised. The failure is
                first recorded on the job through
                fail_analysis, then re-raised so the caller
                can log it. Callers must therefore expect
                this to raise, even though the job has
                already been marked FAILED by then.

        On failure the session is rolled back before the job
        is reloaded and marked, because the transaction that
        failed cannot be used to record its own failure.

        NOTE: If marking the job fails in turn, that second
        exception is swallowed and only a rollback is
        performed. The queue worker releases its advisory lock
        on exit; periodic recovery then records the job as
        FAILED without waiting for another server restart.

        A run that completes with no detections is recorded
        as COMPLETED, not FAILED. See complete_analysis.
        """

        try:

            # -------------------------------------------------
            # Get forest
            # -------------------------------------------------

            forest = (
                self.db.query(ForestArea)
                .filter(
                    ForestArea.id
                    == job.forest_area_id
                )
                .first()
            )

            if forest is None:

                raise ValueError(
                    "Forest area associated with "
                    "analysis job was not found."
                )

            boundary = validate_stored_forest_boundary(forest.geometry)

            # -------------------------------------------------
            # Start analysis
            # -------------------------------------------------

            self.start_analysis(job)

            self.report_progress(
                job,
                "Searching Copernicus for imagery covering "
                "the baseline period, one year earlier.",
            )

            # -------------------------------------------------
            # Acquire imagery for both seasonal windows
            #
            # Each window is searched separately so that the
            # baseline comes from the same calendar period a
            # year earlier, not from whatever happens to be
            # most recent.
            #
            # A job that cannot obtain imagery for one of its
            # two windows FAILS. This is different from a job
            # that ran and confirmed no deforestation, which
            # completes normally: the officer's response
            # differs, so the two outcomes must not look
            # alike.
            # -------------------------------------------------

            (
                baseline_start,
                baseline_end,
                comparison_start,
                comparison_end,
            ) = self.resolve_job_windows(job)

            # -------------------------------------------------
            # Observations named on the job are used as given
            #
            # A job created with both observations already
            # chosen is a request to analyse THOSE two, not a
            # request to go looking for newer ones. Searching
            # anyway cost an earlier run eight hours and two
            # gigabyte downloads for products that were
            # already extracted on disk, and the second
            # transfer was reset by the provider, so the job
            # failed having changed nothing.
            #
            # Both must be usable locally before the search is
            # skipped: a row marked downloaded whose file is
            # missing would otherwise send the run on to fail
            # later, in rasterio, with a far less clear
            # message. That case is real; the database carried
            # four such rows.
            # -------------------------------------------------

            named_previous = self._usable_local_image(
                job.previous_satellite_image_id
            )

            named_latest = self._usable_local_image(
                job.satellite_image_id
            )

            if job.previous_satellite_image_id is not None:
                if named_previous is None or named_latest is None:
                    raise ValueError(
                        "A selected observation is missing from local storage. "
                        "The selected pair was not replaced; acquire both products again."
                    )
                if (
                    named_previous.forest_area_id != forest.id
                    or named_latest.forest_area_id != forest.id
                    or named_previous.tile_id != named_latest.tile_id
                    or named_previous.acquisition_date >= named_latest.acquisition_date
                    or not is_level_2a(named_previous.processing_level)
                    or not is_level_2a(named_latest.processing_level)
                ):
                    raise ValueError(
                        "The selected observations no longer form a compatible pair."
                    )
                self.validate_local_image_inputs(named_previous)
                self.validate_local_image_inputs(named_latest)

            if named_previous is not None and named_latest is not None:

                self.report_progress(
                    job,
                    "Using the two observations named on this "
                    "job. Both are already held locally, so no "
                    "download is required.",
                )

                baseline_available = named_previous
                comparison_available = named_latest

            else:

                baseline_available = (
                    self.sentinel_service
                    .discover_image_in_window(
                        forest_area=forest,

                        start_date=baseline_start,

                        end_date=baseline_end,

                        max_cloud_cover=(
                            self.settings
                            .max_cloud_cover_percentage
                        ),
                    )
                )

                self.report_progress(
                    job,
                    "Searching Copernicus for imagery covering "
                    "the comparison period.",
                )

                comparison_available = None

            if baseline_available is None:

                raise ValueError(
                    "No Sentinel-2 image below "
                    f"{self.settings.max_cloud_cover_percentage}% "
                    "cloud cover was found in the baseline "
                    f"window {baseline_start} to "
                    f"{baseline_end}."
                )

            if comparison_available is None:

                comparison_available = (
                    self.sentinel_service
                    .discover_image_in_window(
                        forest_area=forest,

                        start_date=comparison_start,

                        end_date=comparison_end,

                        max_cloud_cover=(
                            self.settings
                            .max_cloud_cover_percentage
                        ),
                    )
                )

            if comparison_available is None:

                raise ValueError(
                    "No Sentinel-2 image below "
                    f"{self.settings.max_cloud_cover_percentage}% "
                    "cloud cover was found in the comparison "
                    f"window {comparison_start} to "
                    f"{comparison_end}."
                )

            # -------------------------------------------------
            # Refresh database state
            # -------------------------------------------------

            self.db.expire_all()

            # -------------------------------------------------
            # Use the images acquired for each window
            #
            # The pair is taken directly from the two window
            # searches above rather than from "the two most
            # recent images on file", because the whole point
            # of the seasonal design is that the baseline
            # comes from a specific earlier period.
            # -------------------------------------------------

            previous_image = baseline_available

            latest_image = comparison_available

            # -------------------------------------------------
            # Both images must come from the same tile
            #
            # NDVI rasters can only be compared pixel by pixel
            # when they share a grid. Comparing two different
            # Sentinel-2 tiles would fail later, in rasterio,
            # with a far less clear message.
            # -------------------------------------------------

            if previous_image.tile_id != latest_image.tile_id:

                raise ValueError(
                    "The baseline and comparison images come "
                    f"from different Sentinel-2 tiles "
                    f"({previous_image.tile_id} and "
                    f"{latest_image.tile_id}), so they cannot "
                    "be compared directly."
                )

            # -------------------------------------------------
            # Update job with actual image pair
            # -------------------------------------------------

            job.previous_satellite_image_id = (
                previous_image.id
            )

            job.satellite_image_id = (
                latest_image.id
            )

            self.db.commit()

            self.db.refresh(job)

            # -------------------------------------------------
            # Process imagery into analysis rasters
            #
            # This step produces the cloud-masked NDVI for
            # both dates and the persistence-confirmed
            # deforestation mask. It must run before
            # detection, which reads those rasters from disk.
            # -------------------------------------------------

            self.report_progress(
                job,
                "Processing imagery: calculating NDVI for "
                "both dates and removing cloud. This is the "
                "longest stage and may take several minutes.",
            )
            self.prepare_analysis_rasters(
                job=job,

                previous_image=previous_image,

                latest_image=latest_image,
            )

            # -------------------------------------------------
            # Execute deforestation detection
            # -------------------------------------------------

            self.report_progress(
                job,
                "Comparing the two dates and measuring "
                "confirmed clearings.",
            )
            detections = (
                self.detection_service
                .execute_detection(
                    job
                )
            )

            # -------------------------------------------------
            # Generate an alert for each clearing
            #
            # Each detection is a separate place an officer
            # may have to visit, so each raises its own
            # alert rather than one alert describing several
            # unrelated sites.
            # -------------------------------------------------

            for detection in detections:

                self.alert_service.process_detection(
                    detection
                )

            # -------------------------------------------------
            # Summarise vegetation change for the job
            #
            # The job-level figure is the mean NDVI loss
            # weighted by the area of each clearing, so a
            # large clearing counts for more than a small
            # one. An unweighted mean would let a marginal
            # half-hectare patch pull the summary for the
            # whole run.
            # -------------------------------------------------

            vegetation_change = (
                self.summarise_vegetation_change(
                    detections
                )
            )

            # -------------------------------------------------
            # Cloud coverage
            # -------------------------------------------------

            cloud_cover = (
                latest_image
                .cloud_cover_percentage
                or 0.0
            )

            # -------------------------------------------------
            # Complete analysis
            # -------------------------------------------------

            self.complete_analysis(
                job=job,

                cloud_cover=cloud_cover,

                vegetation_change=(
                    vegetation_change
                ),

                ndvi_threshold=(
                    job.ndvi_threshold
                    or self.settings.ndvi_threshold
                ),
            )

        except Exception as exc:

            # -------------------------------------------------
            # Rollback failed database transaction
            # -------------------------------------------------

            self.db.rollback()

            try:

                # Refresh job after rollback

                job = (
                    self.db.query(
                        AnalysisJob
                    )
                    .filter(
                        AnalysisJob.id
                        == job.id
                    )
                    .first()
                )

                if job is not None:

                    self.fail_analysis(
                        job=job,

                        error_message=str(
                            exc
                        ),
                    )

            except Exception:

                self.db.rollback()

            # -------------------------------------------------
            # Re-raise
            # -------------------------------------------------

            raise
