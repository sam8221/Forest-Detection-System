"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Raster Render Service

Purpose:
    Turns the NDVI rasters the pipeline produced into web
    map overlays, histograms and point samples.

Responsibilities:
    - Locate the rasters belonging to a forest area.
    - Colour NDVI and NDVI change for display.
    - Report the overlay's bounds in WGS 84.
    - Summarise the distribution of valid pixels.
    - Read the value under a clicked coordinate.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    All raster work happens here, in the backend. A
    Sentinel-2 tile is 10980 by 10980 pixels, about 480 MB
    as float32, and sending that to a browser to be coloured
    would be unusable. Every read is decimated to a display
    size first, which rasterio does while reading rather
    than afterwards, so the full array is never held.

    Nothing here is generated. Each layer is read from a
    file the detection pipeline wrote, and a request for a
    layer that was never produced reports its absence
    instead of returning an empty image that would look like
    measured ground with no vegetation.

Version:
    1.0.0
===========================================================
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.warp import transform_bounds

from app.core.config import get_settings
from app.core.constants import NDVI_NODATA
from app.services.storage_paths import resolve_layer


# =========================================================
# GEOGRAPHIC COORDINATE SYSTEM
#
# Web maps place overlays in WGS 84 geographic coordinates,
# so raster bounds and clicked points are converted to it.
#
# Built from a PROJ definition rather than the EPSG code,
# for the reason SentinelProcessorService and
# DetectionService already document: a PostGIS install on
# the developer machine puts an older proj.db ahead of the
# one rasterio expects, and resolving "EPSG:4326" fails with
#
#     proj.db contains DATABASE.LAYOUT.VERSION.MINOR = 2
#     whereas a number >= 6 is expected
#
# A PROJ string is self-contained and needs no database.
# =========================================================

WGS84_CRS = CRS.from_proj4(
    "+proj=longlat +datum=WGS84 +no_defs"
)


# =========================================================
# LAYERS
#
# Where each layer lives under a forest area's directory,
# and how its values should be read.
#
# The pipeline writes these paths; this service only reads
# them. "difference" carries the pipeline's sign convention,
# previous minus latest, so a POSITIVE value means
# vegetation was LOST. That is the opposite of what the word
# "difference" suggests to most readers, which is exactly
# why the colour scale for it is defined separately below
# and why the API states the convention in its response.
# =========================================================

@dataclass(frozen=True)
class LayerDefinition:
    """One displayable raster and how to interpret it."""

    key: str
    relative_path: str
    palette: str
    label: str
    description: str


LAYERS: dict[str, LayerDefinition] = {
    "ndvi_current": LayerDefinition(
        key="ndvi_current",
        relative_path="processing/masked_ndvi/ndvi_masked.tif",
        palette="ndvi",
        label="NDVI, later observation",
        description=(
            "Vegetation index for the comparison period. "
            "Red is bare or built ground, green is dense "
            "vegetation. Cloud and shadow are already removed."
        ),
    ),
    "ndvi_previous": LayerDefinition(
        key="ndvi_previous",
        relative_path=(
            "processing_previous/masked_ndvi/ndvi_masked.tif"
        ),
        palette="ndvi",
        label="NDVI, earlier observation",
        description=(
            "Vegetation index for the baseline period, on the "
            "same colour scale as the later observation so "
            "the two can be compared by eye."
        ),
    ),
    "ndvi_difference": LayerDefinition(
        key="ndvi_difference",
        relative_path="persistence/ndvi_difference/ndvi_change.tif",
        palette="difference",
        label="NDVI change, potential vegetation loss",
        description=(
            "Earlier NDVI minus later NDVI, so a POSITIVE "
            "value means vegetation was lost. Red marks "
            "decline, pale marks little change, green marks "
            "growth. A decline is not by itself deforestation."
        ),
    ),
    "confirmed_loss": LayerDefinition(
        key="confirmed_loss",
        relative_path=(
            "persistence/persistence/confirmed_deforestation.tif"
        ),
        palette="confirmed",
        label="Potential loss, past threshold",
        description=(
            "Pixels whose decline reached the analysis "
            "threshold and persisted. These are candidates "
            "for review, not verified clearing."
        ),
    ),
}


# =========================================================
# COLOUR RAMPS
#
# Stops are (value, red, green, blue). Values between stops
# are interpolated, so the ramp is continuous rather than
# banded, and a reader can judge magnitude from the colour
# rather than only its category.
# =========================================================

NDVI_STOPS = [
    (-1.00, 165, 42, 32),     # deep red: water, built, bare
    (0.05, 200, 76, 48),      # red
    (0.20, 232, 150, 60),     # orange
    (0.35, 243, 214, 88),     # yellow
    (0.50, 166, 207, 94),     # light green
    (0.70, 72, 150, 62),      # green
    (1.00, 21, 82, 38),       # dark green: dense canopy
]

# Diverging, centred on no change. Decline is red because
# that is what an officer is looking for; growth is green;
# the middle is deliberately pale so small fluctuations do
# not read as events.
DIFFERENCE_STOPS = [
    (-0.60, 21, 110, 60),     # NDVI rose: growth
    (-0.15, 150, 200, 160),
    (-0.03, 242, 244, 240),   # effectively unchanged
    (0.03, 242, 244, 240),
    (0.15, 240, 170, 90),     # modest decline
    (0.35, 214, 92, 48),      # marked decline
    (0.60, 150, 24, 24),      # severe decline
]


def _ramp(values: np.ndarray, stops) -> np.ndarray:
    """
    Map values to RGB by interpolating between stops.

    Returns an array shaped (height, width, 3) of uint8.
    """

    positions = np.array([stop[0] for stop in stops])

    channels = [
        np.array([stop[index] for stop in stops], dtype="float32")
        for index in (1, 2, 3)
    ]

    clipped = np.clip(values, positions[0], positions[-1])

    return np.stack(
        [
            np.interp(clipped, positions, channel)
            for channel in channels
        ],
        axis=-1,
    ).astype("uint8")


def _max_pool(
    array: np.ndarray,
    out_height: int,
    out_width: int,
) -> np.ndarray:
    """
    Reduce an array by taking the maximum of each block.

    Used for presence masks, where a block containing any
    flagged pixel must stay flagged. np.maximum.reduceat
    takes segment start indices, so blocks need not divide
    the input evenly.
    """

    if array.shape[0] <= out_height and array.shape[1] <= out_width:
        return array

    rows = np.linspace(
        0, array.shape[0], out_height + 1
    ).astype(int)[:-1]

    columns = np.linspace(
        0, array.shape[1], out_width + 1
    ).astype(int)[:-1]

    pooled = np.maximum.reduceat(array, rows, axis=0)

    return np.maximum.reduceat(pooled, columns, axis=1)


class RasterRenderService:
    """
    Renders stored rasters for the monitoring map.
    """

    #: Longest edge of a generated overlay. Keeps a tile that
    #: is 10980 pixels across down to something a browser can
    #: hold, while staying sharp at the zoom levels a forest
    #: area is viewed at.
    MAX_DISPLAY_SIZE = 1024

    #: Pixels sampled when building a histogram. Enough for a
    #: stable distribution without reading the whole tile.
    HISTOGRAM_SAMPLE_SIZE = 2048

    def __init__(self) -> None:
        self.settings = get_settings()

    # =====================================================
    # LOCATION
    # =====================================================

    def layer_path(
        self,
        forest_area_id: int,
        layer: str,
        job_id: int | None = None,
    ) -> Path | None:
        """
        Return the file for a layer, or None if absent.

        Absent means the pipeline has not produced it for
        this forest area: either no analysis has run, or the
        run did not reach that stage.
        """

        definition = LAYERS.get(layer)

        if definition is None:
            return None

        path, _ = resolve_layer(
            forest_area_id=forest_area_id,
            job_id=job_id,
            relative_path=definition.relative_path,
            # This service's own configured root, rather
            # than letting the resolver read the settings
            # again, so writer and readers cannot diverge.
            storage_root=(
                self.settings.satellite_image_storage_path
            ),
        )

        return path

    def available_layers(
        self,
        forest_area_id: int,
        job_id: int | None = None,
    ) -> list[dict]:
        """
        Report which layers exist for a forest area.

        The interface uses this to build its layer control, so
        it only ever offers a layer that can actually be
        drawn.
        """

        available = []

        for definition in LAYERS.values():
            path = self.layer_path(
                forest_area_id, definition.key, job_id
            )

            available.append(
                {
                    "key": definition.key,
                    "label": definition.label,
                    "description": definition.description,
                    "palette": definition.palette,
                    "available": path is not None,
                }
            )

        return available

    # =====================================================
    # RENDERING
    # =====================================================

    def render(
        self,
        forest_area_id: int,
        layer: str,
        job_id: int | None = None,
    ) -> tuple[bytes, list[float], dict] | None:
        """
        Colour a layer and return it as a PNG with bounds.

        Returns:
            (png_bytes, bounds, metadata), where bounds is
            [west, south, east, north] in EPSG:4326 for the
            map to place the overlay, or None when the layer
            does not exist for this area.

        The read is decimated to MAX_DISPLAY_SIZE as it
        happens, so the full tile never enters memory.

        Invalid pixels are made fully transparent rather than
        coloured. A cloud-masked gap drawn in the lowest
        colour of the ramp would be indistinguishable from
        bare ground, which is the one reading the officer
        must not be given.
        """

        definition = LAYERS.get(layer)
        path = self.layer_path(forest_area_id, layer, job_id)

        if definition is None or path is None:
            return None

        with rasterio.open(path) as source:

            scale = max(
                source.width / self.MAX_DISPLAY_SIZE,
                source.height / self.MAX_DISPLAY_SIZE,
                1.0,
            )

            width = int(source.width / scale)
            height = int(source.height / scale)

            if definition.palette == "confirmed":

                # A continuous index averages sensibly when
                # decimated. A 0/1 mask does not: averaging a
                # block that is only part flagged gives a
                # fraction that is neither, and small
                # clearings vanish. Nearest would drop them
                # too, by sampling one pixel per block.
                #
                # So the mask is read at several times the
                # display size and reduced by taking the
                # maximum of each block, which keeps a
                # clearing visible wherever one pixel in the
                # block was flagged. That is what this layer
                # is for.
                oversample = 4

                raw = source.read(
                    1,
                    out_shape=(
                        min(source.height, height * oversample),
                        min(source.width, width * oversample),
                    ),
                    resampling=Resampling.nearest,
                ).astype("float32")

                data = _max_pool(raw, height, width)

            else:
                data = source.read(
                    1,
                    out_shape=(height, width),
                    resampling=Resampling.average,
                ).astype("float32")

            bounds = transform_bounds(
                source.crs,
                WGS84_CRS,
                *source.bounds,
                densify_pts=21,
            )

            source_crs = str(source.crs)

        valid = self._valid_mask(data, definition.palette)

        if definition.palette == "confirmed":
            rgb = np.zeros(
                (*data.shape, 3), dtype="uint8"
            )
            rgb[..., 0] = 200
            rgb[..., 1] = 40
            rgb[..., 2] = 40

        elif definition.palette == "difference":
            rgb = _ramp(data, DIFFERENCE_STOPS)

        else:
            rgb = _ramp(data, NDVI_STOPS)

        alpha = np.where(valid, 230, 0).astype("uint8")

        image = Image.fromarray(
            np.dstack([rgb, alpha]),
            mode="RGBA",
        )

        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)

        return (
            buffer.getvalue(),
            [float(value) for value in bounds],
            {
                "layer": definition.key,
                "label": definition.label,
                "description": definition.description,
                "palette": definition.palette,
                "source_crs": source_crs,
                "display_width": width,
                "display_height": height,
                "valid_pixels": int(np.count_nonzero(valid)),
            },
        )

    @staticmethod
    def _valid_mask(data: np.ndarray, palette: str) -> np.ndarray:
        """
        Mark the pixels that carry a reading.

        For the confirmed mask only the flagged pixels are
        drawn, so the rest of the tile stays transparent and
        the basemap shows through.
        """

        if palette == "confirmed":
            # Greater than zero rather than equal to one, so
            # a decimated block that is partly flagged still
            # draws. The layer answers "was anything flagged
            # here", not "was all of it flagged".
            return data > 0

        return (
            np.isfinite(data)
            & (data != NDVI_NODATA)
            & (np.abs(data) <= 2.0)
        )

    # =====================================================
    # HISTOGRAM
    # =====================================================

    def histogram(
        self,
        forest_area_id: int,
        layer: str,
        bins: int = 40,
        job_id: int | None = None,
    ) -> dict | None:
        """
        Return the distribution of valid pixels in a layer.

        Only pixels carrying a reading take part. Counting
        cloud-masked gaps would pile a spike onto whichever
        bin the no-data sentinel falls in and misrepresent
        the whole distribution.
        """

        definition = LAYERS.get(layer)
        path = self.layer_path(forest_area_id, layer, job_id)

        if definition is None or path is None:
            return None

        with rasterio.open(path) as source:

            scale = max(
                source.width / self.HISTOGRAM_SAMPLE_SIZE,
                source.height / self.HISTOGRAM_SAMPLE_SIZE,
                1.0,
            )

            data = source.read(
                1,
                out_shape=(
                    int(source.height / scale),
                    int(source.width / scale),
                ),
                resampling=Resampling.nearest,
            ).astype("float32")

        valid = self._valid_mask(data, definition.palette)

        values = data[valid]

        if values.size == 0:
            return {
                "layer": definition.key,
                "label": definition.label,
                "valid_pixels": 0,
                "bins": [],
                "mean": None,
                "minimum": None,
                "maximum": None,
            }

        span = (
            (-1.0, 1.0)
            if definition.palette == "ndvi"
            else (float(values.min()), float(values.max()))
        )

        counts, edges = np.histogram(
            values,
            bins=bins,
            range=span,
        )

        return {
            "layer": definition.key,
            "label": definition.label,
            "valid_pixels": int(values.size),
            "mean": round(float(values.mean()), 4),
            "minimum": round(float(values.min()), 4),
            "maximum": round(float(values.max()), 4),
            "bins": [
                {
                    "value": round(
                        float((edges[index] + edges[index + 1]) / 2),
                        4,
                    ),
                    "count": int(counts[index]),
                }
                for index in range(len(counts))
            ],
        }

    # =====================================================
    # POINT SAMPLE
    # =====================================================

    def sample(
        self,
        forest_area_id: int,
        longitude: float,
        latitude: float,
        job_id: int | None = None,
    ) -> dict:
        """
        Read every available layer under one coordinate.

        Used when an officer clicks the map. The coordinate
        arrives in WGS 84 and each raster is in its own
        projected system, so the point is transformed per
        raster rather than assuming they share a grid.

        A value of None means the click fell outside the
        raster or on a pixel with no reading. That is
        reported as such: an officer clicking a cloud gap
        must not be shown a number.
        """

        from rasterio.warp import transform as transform_points

        readings: dict[str, float | None] = {}

        for definition in LAYERS.values():

            path = self.layer_path(
                forest_area_id, definition.key, job_id
            )

            if path is None:
                readings[definition.key] = None
                continue

            with rasterio.open(path) as source:

                xs, ys = transform_points(
                    WGS84_CRS,
                    source.crs,
                    [longitude],
                    [latitude],
                )

                row, column = source.index(xs[0], ys[0])

                if not (
                    0 <= row < source.height
                    and 0 <= column < source.width
                ):
                    readings[definition.key] = None
                    continue

                window = rasterio.windows.Window(
                    column, row, 1, 1
                )

                value = float(
                    source.read(1, window=window)[0][0]
                )

            valid = self._valid_mask(
                np.array([[value]], dtype="float32"),
                definition.palette,
            )[0][0]

            readings[definition.key] = (
                round(value, 4) if valid else None
            )

        return {
            "longitude": round(longitude, 6),
            "latitude": round(latitude, 6),
            "readings": readings,
        }
