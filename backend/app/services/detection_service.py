"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Detection Service

Purpose:
    Performs forest change detection and manages
    detection records.

Responsibilities:
    - Create detections.
    - Verify detections.
    - Reject detections.
    - Close detections.
    - Calculate detection statistics from processed
      Sentinel-2 imagery.
    - Execute two-date forest change analysis.
    - Track analysis-job status and execution time.
    - Use persistence-confirmed deforestation.
    - Calculate detection confidence.
    - Prevent duplicate detections for the same
      satellite-image pair.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    2.2.0
===========================================================
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import numpy as np
import rasterio
from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.enums import (
    AnalysisJobStatus,
    DetectionStatus,
)

from app.repositories.detection_repository import (
    DetectionRepository,
)

from app.services.alert_service import AlertService
from app.services.satellite_image_selection_service import (
    SatelliteImageSelectionService,
)


class DetectionService:
    """
    Handles forest change detection and detection records.
    """

    # =====================================================
    # CONFIGURATION
    # =====================================================

    MIN_DETECTION_AREA_HECTARES = 0.50

    # Threshold used by persistence/change detection.
    DEFAULT_NDVI_THRESHOLD = 0.30

    # =====================================================
    # INITIALIZATION
    # =====================================================

    def __init__(
        self,
        db: Session,
    ):
        """
        Initialize the detection service.
        """

        self.db = db

        self.repository = DetectionRepository(
            db,
        )

        self.alert_service = AlertService(
            db,
        )

    # =====================================================
    # RUN ANALYSIS
    # =====================================================

    def run_analysis(
        self,
        forest_area_id: int,
        started_by: int | None = None,
    ) -> AnalysisJob:
        """
        Start a two-date forest-change analysis.

        Workflow:

        1. Select the latest compatible Sentinel-2 image.
        2. Select the previous compatible Sentinel-2 image.
        3. Prevent duplicate analysis of the same image pair.
        4. Create an analysis job.
        5. Set job status to RUNNING.
        6. Execute the real detection workflow.
        7. Store analysis statistics.
        8. Mark the job COMPLETED.

        If processing fails:

        RUNNING -> FAILED

        The exception is re-raised after the failed job
        has been recorded.
        """

        # -------------------------------------------------
        # Select compatible image pair
        # -------------------------------------------------

        image_selector = (
            SatelliteImageSelectionService(
                self.db,
            )
        )

        previous_image, latest_image = (
            image_selector.select_image_pair(
                forest_area_id=forest_area_id,
            )
        )

        # -------------------------------------------------
        # Prevent duplicate analysis
        # -------------------------------------------------

        existing_job = (
            self.db.query(AnalysisJob)
            .filter(
                AnalysisJob.forest_area_id
                == forest_area_id,
                AnalysisJob.previous_satellite_image_id
                == previous_image.id,
                AnalysisJob.satellite_image_id
                == latest_image.id,
                AnalysisJob.status
                == AnalysisJobStatus.COMPLETED,
            )
            .order_by(
                AnalysisJob.created_at.desc(),
            )
            .first()
        )

        if existing_job is not None:
            return existing_job

        # -------------------------------------------------
        # Create analysis job
        # -------------------------------------------------

        job = AnalysisJob(
            forest_area_id=forest_area_id,
            previous_satellite_image_id=previous_image.id,
            satellite_image_id=latest_image.id,
            started_by=started_by,
            status=AnalysisJobStatus.PENDING,
            ndvi_threshold=self.DEFAULT_NDVI_THRESHOLD,
        )

        self.db.add(job)

        try:
            self.db.commit()
            self.db.refresh(job)

        except Exception:
            self.db.rollback()
            raise

        # -------------------------------------------------
        # Start timing
        # -------------------------------------------------

        started_at = datetime.now(UTC)
        timer_start = perf_counter()

        job.status = AnalysisJobStatus.RUNNING
        job.started_at = started_at
        job.error_message = None

        job.execution_log = (
            "Analysis started. "
            f"Previous image ID: {previous_image.id}. "
            f"Latest image ID: {latest_image.id}."
        )

        try:

            self.db.commit()

            # -------------------------------------------------
            # Execute real detection
            # -------------------------------------------------

            detection = self.execute_detection(
                job=job,
            )

            # -------------------------------------------------
            # Calculate execution time
            # -------------------------------------------------

            completed_at = datetime.now(UTC)

            duration_seconds = (
                perf_counter()
                - timer_start
            )

            job.completed_at = completed_at
            job.duration_seconds = round(
                duration_seconds,
                3,
            )

            job.status = (
                AnalysisJobStatus.COMPLETED
            )

            # -------------------------------------------------
            # Save analysis statistics
            # -------------------------------------------------

            if detection is not None:

                job.vegetation_change_percentage = (
                    detection.vegetation_loss_percentage
                )

                job.execution_log = (
                    "Analysis completed successfully. "
                    f"Confirmed deforestation area: "
                    f"{detection.detected_area_hectares:.4f} ha. "
                    f"Confidence: "
                    f"{detection.confidence_score:.2f}%. "
                    f"NDVI before: "
                    f"{detection.ndvi_before:.6f}. "
                    f"NDVI after: "
                    f"{detection.ndvi_after:.6f}. "
                    f"Vegetation loss: "
                    f"{detection.vegetation_loss_percentage:.2f}%."
                )

            else:

                job.vegetation_change_percentage = 0.0

                job.execution_log = (
                    "Analysis completed successfully. "
                    "No significant deforestation was confirmed."
                )

            self.db.commit()
            self.db.refresh(job)

            return job

        except Exception as exc:

            # -------------------------------------------------
            # Calculate failure duration
            # -------------------------------------------------

            duration_seconds = (
                perf_counter()
                - timer_start
            )

            # -------------------------------------------------
            # Mark job as failed
            # -------------------------------------------------

            job.status = AnalysisJobStatus.FAILED

            job.completed_at = datetime.now(UTC)

            job.duration_seconds = round(
                duration_seconds,
                3,
            )

            job.error_message = str(exc)[:500]

            job.execution_log = (
                "Analysis failed. "
                f"Error: {str(exc)[:1000]}"
            )

            try:
                self.db.commit()

            except Exception:
                self.db.rollback()

            raise

    # =====================================================
    # CREATE DETECTION
    # =====================================================

    def create_detection(
        self,
        job: AnalysisJob,
        detected_area: float,
        confidence: float,
        ndvi_before: float,
        ndvi_after: float,
        vegetation_loss: float,
    ) -> Detection:
        """
        Create a new detection record.
        """

        detection = Detection(
            forest_area_id=job.forest_area_id,
            satellite_image_id=job.satellite_image_id,
            analysis_job_id=job.id,
            detected_area_hectares=detected_area,
            confidence_score=confidence,
            ndvi_before=ndvi_before,
            ndvi_after=ndvi_after,
            vegetation_loss_percentage=vegetation_loss,
            status=DetectionStatus.PENDING,
        )

        return self.repository.create(
            detection,
        )

    # =====================================================
    # VERIFY DETECTION
    # =====================================================

    def verify_detection(
        self,
        detection: Detection,
        verified_by: int,
    ) -> Detection:
        """
        Verify a detection and trigger alerts.
        """

        detection.status = (
            DetectionStatus.VERIFIED
        )

        detection.verified_by = verified_by

        detection.verified_at = datetime.now(
            UTC,
        )

        detection = self.repository.update(
            detection,
        )

        self.alert_service.process_detection(
            detection,
        )

        return detection

    # =====================================================
    # REJECT DETECTION
    # =====================================================

    def reject_detection(
        self,
        detection: Detection,
        verified_by: int,
        notes: str,
    ) -> Detection:
        """
        Reject a detection.
        """

        detection.status = (
            DetectionStatus.REJECTED
        )

        detection.verified_by = verified_by

        detection.verified_at = datetime.now(
            UTC,
        )

        detection.verification_notes = notes

        return self.repository.update(
            detection,
        )

    # =====================================================
    # CLOSE DETECTION
    # =====================================================

    def close_detection(
        self,
        detection: Detection,
        notes: str | None = None,
    ) -> Detection:
        """
        Close a verified detection.
        """

        detection.status = (
            DetectionStatus.CLOSED
        )

        if notes:
            detection.verification_notes = notes

        return self.repository.update(
            detection,
        )

    # =====================================================
    # CALCULATE DETECTION STATISTICS
    # =====================================================

    def calculate_detection_statistics(
        self,
        previous_ndvi_path: str | Path,
        latest_ndvi_path: str | Path,
        confirmed_mask_path: str | Path,
    ) -> dict[str, float]:
        """
        Calculate real detection statistics from
        processed Sentinel-2 imagery.

        Inputs:

        previous_ndvi_path:
            Cloud-masked NDVI from the previous date.

        latest_ndvi_path:
            Cloud-masked NDVI from the latest date.

        confirmed_mask_path:
            Persistence-confirmed deforestation mask.

        Returns:

            detected_area_hectares
            confidence
            ndvi_before
            ndvi_after
            vegetation_loss_percentage
            confirmed_pixels
        """

        previous_ndvi_path = Path(
            previous_ndvi_path,
        )

        latest_ndvi_path = Path(
            latest_ndvi_path,
        )

        confirmed_mask_path = Path(
            confirmed_mask_path,
        )

        # -------------------------------------------------
        # Validate files
        # -------------------------------------------------

        for path, name in [
            (
                previous_ndvi_path,
                "Previous NDVI",
            ),
            (
                latest_ndvi_path,
                "Latest NDVI",
            ),
            (
                confirmed_mask_path,
                "Confirmed deforestation mask",
            ),
        ]:
            if not path.exists():
                raise FileNotFoundError(
                    f"{name} file not found: {path}"
                )

        # -------------------------------------------------
        # Open rasters
        # -------------------------------------------------

        with rasterio.open(
            previous_ndvi_path,
        ) as previous_src, rasterio.open(
            latest_ndvi_path,
        ) as latest_src, rasterio.open(
            confirmed_mask_path,
        ) as mask_src:

            previous = previous_src.read(1)

            latest = latest_src.read(1)

            confirmed_mask = mask_src.read(1)

            # -------------------------------------------------
            # Validate dimensions
            # -------------------------------------------------

            if previous.shape != latest.shape:
                raise ValueError(
                    "Previous and latest NDVI rasters "
                    "have different dimensions."
                )

            if previous.shape != confirmed_mask.shape:
                raise ValueError(
                    "NDVI rasters and confirmed "
                    "deforestation mask are not aligned."
                )

            # -------------------------------------------------
            # Validate transforms
            # -------------------------------------------------

            if (
                previous_src.transform
                != latest_src.transform
            ):
                raise ValueError(
                    "Previous and latest NDVI rasters "
                    "have different spatial transforms."
                )

            if (
                previous_src.transform
                != mask_src.transform
            ):
                raise ValueError(
                    "NDVI rasters and confirmed mask "
                    "have different spatial transforms."
                )

            # -------------------------------------------------
            # Validate CRS
            # -------------------------------------------------

            if (
                previous_src.crs
                != latest_src.crs
            ):
                raise ValueError(
                    "Previous and latest NDVI rasters "
                    "have different CRS."
                )

            if (
                previous_src.crs
                != mask_src.crs
            ):
                raise ValueError(
                    "NDVI rasters and confirmed mask "
                    "have different CRS."
                )

            # -------------------------------------------------
            # Pixel size
            # -------------------------------------------------

            pixel_width = abs(
                previous_src.transform.a
            )

            pixel_height = abs(
                previous_src.transform.e
            )

            pixel_area_m2 = (
                pixel_width
                * pixel_height
            )

        # -------------------------------------------------
        # Confirmed deforestation pixels
        # -------------------------------------------------

        confirmed = (
            confirmed_mask == 1
        )

        confirmed_pixels = int(
            np.count_nonzero(
                confirmed,
            )
        )

        if confirmed_pixels == 0:
            return {
                "detected_area_hectares": 0.0,
                "confidence": 0.0,
                "ndvi_before": 0.0,
                "ndvi_after": 0.0,
                "vegetation_loss_percentage": 0.0,
                "confirmed_pixels": 0.0,
            }

        # -------------------------------------------------
        # Remove invalid NDVI values
        # -------------------------------------------------

        valid = (
            confirmed
            & np.isfinite(previous)
            & np.isfinite(latest)
            & (previous != -9999)
            & (latest != -9999)
        )

        valid_pixels = int(
            np.count_nonzero(
                valid,
            )
        )

        if valid_pixels == 0:
            raise ValueError(
                "No valid NDVI pixels exist inside "
                "the confirmed deforestation mask."
            )

        # -------------------------------------------------
        # NDVI values
        # -------------------------------------------------

        previous_values = (
            previous[valid]
            .astype(np.float64)
        )

        latest_values = (
            latest[valid]
            .astype(np.float64)
        )

        # -------------------------------------------------
        # Mean NDVI
        # -------------------------------------------------

        ndvi_before = float(
            np.mean(
                previous_values,
            )
        )

        ndvi_after = float(
            np.mean(
                latest_values,
            )
        )

        # -------------------------------------------------
        # Vegetation loss
        # -------------------------------------------------

        if abs(ndvi_before) > 1e-9:

            vegetation_loss_percentage = (
                (
                    ndvi_before
                    - ndvi_after
                )
                / abs(ndvi_before)
            ) * 100.0

        else:

            vegetation_loss_percentage = 0.0

        vegetation_loss_percentage = max(
            0.0,
            min(
                100.0,
                vegetation_loss_percentage,
            ),
        )

        # -------------------------------------------------
        # Affected area
        # -------------------------------------------------

        detected_area_hectares = (
            valid_pixels
            * pixel_area_m2
            / 10000.0
        )

        # -------------------------------------------------
        # Confidence indicator
        #
        # This is a confidence indicator produced from
        # persistence confirmation and NDVI reduction.
        #
        # It is NOT an AI probability.
        # -------------------------------------------------

        persistence_ratio = (
            valid_pixels
            / confirmed_pixels
        )

        ndvi_strength = (
            vegetation_loss_percentage
            / 100.0
        )

        confidence = (
            (
                persistence_ratio
                * 0.60
            )
            +
            (
                ndvi_strength
                * 0.40
            )
        ) * 100.0

        confidence = max(
            0.0,
            min(
                100.0,
                confidence,
            ),
        )

        return {
            "detected_area_hectares": round(
                detected_area_hectares,
                4,
            ),
            "confidence": round(
                confidence,
                2,
            ),
            "ndvi_before": round(
                ndvi_before,
                6,
            ),
            "ndvi_after": round(
                ndvi_after,
                6,
            ),
            "vegetation_loss_percentage": round(
                vegetation_loss_percentage,
                2,
            ),
            "confirmed_pixels": float(
                confirmed_pixels,
            ),
        }

    # =====================================================
    # EXECUTE DETECTION
    # =====================================================

    def execute_detection(
        self,
        job: AnalysisJob,
    ) -> Detection | None:
        """
        Execute the real deforestation detection workflow.

        Processing pipeline:

        1. Load previous cloud-masked NDVI.
        2. Load latest cloud-masked NDVI.
        3. Load persistence-confirmed mask.
        4. Calculate confirmed affected area.
        5. Calculate mean NDVI before.
        6. Calculate mean NDVI after.
        7. Calculate vegetation loss.
        8. Calculate confidence.
        9. Create a PENDING detection.

        The Forestry Officer must review the detection.
        """

        # -------------------------------------------------
        # Validate image pair
        # -------------------------------------------------

        if (
            job.previous_satellite_image_id
            is None
        ):
            raise ValueError(
                "Analysis job does not have a "
                "previous satellite image."
            )

        if job.satellite_image_id is None:
            raise ValueError(
                "Analysis job does not have a "
                "latest satellite image."
            )

        # -------------------------------------------------
        # Storage root
        # -------------------------------------------------

        storage_root = (
            Path(__file__)
            .resolve()
            .parents[2]
            / "storage"
            / "satellite_images"
        )

        # -------------------------------------------------
        # Forest-area processing directory
        # -------------------------------------------------

        forest_area_directory = (
            storage_root
            / str(job.forest_area_id)
        )

        # -------------------------------------------------
        # Previous cloud-masked NDVI
        # -------------------------------------------------

        previous_ndvi = (
            forest_area_directory
            / "processing_previous"
            / "masked_ndvi"
            / "ndvi_masked.tif"
        )

        # -------------------------------------------------
        # Latest cloud-masked NDVI
        # -------------------------------------------------

        latest_ndvi = (
            forest_area_directory
            / "processing"
            / "masked_ndvi"
            / "ndvi_masked.tif"
        )

        # -------------------------------------------------
        # Persistence-confirmed mask
        # -------------------------------------------------

        confirmed_mask = (
            forest_area_directory
            / "persistence"
            / "persistence"
            / "confirmed_deforestation.tif"
        )

        # -------------------------------------------------
        # Calculate real statistics
        # -------------------------------------------------

        statistics = (
            self.calculate_detection_statistics(
                previous_ndvi_path=previous_ndvi,
                latest_ndvi_path=latest_ndvi,
                confirmed_mask_path=confirmed_mask,
            )
        )

        detected_area = statistics[
            "detected_area_hectares"
        ]

        # -------------------------------------------------
        # No significant change
        # -------------------------------------------------

        if (
            detected_area
            < self.MIN_DETECTION_AREA_HECTARES
        ):
            return None

        # -------------------------------------------------
        # Prevent duplicate detection
        # -------------------------------------------------

        existing_detection = (
            self.db.query(Detection)
            .filter(
                Detection.forest_area_id
                == job.forest_area_id,
                Detection.satellite_image_id
                == job.satellite_image_id,
            )
            .order_by(
                Detection.created_at.desc(),
            )
            .first()
        )

        if existing_detection is not None:
            return existing_detection

        # -------------------------------------------------
        # Create real detection
        # -------------------------------------------------

        detection = self.create_detection(
            job=job,
            detected_area=detected_area,
            confidence=statistics[
                "confidence"
            ],
            ndvi_before=statistics[
                "ndvi_before"
            ],
            ndvi_after=statistics[
                "ndvi_after"
            ],
            vegetation_loss=statistics[
                "vegetation_loss_percentage"
            ],
        )

        return detection