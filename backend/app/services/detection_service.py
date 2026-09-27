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
    - Use persistence-confirmed deforestation.
    - Suppress patches below the minimum detectable area.
    - Calculate detection confidence.
    - Prevent duplicate detections for the same
      satellite-image pair.

Note:
    Analysis-job orchestration (status transitions, timing
    and raster processing) belongs to AnalysisService. This
    service turns already-processed rasters into Detection
    records and nothing more.

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

import numpy as np
import rasterio
from geoalchemy2.shape import from_shape
from rasterio.features import geometry_mask, shapes
from shapely.geometry import MultiPolygon, Polygon, shape
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import NDVI_NODATA
from app.models.analysis_job import AnalysisJob
from app.models.detection import Detection
from app.models.enums import DetectionStatus

from app.repositories.detection_repository import (
    DetectionRepository,
)

from app.services.alert_service import AlertService


# =========================================================
# CONFIDENCE INDICATOR WEIGHTS
#
# How the two components of confidence_indicator are
# balanced. They sum to 1.0, so the indicator stays within
# 0-100 whatever the inputs.
#
# Coverage, the share of the patch that carried a reading on
# both dates, is weighted more heavily than severity: a
# pronounced decline seen over a fifth of a clearing is
# weaker evidence than a moderate decline seen over all of
# it, because the rest of the patch was never observed.
#
# These are a reasoned starting point, not a measured
# optimum. The Chapter Five evaluation can test them
# against verified and rejected detections.
# =========================================================

COVERAGE_WEIGHT = 0.60

SEVERITY_WEIGHT = 0.40


class DetectionService:
    """
    Handles forest change detection and detection records.
    """

    # =====================================================
    # INITIALIZATION
    # =====================================================

    def __init__(
        self,
        db: Session,
    ):
        """
        Initialize the detection service.

        Detection thresholds are read from application
        settings rather than being hardcoded here, so the
        minimum detectable area and the NDVI threshold have
        a single authoritative definition shared by every
        service in the pipeline.
        """

        self.db = db

        self.settings = get_settings()

        self.repository = DetectionRepository(
            db,
        )

        self.alert_service = AlertService(
            db,
        )

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
        geometry=None,
    ) -> Detection:
        """
        Create a new detection record.

        Args:
            geometry:
                Outline of the clearing, in UTM so that its
                area is measured in metres. Optional only so
                that a detection can still be recorded if
                the outline could not be built.
        """

        detection = Detection(
            forest_area_id=job.forest_area_id,
            satellite_image_id=job.satellite_image_id,
            analysis_job_id=job.id,
            geometry=geometry,
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
        Confirm a detection as real clearing and alert.

        Args:
            detection:
                The detection being judged.
            verified_by:
                Identifier of the officer making the
                judgement, recorded so the decision is
                attributable.

        Returns:
            Detection:
                The updated record.

        Verifying is what releases the alert workflow, so
        officers are notified only about clearing a person
        has confirmed rather than about every array of
        pixels the threshold flagged.

        The verdict is decided by which method is called,
        not by a status supplied by the caller. Rejecting
        through this method would mark the detection
        VERIFIED, email officers about clearing that was
        just judged false, and record a false positive as a
        true positive in the data the accuracy evaluation
        rests on.
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
        Record a detection as not being real clearing.

        Args:
            detection:
                The detection being judged.
            verified_by:
                Identifier of the officer making the
                judgement.
            notes:
                Why it was rejected. Required rather than
                optional: a rejection without a reason
                cannot be reviewed later, and these notes
                are the record of what the system mistook
                for clearing.

        Returns:
            Detection:
                The updated record.

        No alert is raised. The record is kept rather than
        deleted, because rejected detections are the false
        positives the accuracy evaluation is calculated
        from; deleting them would leave only successes and
        make the system appear more accurate than it is.
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
        Close a detection once it has been acted upon.

        Args:
            detection:
                The detection to close.
            notes:
                What action was taken, for example the
                outcome of a field visit. Optional; when
                absent, any existing verification notes are
                left as they are rather than cleared.

        Returns:
            Detection:
                The updated record.

        Closing marks the end of the response to a
        detection, not a judgement about whether it was
        real. That judgement stays in the verified or
        rejected state it was given, so closing a case does
        not remove it from the accuracy evaluation.
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
    # UTM SRID FROM A RASTER CRS
    # =====================================================

    @staticmethod
    def utm_srid_from_crs(crs) -> int:
        """
        Derive the EPSG code of a UTM coordinate system.

        Args:
            crs:
                Coordinate reference system of a raster.

        Returns:
            The EPSG code, for example 32735 for UTM Zone
            35S, which covers the Copperbelt.

        Raises:
            ValueError:
                The raster is not in a UTM projection, so
                its coordinates are not in metres and the
                geometry could not be stored correctly.

        The code is calculated from the zone number rather
        than looked up with CRS.to_epsg(). A PostGIS
        installation on the developer machine supplies an
        older proj.db that rasterio cannot read, which makes
        to_epsg() return None. The arithmetic below needs no
        database:

            northern hemisphere: 32600 + zone
            southern hemisphere: 32700 + zone
        """

        parameters = crs.to_dict()

        if parameters.get("proj") != "utm":
            raise ValueError(
                "Detection geometry requires a UTM raster, "
                "so that areas are measured in metres. "
                f"Found projection: {parameters.get('proj')}"
            )

        zone = int(parameters["zone"])

        if parameters.get("south"):
            return 32700 + zone

        return 32600 + zone

    # =====================================================
    # EXTRACT DETECTION PATCHES
    # =====================================================

    def extract_detection_patches(
        self,
        previous_ndvi_path: str | Path,
        latest_ndvi_path: str | Path,
        confirmed_mask_path: str | Path,
    ) -> list[dict]:
        """
        Split the confirmed deforestation mask into
        individual clearings.

        Args:
            previous_ndvi_path:
                Cloud-masked NDVI from the baseline date.

            latest_ndvi_path:
                Cloud-masked NDVI from the comparison date.

            confirmed_mask_path:
                Persistence-confirmed deforestation mask.

        Returns:
            One dictionary per clearing that reaches the
            minimum detectable area, each containing its
            outline, area, NDVI values, vegetation loss and
            confidence. The list is ordered largest first.

        Why this exists:

            A confirmed mask covers a whole Sentinel-2 tile,
            roughly 110 km square. Summing every confirmed
            pixel in it produces a single total that mixes
            unrelated events together, and compares that
            total against the 0.5 hectare minimum rather
            than comparing each clearing against it. The
            minimum then passes automatically, because a
            tile-wide total is always large, and the
            isolated noise pixels the rule exists to remove
            are counted as deforestation instead.

            Grouping the mask into contiguous patches first
            applies the rule as intended: each clearing is
            measured on its own, and anything under half a
            hectare is discarded.

            It also gives every detection an outline that
            can be drawn on a map and tested against a
            reserve boundary, which a tile-wide total cannot
            provide.

        Pixels are grouped using 8-connectivity, so a
        clearing that runs diagonally across the grid stays
        a single patch rather than breaking into fragments.
        """

        (
            previous,
            latest,
            confirmed_mask,
            transform,
            crs,
            pixel_area_m2,
        ) = self.read_analysis_rasters(
            previous_ndvi_path=previous_ndvi_path,
            latest_ndvi_path=latest_ndvi_path,
            confirmed_mask_path=confirmed_mask_path,
        )

        srid = self.utm_srid_from_crs(crs)

        confirmed = confirmed_mask == 1

        if not np.any(confirmed):
            return []

        # -------------------------------------------------
        # NDVI values that were actually measurable
        # -------------------------------------------------

        measurable = (
            np.isfinite(previous)
            & np.isfinite(latest)
            & (previous != NDVI_NODATA)
            & (latest != NDVI_NODATA)
        )

        minimum_area = (
            self.settings.min_detection_area_hectares
        )

        pixel_size_x = abs(transform.a)

        pixel_size_y = abs(transform.e)

        origin_x = transform.c

        origin_y = transform.f

        patches: list[dict] = []

        # -------------------------------------------------
        # Vectorise the mask into contiguous outlines
        # -------------------------------------------------

        for geometry_dict, value in shapes(
            confirmed_mask,
            mask=confirmed,
            transform=transform,
            connectivity=8,
        ):

            if value != 1:
                continue

            polygon = shape(geometry_dict)

            # ---------------------------------------------
            # Discard clearings below the minimum area
            #
            # 0.5 hectares is 50 Sentinel-2 pixels at 10 m.
            # The figure is taken from the area criterion in
            # the Forests Act No. 4 of 2015; see the note in
            # core/config.py for what that does and does not
            # mean, including why a patch of exactly 50
            # pixels is kept.
            #
            # Checking here, per clearing, is the whole
            # point of this method: applying the threshold
            # to a whole tile instead would let a scatter of
            # sub-threshold noise sum into a false detection.
            # ---------------------------------------------

            area_hectares = polygon.area / 10_000.0

            if area_hectares < minimum_area:
                continue

            # ---------------------------------------------
            # Read only the pixels beneath this patch
            #
            # Outlines produced by shapes() follow pixel
            # edges exactly, so converting their bounds to
            # row and column indices is exact.
            # ---------------------------------------------

            min_x, min_y, max_x, max_y = polygon.bounds

            column_start = int(
                round((min_x - origin_x) / pixel_size_x)
            )

            column_stop = int(
                round((max_x - origin_x) / pixel_size_x)
            )

            row_start = int(
                round((origin_y - max_y) / pixel_size_y)
            )

            row_stop = int(
                round((origin_y - min_y) / pixel_size_y)
            )

            window_transform = rasterio.Affine(
                transform.a,
                transform.b,
                origin_x + column_start * pixel_size_x,
                transform.d,
                transform.e,
                origin_y - row_start * pixel_size_y,
            )

            window_shape = (
                row_stop - row_start,
                column_stop - column_start,
            )

            inside_patch = geometry_mask(
                [geometry_dict],
                out_shape=window_shape,
                transform=window_transform,
                invert=True,
            )

            window_measurable = measurable[
                row_start:row_stop,
                column_start:column_stop,
            ]

            usable = inside_patch & window_measurable

            usable_pixels = int(np.count_nonzero(usable))

            if usable_pixels == 0:
                continue

            window_previous = previous[
                row_start:row_stop,
                column_start:column_stop,
            ]

            window_latest = latest[
                row_start:row_stop,
                column_start:column_stop,
            ]

            ndvi_before = float(
                np.mean(
                    window_previous[usable]
                    .astype(np.float64)
                )
            )

            ndvi_after = float(
                np.mean(
                    window_latest[usable]
                    .astype(np.float64)
                )
            )

            patch_pixels = int(
                np.count_nonzero(inside_patch)
            )

            patches.append(
                {
                    "geometry": self.to_multipolygon(
                        polygon,
                        srid,
                    ),
                    "detected_area_hectares": round(
                        usable_pixels
                        * pixel_area_m2
                        / 10_000.0,
                        4,
                    ),
                    "ndvi_before": round(ndvi_before, 6),
                    "ndvi_after": round(ndvi_after, 6),
                    "vegetation_loss_percentage": round(
                        self.vegetation_loss(
                            ndvi_before,
                            ndvi_after,
                        ),
                        2,
                    ),
                    "confidence": round(
                        self.confidence_indicator(
                            measurable_pixels=usable_pixels,
                            patch_pixels=patch_pixels,
                            vegetation_loss_percentage=(
                                self.vegetation_loss(
                                    ndvi_before,
                                    ndvi_after,
                                )
                            ),
                        ),
                        2,
                    ),
                    "confirmed_pixels": float(
                        usable_pixels
                    ),
                }
            )

        # -------------------------------------------------
        # Largest clearing first
        # -------------------------------------------------

        patches.sort(
            key=lambda patch: patch[
                "detected_area_hectares"
            ],
            reverse=True,
        )

        return patches

    # =====================================================
    # GEOMETRY CONVERSION
    # =====================================================

    @staticmethod
    def to_multipolygon(
        polygon: Polygon,
        srid: int,
    ):
        """
        Convert a clearing outline into a storable value.

        Args:
            polygon:
                The clearing outline, as a Shapely Polygon
                or MultiPolygon, in the coordinate system
                identified by srid.
            srid:
                EPSG code of that coordinate system,
                normally 32735 (WGS 84 / UTM zone 35S).

        Returns:
            geoalchemy2.elements.WKBElement:
                The geometry in a form the PostGIS column
                accepts.

        Detection.geometry is declared as MULTIPOLYGON, so a
        single polygon is wrapped rather than stored as a
        different geometry type. Keeping one column type
        avoids every consumer of the map having to handle
        two.

        UTM zone 35S covers the Copperbelt and has metres as
        its unit, so an area computed from these coordinates
        is already in square metres. A geographic system such
        as EPSG:4326 would give an area in square degrees,
        which varies with latitude and cannot be converted
        to hectares by a constant.
        """

        if isinstance(polygon, MultiPolygon):
            multipolygon = polygon

        else:
            multipolygon = MultiPolygon([polygon])

        return from_shape(multipolygon, srid=srid)

    # =====================================================
    # VEGETATION LOSS
    # =====================================================

    @staticmethod
    def vegetation_loss(
        ndvi_before: float,
        ndvi_after: float,
    ) -> float:
        """
        Express an NDVI decline as a percentage of the
        vegetation present beforehand.

        Args:
            ndvi_before:
                Mean NDVI over the patch in the baseline
                period, -1.0 to 1.0.
            ndvi_after:
                Mean NDVI over the same patch in the
                comparison period, -1.0 to 1.0.

        Returns:
            float:
                Proportion of the earlier NDVI that was
                lost, as a percentage from 0.0 to 100.0.

        The decline is expressed relative to what was there
        before, not as a bare difference, because the same
        absolute drop means different things at different
        starting points. A fall of 0.3 from dense canopy at
        0.8 removes under half the signal; the same fall
        from 0.35 removes nearly all of it.

        The divisor is the ABSOLUTE value of ndvi_before, so
        a baseline below zero still yields a positive
        percentage for a further decline rather than
        reversing the sign of the result.

        A baseline of effectively zero returns 0.0 rather
        than dividing. There is no vegetation to lose, and
        the ratio would otherwise be unbounded.

        Bounded to 0-100. A negative result would mean
        vegetation increased, which is not a loss.
        """

        if abs(ndvi_before) <= 1e-9:
            return 0.0

        loss = (
            (ndvi_before - ndvi_after)
            / abs(ndvi_before)
        ) * 100.0

        return max(0.0, min(100.0, loss))

    # =====================================================
    # CONFIDENCE INDICATOR
    # =====================================================

    @staticmethod
    def confidence_indicator(
        measurable_pixels: int,
        patch_pixels: int,
        vegetation_loss_percentage: float,
    ) -> float:
        """
        Combine how much of a clearing could be measured
        with how severe its NDVI decline was.

        Args:
            measurable_pixels:
                Pixels within the patch carrying a reading
                on BOTH dates, so neither was masked.
            patch_pixels:
                Total pixels in the patch, measurable or
                not.
            vegetation_loss_percentage:
                Severity of the decline, 0.0 to 100.0, from
                vegetation_loss.

        Returns:
            float:
                Indicator from 0.0 to 100.0. Returns 0.0
                for an empty patch, which cannot be
                evidence of anything.

        The two inputs answer different questions. Coverage
        asks how much of the patch was actually observed: a
        clearing half hidden by cloud rests on half the
        evidence. Severity asks how pronounced the decline
        was where it could be seen.

        Coverage carries the greater weight because a
        confident reading of a small sample remains a small
        sample, whereas a modest decline observed across a
        whole patch is still a complete observation.

        This is a transparent indicator calculated from two
        stated quantities. It is NOT a machine-learning
        probability, it is not calibrated against verified
        outcomes, and it must not be presented as one. An
        indicator of 80 does not mean eighty detections in a
        hundred are genuine.

        NOTE: The weights are a reasoned choice, not an
        empirical one. Whether they rank detections in the
        order an officer would is a question for the
        Chapter Five evaluation, which can compare the
        indicator against verified and rejected outcomes.
        """

        if patch_pixels == 0:
            return 0.0

        coverage = measurable_pixels / patch_pixels

        strength = vegetation_loss_percentage / 100.0

        confidence = (
            (coverage * COVERAGE_WEIGHT)
            + (strength * SEVERITY_WEIGHT)
        ) * 100.0

        return max(0.0, min(100.0, confidence))

    # =====================================================
    # READ ANALYSIS RASTERS
    # =====================================================

    def read_analysis_rasters(
        self,
        previous_ndvi_path: str | Path,
        latest_ndvi_path: str | Path,
        confirmed_mask_path: str | Path,
    ):
        """
        Open and validate the three rasters an analysis
        produces.

        Returns:
            previous NDVI, latest NDVI, confirmed mask,
            transform, CRS and pixel area in square metres.

        Raises:
            FileNotFoundError:
                One of the rasters is missing, which means
                the processing pipeline did not run.

            ValueError:
                The rasters do not share a grid, so their
                pixels do not describe the same ground and
                cannot be compared.
        """

        previous_ndvi_path = Path(previous_ndvi_path)

        latest_ndvi_path = Path(latest_ndvi_path)

        confirmed_mask_path = Path(confirmed_mask_path)

        for path, name in [
            (previous_ndvi_path, "Previous NDVI"),
            (latest_ndvi_path, "Latest NDVI"),
            (
                confirmed_mask_path,
                "Confirmed deforestation mask",
            ),
        ]:
            if not path.exists():
                raise FileNotFoundError(
                    f"{name} file not found: {path}"
                )

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

            if previous_src.transform != latest_src.transform:
                raise ValueError(
                    "Previous and latest NDVI rasters "
                    "have different spatial transforms."
                )

            if previous_src.transform != mask_src.transform:
                raise ValueError(
                    "NDVI rasters and confirmed mask "
                    "have different spatial transforms."
                )

            if previous_src.crs != latest_src.crs:
                raise ValueError(
                    "Previous and latest NDVI rasters "
                    "have different CRS."
                )

            if previous_src.crs != mask_src.crs:
                raise ValueError(
                    "NDVI rasters and confirmed mask "
                    "have different CRS."
                )

            transform = previous_src.transform

            crs = previous_src.crs

            pixel_area_m2 = (
                abs(transform.a)
                * abs(transform.e)
            )

        return (
            previous,
            latest,
            confirmed_mask,
            transform,
            crs,
            pixel_area_m2,
        )

    # =====================================================
    # CALCULATE SCENE STATISTICS
    # =====================================================

    def calculate_detection_statistics(
        self,
        previous_ndvi_path: str | Path,
        latest_ndvi_path: str | Path,
        confirmed_mask_path: str | Path,
    ) -> dict[str, float]:
        """
        Summarise confirmed change across an ENTIRE scene.

        Args:
            previous_ndvi_path:
                Cloud-masked NDVI from the baseline date.
            latest_ndvi_path:
                Cloud-masked NDVI from the comparison date,
                on the same grid.
            confirmed_mask_path:
                Persistence-confirmed deforestation mask, 1
                where change was confirmed.

        Returns:
            dict[str, float]:
                "detected_area_hectares", the confirmed area
                in hectares; "confidence", the indicator
                from 0.0 to 100.0; "ndvi_before" and
                "ndvi_after", mean NDVI over the confirmed
                pixels on each date, -1.0 to 1.0;
                "vegetation_loss_percentage", 0.0 to 100.0;
                and "confirmed_pixels", the pixel count.
                All zero when no pixel was confirmed.

        Raises:
            FileNotFoundError:
                A raster is missing, meaning the processing
                pipeline did not run.
            ValueError:
                The rasters do not share a grid, so their
                pixels do not describe the same ground; or
                the mask confirms pixels that carry no valid
                NDVI on both dates, which means the mask and
                the NDVI rasters disagree about which pixels
                were measurable and one of them is stale.

        IMPORTANT:
            These figures describe a whole Sentinel-2 tile,
            roughly 110 km square, and mix every confirmed
            pixel in it together. They are a scene-level
            summary for the analysis job record.

            Do NOT create a Detection from them. A detection
            describes one clearing, and is produced by
            extract_detection_patches, which applies the
            minimum detectable area to each clearing
            separately.
        """

        (
            previous,
            latest,
            confirmed_mask,
            _transform,
            _crs,
            pixel_area_m2,
        ) = self.read_analysis_rasters(
            previous_ndvi_path=previous_ndvi_path,
            latest_ndvi_path=latest_ndvi_path,
            confirmed_mask_path=confirmed_mask_path,
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
            & (previous != NDVI_NODATA)
            & (latest != NDVI_NODATA)
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
    ) -> list[Detection]:
        """
        Execute the real deforestation detection workflow.

        Returns:
            One PENDING Detection per confirmed clearing,
            largest first. An empty list means the analysis
            ran and found no clearing large enough to
            report, which is a successful outcome.

        Processing pipeline:

        1. Load previous cloud-masked NDVI.
        2. Load latest cloud-masked NDVI.
        3. Load persistence-confirmed mask.
        4. Group confirmed pixels into separate clearings.
        5. Discard clearings below the minimum area.
        6. Measure each surviving clearing on its own.
        7. Record one PENDING detection for each, with its
           outline.

        A Forestry Officer must review every detection.

        Each clearing becomes its own record because a
        detection is a place an officer may have to visit.
        Merging unrelated clearings from across a 110 km
        tile into one row would describe no single place,
        and would defeat the minimum detectable area by
        adding scattered noise together until it passed.
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
        #
        # Read from application settings so this service and
        # the services that WRITE these rasters
        # (SentinelProcessorService, CloudMaskService and
        # PersistenceService, orchestrated by AnalysisService)
        # always agree on one location.
        # -------------------------------------------------

        storage_root = (
            self.settings.satellite_image_storage_path
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
        # Prevent duplicate detections
        #
        # Re-running an analysis over the same image pair
        # must not create a second copy of every clearing.
        # -------------------------------------------------

        existing_detections = (
            self.db.query(Detection)
            .filter(
                Detection.forest_area_id
                == job.forest_area_id,
                Detection.satellite_image_id
                == job.satellite_image_id,
            )
            .order_by(
                Detection.detected_area_hectares.desc(),
            )
            .all()
        )

        if existing_detections:
            return existing_detections

        # -------------------------------------------------
        # Split the confirmed mask into separate clearings
        #
        # Each clearing is measured on its own and anything
        # below the minimum detectable area is discarded
        # inside extract_detection_patches.
        #
        # An empty list is a valid outcome, not a failure:
        # the analysis ran and confirmed no deforestation
        # large enough to report. The job still completes.
        # -------------------------------------------------

        patches = self.extract_detection_patches(
            previous_ndvi_path=previous_ndvi,
            latest_ndvi_path=latest_ndvi,
            confirmed_mask_path=confirmed_mask,
        )

        if not patches:
            return []

        # -------------------------------------------------
        # Record one detection per clearing
        # -------------------------------------------------

        detections = [
            self.create_detection(
                job=job,
                detected_area=patch[
                    "detected_area_hectares"
                ],
                confidence=patch["confidence"],
                ndvi_before=patch["ndvi_before"],
                ndvi_after=patch["ndvi_after"],
                vegetation_loss=patch[
                    "vegetation_loss_percentage"
                ],
                geometry=patch["geometry"],
            )
            for patch in patches
        ]

        return detections