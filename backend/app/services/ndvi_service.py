"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: NDVI Service

Purpose:
    Calculates NDVI from Sentinel-2 imagery.

Responsibilities:
    - Read Sentinel-2 bands.
    - Calculate NDVI.
    - Save NDVI raster.
    - Compare NDVI images.
    - Flag significant vegetation decline.
    - Calculate NDVI statistics.

Note:
    calculate_ndvi and flag_change are deliberately pure
    array operations with no file access. They hold the
    two formulas the detection results depend on, so they
    can be verified directly against hand-calculated
    values in the test suite.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio


class NDVIService:
    """
    Performs NDVI calculations using
    Sentinel-2 imagery.
    """

    # ---------------------------------------------------------
    # Read Raster Band
    # ---------------------------------------------------------
    def read_band(
        self,
        band_path: Path,
    ) -> tuple[np.ndarray, dict]:
        """
        Read a Sentinel-2 raster band and its georeference.

        Args:
            band_path:
                Path to a single-band GeoTIFF or JP2, such
                as an extracted B4 or B8 file.

        Returns:
            tuple[np.ndarray, dict]:
                The first band as a 2-D float32 array, and
                the rasterio profile describing its CRS,
                transform, dimensions and nodata value.

        Raises:
            rasterio.errors.RasterioIOError:
                The file is absent or not a raster rasterio
                can open.

        Only band 1 is read, because Sentinel-2 bands are
        distributed one band per file.

        The array is cast to float32 on read. Reflectance is
        stored as scaled integers, and NDVI is a ratio: left
        as integers the division would truncate toward zero
        and return an array of 0 and 1 rather than a
        continuous index. float32 also allows np.nan to mark
        pixels with no reading, which an integer array
        cannot represent.
        """

        with rasterio.open(band_path) as src:

            image = src.read(1).astype("float32")

            profile = src.profile

        return image, profile

    # ---------------------------------------------------------
    # Calculate NDVI
    # ---------------------------------------------------------
    def calculate_ndvi(
        self,
        red_band: np.ndarray,
        nir_band: np.ndarray,
    ) -> np.ndarray:
        """
        Calculate NDVI from red and near-infrared bands.

        Args:
            red_band:
                Red reflectance, Sentinel-2 band B4 at 10 m
                resolution, as a 2-D array.
            nir_band:
                Near-infrared reflectance, Sentinel-2 band
                B8 at 10 m resolution, as a 2-D array of the
                same shape and grid as red_band.

        Returns:
            np.ndarray:
                NDVI per pixel, in the range -1.0 to 1.0,
                with np.nan wherever the index is undefined.

        Formula:

            (NIR - RED)
            -----------
            (NIR + RED)

        Why these two bands:
            Healthy vegetation absorbs red light for
            photosynthesis and reflects near-infrared
            strongly, so the difference between B8 and B4 is
            large over canopy and small over bare ground.
            Dividing by their sum normalises the result
            against illumination, so a slope in shadow and
            the same canopy in full sun give comparable
            readings. Both bands are 10 m, so neither has to
            be resampled and no resampling artefact is
            introduced into the ratio.

        Range:
            The result is bounded to -1.0 to 1.0 by the
            formula itself. Dense canopy in the Copperbelt
            reads roughly 0.6 to 0.9; bare or recently
            cleared ground reads roughly 0.1 to 0.3; water
            reads below zero.

        Undefined pixels:
            Where NIR and red sum to zero the index has no
            value, so the denominator is set to np.nan and
            the division yields np.nan rather than raising
            or returning infinity. This happens where both
            bands read zero, which is outside the captured
            swath or in a band gap rather than on real
            ground. Callers must treat np.nan as "no
            reading" and exclude it, not as low vegetation:
            counted as a number it would read as severe
            loss.

        NOTE: np.seterr is called here and changes NumPy's
        error handling for the whole process, not only for
        this calculation. A divide or overflow warning
        raised by unrelated code elsewhere is silenced as a
        side effect. Scoping it with np.errstate as a
        context manager would confine it to this operation.
        """

        np.seterr(
            divide="ignore",
            invalid="ignore",
        )

        denominator = nir_band + red_band

        denominator[denominator == 0] = np.nan

        ndvi = (
            (nir_band - red_band)
            / denominator
        )

        return ndvi

    # ---------------------------------------------------------
    # Save NDVI
    # ---------------------------------------------------------
    def save_ndvi(
        self,
        ndvi: np.ndarray,
        profile: dict,
        output_path: Path,
    ) -> Path:
        """
        Write an NDVI array to a GeoTIFF.

        Args:
            ndvi:
                NDVI values in the range -1.0 to 1.0, with
                np.nan where there is no reading.
            profile:
                The rasterio profile of the band the NDVI
                was derived from. Copied before it is
                altered, so the caller's profile is left
                usable for a second write.
            output_path:
                Destination file. Parent directories are
                created if absent.

        Returns:
            Path:
                The path written to, so the caller can pass
                it on without rebuilding it.

        Raises:
            rasterio.errors.RasterioIOError:
                The destination cannot be written.

        The profile is carried over from the source band so
        the NDVI raster keeps the same CRS, transform and
        pixel grid. A later stage compares this raster with
        another pixel by pixel, which is only valid while
        both describe the same ground in the same grid.

        Written as a single float32 band with LZW
        compression. float32 preserves the fractional index
        and carries np.nan; LZW is lossless, so the stored
        values are the computed ones rather than an
        approximation of them.
        """

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        profile = profile.copy()

        profile.update(
            dtype="float32",
            count=1,
            compress="lzw",
        )

        with rasterio.open(
            output_path,
            "w",
            **profile,
        ) as dst:

            dst.write(
                ndvi.astype("float32"),
                1,
            )

        return output_path

    # ---------------------------------------------------------
    # Calculate NDVI Change
    # ---------------------------------------------------------
    def calculate_change(
        self,
        previous_ndvi: np.ndarray,
        current_ndvi: np.ndarray,
    ) -> np.ndarray:
        """
        Calculate signed NDVI change between two dates.

        Args:
            previous_ndvi:
                NDVI from the baseline period, -1.0 to 1.0.
            current_ndvi:
                NDVI from the comparison period, on the
                same pixel grid as previous_ndvi.

        Returns:
            np.ndarray:
                current minus previous, so a NEGATIVE value
                means vegetation was lost and a positive
                value means it grew. Range -2.0 to 2.0.
                np.nan propagates from either input.

        CAUTION: This is the opposite sign convention to
        flag_change, which expects DECLINE, calculated as
        previous minus current, where a POSITIVE value means
        loss. The output of this method must be negated
        before it is passed to flag_change; handing it over
        unchanged would flag vegetation growth as
        deforestation and ignore every real clearing.

        Both inputs must describe the same ground in the
        same pixel grid. Nothing here verifies that, because
        the arrays carry no georeference: alignment is the
        responsibility of the stage that produced them.
        """

        return current_ndvi - previous_ndvi

    # ---------------------------------------------------------
    # Flag Significant Vegetation Decline
    # ---------------------------------------------------------
    def flag_change(
        self,
        ndvi_decline: np.ndarray,
        threshold: float,
    ) -> np.ndarray:
        """
        Flag pixels whose NDVI decline reaches a threshold.

        Args:
            ndvi_decline:
                Array of NDVI DECLINE values, calculated as

                    previous NDVI - latest NDVI

                so that a positive value means vegetation
                was lost.

            threshold:
                Minimum decline required before a pixel is
                treated as possible deforestation.

        Returns:
            A uint8 array where 1 marks a flagged pixel and
            0 marks an unflagged one.

        This is the single decision rule behind change
        detection, kept as a pure array operation so it can
        be tested directly against hand-calculated values
        without reading or writing any raster file.

        Non-finite values never flag: a pixel that could not
        be measured is not evidence of vegetation loss.
        """

        if threshold <= 0:
            raise ValueError(
                "NDVI decline threshold must be "
                "greater than zero."
            )

        flagged = np.zeros(
            ndvi_decline.shape,
            dtype=np.uint8,
        )

        measurable = np.isfinite(
            ndvi_decline
        )

        flagged[
            measurable
            & (
                ndvi_decline
                >= threshold
            )
        ] = 1

        return flagged

    # ---------------------------------------------------------
    # Calculate Statistics
    # ---------------------------------------------------------
    def calculate_statistics(
        self,
        ndvi: np.ndarray,
    ) -> dict[str, float]:
        """
        Summarise an NDVI or NDVI-change raster.

        Args:
            ndvi:
                NDVI values (-1.0 to 1.0) or NDVI change
                values (-2.0 to 2.0). Non-finite entries
                are excluded.

        Returns:
            dict[str, float]:
                "minimum", "maximum", "mean" and "std" over
                the finite pixels only. All four are 0.0
                when no pixel carries a reading.

        Non-finite pixels are excluded rather than treated
        as zero. Cloud, shadow and out-of-swath ground are
        stored as np.nan, and averaging them in as 0.0 would
        drag the mean toward bare ground and report
        vegetation loss proportional to how cloudy the scene
        was.

        NOTE: A fully masked raster returns zeros, which are
        indistinguishable from a real reading of 0.0 across
        the scene. Callers cannot tell "no usable data" from
        "uniformly bare ground" without checking the valid
        pixel count separately.
        """

        valid_pixels = ndvi[np.isfinite(ndvi)]

        if valid_pixels.size == 0:

            return {
                "minimum": 0.0,
                "maximum": 0.0,
                "mean": 0.0,
                "std": 0.0,
            }

        return {
            "minimum": float(
                np.min(valid_pixels)
            ),
            "maximum": float(
                np.max(valid_pixels)
            ),
            "mean": float(
                np.mean(valid_pixels)
            ),
            "std": float(
                np.std(valid_pixels)
            ),
        }

    # ---------------------------------------------------------
    # Process NDVI
    # ---------------------------------------------------------
    def process_ndvi(
        self,
        red_band_path: Path,
        nir_band_path: Path,
        output_path: Path,
    ) -> tuple[
        np.ndarray,
        dict[str, float],
        Path,
    ]:
        """
        Compute NDVI from two band files and write it out.

        Args:
            red_band_path:
                Sentinel-2 band B4 (red) at 10 m.
            nir_band_path:
                Sentinel-2 band B8 (near-infrared) at 10 m,
                covering the same tile as the red band.
            output_path:
                Destination for the NDVI GeoTIFF.

        Returns:
            tuple[np.ndarray, dict[str, float], Path]:
                The NDVI array, its summary statistics, and
                the path written to.

        Raises:
            rasterio.errors.RasterioIOError:
                A band cannot be read, or the output cannot
                be written.
            ValueError:
                The two bands differ in shape, so they
                cannot be combined pixel by pixel.

        The profile of the red band is reused for the
        output, so the NDVI raster inherits its CRS,
        transform and grid. B4 and B8 are both 10 m and
        share a grid within a tile, so neither is resampled.
        """

        # ---------------------------------------------
        # Read Sentinel-2 bands
        # ---------------------------------------------
        red_band, profile = self.read_band(
            red_band_path,
        )

        nir_band, _ = self.read_band(
            nir_band_path,
        )

        # ---------------------------------------------
        # Calculate NDVI
        # ---------------------------------------------
        ndvi = self.calculate_ndvi(
            red_band,
            nir_band,
        )

        # ---------------------------------------------
        # Save NDVI
        # ---------------------------------------------
        output_file = self.save_ndvi(
            ndvi,
            profile,
            output_path,
        )

        # ---------------------------------------------
        # Calculate statistics
        # ---------------------------------------------
        statistics = self.calculate_statistics(
            ndvi,
        )

        return (
            ndvi,
            statistics,
            output_file,
        )

    # ---------------------------------------------------------
    # Compare NDVI Images
    # ---------------------------------------------------------
    def compare_ndvi(
        self,
        previous_ndvi: np.ndarray,
        current_ndvi: np.ndarray,
    ) -> tuple[
        np.ndarray,
        dict[str, float],
    ]:
        """
        Compare two NDVI rasters and summarise the change.

        Args:
            previous_ndvi:
                NDVI from the baseline period.
            current_ndvi:
                NDVI from the comparison period, on the
                same pixel grid.

        Returns:
            tuple[np.ndarray, dict[str, float]]:
                The signed change raster and its summary
                statistics.

        Raises:
            ValueError:
                The two arrays differ in shape.

        The change carries the sign convention of
        calculate_change: negative means vegetation was
        lost. See the caution on that method before passing
        this result to flag_change, which expects the
        opposite sign.

        The two periods compared should be EQUIVALENT
        SEASONAL WINDOWS IN DIFFERENT YEARS, for example
        May to July 2024 against May to July 2025. Miombo
        woodland in the Copperbelt sheds leaves across the
        whole province every dry season, so comparing
        adjacent months would show NDVI falling everywhere
        and report deforestation across ground where nothing
        was cleared. Nothing in this method enforces that;
        it is a property of the windows the caller selects.

        NOTE: Neither this method nor calculate_change is
        called by the detection pipeline. PersistenceService
        computes the decline directly as previous minus
        latest and passes it to flag_change, so the sign
        convention here is not currently exercised by any
        production path or test. Either route the pipeline
        through these methods or remove them; an untested
        helper whose sign is the reverse of the one the
        pipeline uses is a trap for the next caller.
        """

        change = self.calculate_change(
            previous_ndvi,
            current_ndvi,
        )

        statistics = self.calculate_statistics(
            change,
        )

        return (
            change,
            statistics,
        )