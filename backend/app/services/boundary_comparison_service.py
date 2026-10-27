"""Boundary-scoped rasters used by satellite comparison jobs."""

from __future__ import annotations

import hashlib
import io
import json
import math
from contextlib import ExitStack, nullcontext
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.crs import CRS
from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import to_shape
from rasterio.enums import Resampling
from rasterio.features import geometry_mask, geometry_window
from rasterio.transform import Affine
from rasterio.warp import transform_bounds, transform_geom
from rasterio.vrt import WarpedVRT
from shapely import wkb
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

from app.services.sentinel_processor_service import SentinelProcessorService


WGS84 = CRS.from_proj4(
    "+proj=longlat +datum=WGS84 +no_defs"
)
NDVI_NODATA = -9999.0
MAX_PREVIEW_EDGE = 1024
RGB_BANDS = ("B04", "B03", "B02")


def _shares_pixel_grid(first: Affine, second: Affine) -> bool:
    """Check equal pixel vectors and a whole-pixel origin offset."""

    coefficients = ("a", "b", "d", "e")
    if not all(
        math.isclose(
            getattr(first, name),
            getattr(second, name),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for name in coefficients
    ):
        return False

    column_offset, row_offset = (~first) * (second.c, second.f)
    return all(
        math.isclose(value, round(value), rel_tol=0.0, abs_tol=1e-6)
        for value in (column_offset, row_offset)
    )


def validate_forest_boundary(boundary: BaseGeometry | None) -> BaseGeometry:
    """Reject boundaries that cannot safely constrain raster work."""

    if boundary is None:
        raise ValueError("The selected forest area has no boundary.")
    if boundary.is_empty:
        raise ValueError("The selected forest boundary is empty.")
    if boundary.geom_type != "Polygon":
        raise ValueError("The selected forest boundary must be a polygon.")
    if not boundary.is_valid:
        raise ValueError(
            "The selected forest boundary is invalid: "
            f"{explain_validity(boundary)}. Correct the boundary before analysis."
        )
    if not np.isfinite(boundary.area) or boundary.area <= 0:
        raise ValueError("The selected forest boundary has no measurable area.")
    rings = [boundary.exterior, *boundary.interiors]
    coordinates = np.concatenate(
        [np.asarray(ring.coords, dtype=np.float64) for ring in rings],
        axis=0,
    )
    if not np.isfinite(coordinates).all():
        raise ValueError("The selected forest boundary contains invalid coordinates.")
    if (
        np.any(coordinates[:, 0] < -180.0)
        or np.any(coordinates[:, 0] > 180.0)
        or np.any(coordinates[:, 1] < -90.0)
        or np.any(coordinates[:, 1] > 90.0)
    ):
        raise ValueError("The selected forest boundary is outside EPSG:4326 coordinate limits.")
    return boundary


def validate_stored_forest_boundary(value) -> BaseGeometry:
    """Read and validate a stored PostGIS geometry in the app's EPSG:4326 contract."""

    if value is None:
        raise ValueError("The selected forest area has no boundary.")
    srid = getattr(value, "srid", 4326)
    if srid != 4326:
        raise ValueError(
            "The selected forest boundary must use EPSG:4326 coordinates."
        )
    geometry = to_shape(value) if isinstance(value, WKBElement) else value
    return validate_forest_boundary(geometry)


def boundary_fingerprint(boundary: BaseGeometry) -> str:
    """Stable identifier used to reject results from an edited boundary."""

    normalized = boundary.normalize()
    return hashlib.sha256(wkb.dumps(normalized, hex=False)).hexdigest()


def write_comparison_manifest(
    path: Path,
    *,
    forest_area_id: int,
    job_id: int,
    previous_image_id: int,
    recent_image_id: int,
    boundary: BaseGeometry,
    imagery: dict[str, dict[str, object]],
    figure: dict[str, object] | None = None,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "forest_area_id": forest_area_id,
        "analysis_job_id": job_id,
        "previous_satellite_image_id": previous_image_id,
        "recent_satellite_image_id": recent_image_id,
        "boundary_sha256": boundary_fingerprint(boundary),
        "imagery": imagery,
    }
    if figure is not None:
        manifest["figure"] = figure
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def read_matching_manifest(
    path: Path,
    *,
    forest_area_id: int,
    job_id: int,
    previous_image_id: int,
    recent_image_id: int,
    boundary: BaseGeometry,
) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    expected = {
        "forest_area_id": forest_area_id,
        "analysis_job_id": job_id,
        "previous_satellite_image_id": previous_image_id,
        "recent_satellite_image_id": recent_image_id,
        "boundary_sha256": boundary_fingerprint(boundary),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        return None
    return manifest


def manifest_matches_selected_images(
    manifest: dict[str, object],
    previous_image,
    recent_image,
) -> bool:
    """Bind persisted preview metadata to the exact product rows in the job."""

    imagery = manifest.get("imagery")
    if not isinstance(imagery, dict):
        return False
    for side, image in (("previous", previous_image), ("recent", recent_image)):
        recorded = imagery.get(side)
        if not isinstance(recorded, dict):
            return False
        try:
            expected = {
                "product_id": image.product_id,
                "tile_id": image.tile_id,
                "processing_level": image.processing_level,
                "acquisition_date": image.acquisition_date.isoformat(),
                "cloud_cover_percentage": float(image.cloud_cover_percentage),
            }
            if any(recorded.get(key) != value for key, value in expected.items()):
                return False
        except (AttributeError, TypeError, ValueError):
            return False
    return True


class BoundaryComparisonService:
    """Masks analytical inputs and renders cached actual RGB imagery."""

    def mask_ndvi_pair(
        self,
        previous_path: Path,
        recent_path: Path,
        boundary: BaseGeometry,
        previous_output: Path,
        recent_output: Path,
    ) -> dict[str, object]:
        boundary = validate_forest_boundary(boundary)
        previous_output.parent.mkdir(parents=True, exist_ok=True)
        recent_output.parent.mkdir(parents=True, exist_ok=True)

        with rasterio.open(previous_path) as previous, rasterio.open(recent_path) as recent:
            if previous.crs is None or recent.crs is None:
                raise ValueError("Both NDVI observations must declare or inherit a CRS.")
            if not previous.crs.is_projected:
                raise ValueError("The common NDVI target grid must use a projected metric CRS.")
            if previous.crs.linear_units.lower() not in {
                "metre",
                "meter",
                "metres",
                "meters",
            }:
                raise ValueError("The common NDVI target grid must use metre-based coordinates.")
            if not np.allclose(np.abs(previous.res), (10.0, 10.0), atol=0.05):
                raise ValueError("The common NDVI target grid must use the native 10 m resolution.")
            if (
                not np.isfinite(recent.res).all()
                or recent.res[0] <= 0
                or recent.res[1] <= 0
            ):
                raise ValueError("The recent NDVI observation has an invalid source resolution.")
            grid_crs = previous.crs

            same_grid = (
                recent.crs == previous.crs
                and recent.transform == previous.transform
                and recent.width == previous.width
                and recent.height == previous.height
            )

            projected_boundary = transform_geom(
                WGS84, previous.crs, mapping(boundary), precision=-1
            )
            try:
                window = geometry_window(previous, [projected_boundary]).round_offsets().round_lengths()
            except Exception as exc:
                raise ValueError(
                    "The selected forest boundary does not overlap the Sentinel-2 observations."
                ) from exc

            window = window.intersection(
                rasterio.windows.Window(0, 0, previous.width, previous.height)
            )
            if window.width <= 0 or window.height <= 0:
                raise ValueError(
                    "The selected forest boundary does not overlap the Sentinel-2 observations."
                )

            if same_grid:
                aligned_recent_context = nullcontext(recent)
            else:
                aligned_recent_context = WarpedVRT(
                    recent,
                    crs=previous.crs,
                    transform=previous.transform,
                    width=previous.width,
                    height=previous.height,
                    src_nodata=(
                        recent.nodata
                        if recent.nodata is not None
                        else NDVI_NODATA
                    ),
                    nodata=NDVI_NODATA,
                    resampling=Resampling.bilinear,
                    init_dest_nodata=True,
                )

            with aligned_recent_context as aligned_recent:
                previous_data = previous.read(1, window=window).astype(np.float32)
                recent_data = aligned_recent.read(1, window=window).astype(np.float32)
                transform = previous.window_transform(window)
                inside = geometry_mask(
                    [projected_boundary],
                    out_shape=previous_data.shape,
                    transform=transform,
                    invert=True,
                    all_touched=False,
                )

                previous_valid = np.isfinite(previous_data) & (previous_data > -9990)
                recent_valid = np.isfinite(recent_data) & (recent_data > -9990)
                if previous.nodata is not None:
                    previous_valid &= previous_data != previous.nodata
                if aligned_recent.nodata is not None:
                    recent_valid &= recent_data != aligned_recent.nodata

                inside_count = int(np.count_nonzero(inside))
                common_valid = inside & previous_valid & recent_valid
                common_count = int(np.count_nonzero(common_valid))
                if inside_count == 0:
                    raise ValueError("The selected forest boundary contains no raster pixels.")
                if common_count == 0:
                    raise ValueError(
                        "No clear, valid pixels are available inside the selected forest boundary "
                        "for both observations."
                    )

                mean_previous = float(np.mean(previous_data[common_valid]))
                mean_recent = float(np.mean(recent_data[common_valid]))
                mean_change = float(
                    np.mean(recent_data[common_valid] - previous_data[common_valid])
                )

                previous_data[~(inside & previous_valid)] = NDVI_NODATA
                recent_data[~(inside & recent_valid)] = NDVI_NODATA
                profile = previous.profile.copy()
                profile.pop("blockxsize", None)
                profile.pop("blockysize", None)
                profile.update(
                    height=int(window.height),
                    width=int(window.width),
                    transform=transform,
                    dtype="float32",
                    count=1,
                    nodata=NDVI_NODATA,
                    compress="lzw",
                    tiled=False,
                )
                with rasterio.open(previous_output, "w", **profile) as destination:
                    destination.write(previous_data, 1)
                with rasterio.open(recent_output, "w", **profile) as destination:
                    destination.write(recent_data, 1)

                bounds = transform_bounds(
                    previous.crs,
                    WGS84,
                    *rasterio.windows.bounds(window, previous.transform),
                    densify_pts=21,
                )

        return {
            "bounds": [float(value) for value in bounds],
            "inside_pixels": inside_count,
            "common_valid_pixels": common_count,
            "common_valid_percentage": round(common_count / inside_count * 100.0, 2),
            "crs": str(grid_crs),
            "resolution_m": 10.0,
            "mean_previous_ndvi": round(mean_previous, 4),
            "mean_recent_ndvi": round(mean_recent, 4),
            "mean_ndvi_change": round(mean_change, 4),
        }

    def write_recent_minus_previous_ndvi_change(
        self,
        previous_path: Path,
        recent_path: Path,
        output_path: Path,
    ) -> dict[str, object]:
        """Write the display raster using the conventional recent − previous sign."""

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(previous_path) as previous, rasterio.open(recent_path) as recent:
            if (
                previous.crs != recent.crs
                or previous.transform != recent.transform
                or previous.width != recent.width
                or previous.height != recent.height
                or previous.res != recent.res
            ):
                raise ValueError("Masked NDVI observations do not share an aligned raster grid.")

            previous_values = previous.read(1).astype(np.float32)
            recent_values = recent.read(1).astype(np.float32)
            valid = np.isfinite(previous_values) & np.isfinite(recent_values)
            valid &= (previous_values > -9990) & (recent_values > -9990)
            if previous.nodata is not None:
                valid &= previous_values != previous.nodata
            if recent.nodata is not None:
                valid &= recent_values != recent.nodata
            if not np.any(valid):
                raise ValueError("No common valid pixels are available for NDVI comparison.")

            change = np.full(previous_values.shape, NDVI_NODATA, dtype=np.float32)
            change[valid] = recent_values[valid] - previous_values[valid]
            profile = previous.profile.copy()
            profile.update(dtype="float32", count=1, nodata=NDVI_NODATA, compress="lzw")
            with rasterio.open(output_path, "w", **profile) as destination:
                destination.write(change, 1)

        return {
            "valid_pixels": int(np.count_nonzero(valid)),
            "mean_ndvi_change": round(float(np.mean(change[valid])), 4),
            "sign_convention": "recent_minus_previous",
        }

    def render_rgb_preview(
        self,
        extracted_directory: Path,
        valid_mask_path: Path,
        boundary: BaseGeometry,
        output_path: Path,
    ) -> dict[str, object]:
        """Render a small true-colour PNG from the selected product's B04/B03/B02 bands."""

        boundary = validate_forest_boundary(boundary)
        processor = SentinelProcessorService()
        paths = [processor.find_band(extracted_directory, band) for band in RGB_BANDS]
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with ExitStack() as stack:
            sources = [stack.enter_context(rasterio.open(path)) for path in paths]
            red = sources[0]
            mask = stack.enter_context(rasterio.open(valid_mask_path))

            # The mask is written from this product's NDVI
            # raster, whose CRS has already been resolved from
            # the tile when Sentinel JP2 metadata omits it.
            # Use that CRS for otherwise aligned CRS-less RGB
            # bands, while rejecting a conflicting explicit
            # B04 CRS or an incorrectly aligned target mask.
            target_crs = mask.crs
            if target_crs is None or not target_crs.is_projected:
                raise ValueError("RGB observations must use a projected CRS.")
            if target_crs.linear_units.lower() not in {
                "metre",
                "meter",
                "metres",
                "meters",
            }:
                raise ValueError("RGB observations must use metre-based coordinates.")
            if not np.allclose(np.abs(mask.res), (10.0, 10.0), atol=0.05):
                raise ValueError("The cloud mask must use the target 10 m RGB grid.")
            # The mask is written from this product's NDVI,
            # which is computed only over the forest boundary,
            # so it is a whole-pixel window of the B04 tile
            # rather than the whole of it. What must hold is
            # that the two grids are the same grid: identical
            # pixel size and rotation, offset by a whole number
            # of pixels. Requiring identical dimensions instead
            # would force NDVI back onto the full 10,980-pixel
            # tile and cost minutes per observation.
            if not _shares_pixel_grid(red.transform, mask.transform):
                raise ValueError("B04 and its cloud mask must share the exact target grid.")
            if red.crs is not None and red.crs != target_crs:
                raise ValueError("B04 CRS conflicts with its cloud-mask target grid.")

            aligned_sources = []
            for source in sources:
                options = {
                    "src_crs": source.crs or target_crs,
                    "crs": target_crs,
                    "transform": mask.transform,
                    "width": mask.width,
                    "height": mask.height,
                    # Nearest keeps band values from adjacent
                    # pixels outside the forest boundary from
                    # blending into displayed edge pixels.
                    "resampling": Resampling.nearest,
                    "init_dest_nodata": True,
                }
                if source.nodata is not None:
                    options["src_nodata"] = source.nodata
                    options["nodata"] = source.nodata
                aligned_sources.append(
                    stack.enter_context(WarpedVRT(source, **options))
                )

            projected_boundary = transform_geom(
                WGS84, target_crs, mapping(boundary), precision=-1
            )
            try:
                window = geometry_window(mask, [projected_boundary]).round_offsets().round_lengths()
            except Exception as exc:
                raise ValueError(
                    "The selected forest boundary does not overlap the RGB observation."
                ) from exc
            window = window.intersection(
                rasterio.windows.Window(0, 0, red.width, red.height)
            )
            if window.width <= 0 or window.height <= 0:
                raise ValueError("The selected forest boundary does not overlap the RGB observation.")

            scale = min(1.0, MAX_PREVIEW_EDGE / max(window.width, window.height))
            width = max(1, int(round(window.width * scale)))
            height = max(1, int(round(window.height * scale)))
            out_shape = (height, width)

            channels = []
            band_masks = []
            for source in aligned_sources:
                values = source.read(
                    1,
                    window=window,
                    out_shape=out_shape,
                    # Nearest sampling prevents radiance from outside the
                    # selected boundary blending into visible edge pixels.
                    resampling=Resampling.nearest,
                ).astype(np.float32)
                # L2A reflectance is scaled by 10,000. A fixed stretch
                # keeps the colours comparable between the dates.
                scaled = np.clip(values / 3000.0, 0.0, 1.0) ** (1.0 / 1.1)
                channels.append(np.rint(scaled * 255).astype(np.uint8))
                band_masks.append(
                    source.read_masks(
                        1,
                        window=window,
                        out_shape=out_shape,
                        resampling=Resampling.nearest,
                    )
                    > 0
                )

            mask_values = mask.read(
                1,
                window=window,
                out_shape=out_shape,
                resampling=Resampling.nearest,
            )
            preview_transform = mask.window_transform(window) * Affine.scale(
                window.width / width,
                window.height / height,
            )
            preview_inside = geometry_mask(
                [projected_boundary],
                out_shape=out_shape,
                transform=preview_transform,
                invert=True,
                all_touched=False,
            )
            valid = (mask_values == 1) & preview_inside
            for band_valid in band_masks:
                valid &= band_valid
            inside_pixels = int(np.count_nonzero(preview_inside))
            valid_pixels = int(np.count_nonzero(valid))
            if valid_pixels == 0:
                raise ValueError(
                    "No clear pixels are available inside the selected forest boundary "
                    "for this observation."
                )

            rgba = np.dstack((*channels, np.where(valid, 255, 0).astype(np.uint8)))
            Image.fromarray(rgba, mode="RGBA").save(output_path, format="PNG", optimize=True)
            bounds = transform_bounds(
                target_crs,
                WGS84,
                *rasterio.windows.bounds(window, mask.transform),
                densify_pts=21,
            )

        return {
            "bounds": [float(value) for value in bounds],
            "valid_pixels": valid_pixels,
            "inside_pixels": inside_pixels,
            "valid_percentage": round(valid_pixels / inside_pixels * 100.0, 2)
            if inside_pixels
            else 0.0,
            "display_width": width,
            "display_height": height,
        }
