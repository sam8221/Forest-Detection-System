"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Analysis Service

Purpose:
    Coordinates the complete intelligent deforestation
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

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.analysis_job import AnalysisJob
from app.models.enums import (
    AnalysisJobStatus,
    AnalysisJobType,
)
from app.models.forest_area import ForestArea
from app.models.satellite_image import SatelliteImage

from app.services.alert_service import AlertService
from app.services.cloud_mask_service import CloudMaskService
from app.services.detection_service import DetectionService
from app.services.persistence_service import PersistenceService
from app.services.satellite_image_selection_service import (
    SatelliteImageSelectionService,
)
from app.services.sentinel_processor_service import (
    SentinelProcessorService,
)
from app.services.sentinel_service import SentinelService


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

        return job

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
        """

        completed_at = (
            datetime.now(UTC)
        )

        job.completed_at = completed_at

        job.status = (
            AnalysisJobStatus.COMPLETED
        )

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

        processing_result = (
            self.processor_service.process_product(
                zip_path=image.storage_path,

                working_directory=working_directory,
            )
        )

        ndvi_path = Path(
            processing_result["ndvi"]
        )

        # -----------------------------------------------------
        # Locate the Scene Classification Layer
        # -----------------------------------------------------

        scl_band_path = (
            self.cloud_mask_service.find_scl_band(
                working_directory
                / "extracted"
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

        forest_area_directory = (
            self.settings
            .satellite_image_storage_path
            / str(job.forest_area_id)
        )

        # -----------------------------------------------------
        # Cloud-masked NDVI for the baseline date
        # -----------------------------------------------------

        previous_masked_ndvi = (
            self.prepare_masked_ndvi(
                image=previous_image,

                working_directory=(
                    forest_area_directory
                    / "processing_previous"
                ),
            )
        )

        # -----------------------------------------------------
        # Cloud-masked NDVI for the comparison date
        # -----------------------------------------------------

        latest_masked_ndvi = (
            self.prepare_masked_ndvi(
                image=latest_image,

                working_directory=(
                    forest_area_directory
                    / "processing"
                ),
            )
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

        return self.persistence_service.process(
            previous_ndvi_path=previous_masked_ndvi,

            latest_ndvi_path=latest_masked_ndvi,

            working_directory=(
                forest_area_directory
                / "persistence"
            ),

            threshold=ndvi_threshold,
        )

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
        performed, leaving the job RUNNING with nothing
        recorded against it. It is then closed as FAILED at
        the next startup by recover_abandoned_analysis_jobs,
        but until the server restarts the officer sees a run
        that appears to be still in progress.

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

            self.report_progress(
                job,
                "Searching Copernicus for imagery covering "
                "the comparison period.",
            )
            if baseline_available is None:

                raise ValueError(
                    "No Sentinel-2 image below "
                    f"{self.settings.max_cloud_cover_percentage}% "
                    "cloud cover was found in the baseline "
                    f"window {baseline_start} to "
                    f"{baseline_end}."
                )

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