"""Render exportable figures from one selected-pair analysis job."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import NamedTuple

import numpy as np
import rasterio
from PIL import Image, ImageDraw, ImageFont, ImageOps
from rasterio.enums import Resampling


NDVI_CLASS_BOUNDARIES = (-1.0, 0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
NDVI_CLASS_COLORS = (
    "#8c510a",
    "#bf812d",
    "#dfc27d",
    "#a6dba0",
    "#5aae61",
    "#1b7837",
)
NDVI_CLASS_LABELS = ("< 0", "0–0.2", "0.2–0.4", "0.4–0.6", "0.6–0.8", "0.8–1")
CHANGE_NEGATIVE = (178, 24, 43)
CHANGE_ZERO = (247, 247, 247)
CHANGE_POSITIVE = (26, 152, 80)
FIGURE_DPI = 200

# A single extreme pixel must not set the stretch for the whole difference
# panel. On a real Copperbelt job, one pixel in 300,517 reached 0.997 while
# 99.9% of the scene sat inside ±0.26, which flattened the map to near-white.
# The display therefore stretches to a high percentile of |difference| and
# saturates beyond it. Saturation is a display choice only: the stored raster
# keeps every original value, and the manifest records the true observed
# extremes alongside the displayed range.
DIFFERENCE_DISPLAY_PERCENTILE = 98.0
# Below this, a scene with no real change would amplify sensor and atmospheric
# noise into an alarming-looking map.
DIFFERENCE_DISPLAY_FLOOR = 0.05
# NDVI is bounded by [-1, 1], so a difference cannot exceed 2 in magnitude.
DIFFERENCE_MAXIMUM_MAGNITUDE = 2.0
DIFFERENCE_HISTOGRAM_BINS = 4000


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        ("arialbd.ttf", "DejaVuSans-Bold.ttf")
        if bold
        else ("arial.ttf", "DejaVuSans.ttf")
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _raster_valid(values: np.ndarray, nodata: float | int | None) -> np.ndarray:
    valid = np.isfinite(values) & (values > -9990)
    if nodata is not None:
        valid &= values != nodata
    return valid


def _read_display_raster(
    path: Path,
    *,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    with rasterio.open(path) as source:
        sampled = source.read(
            1,
            out_shape=(height, width),
            resampling=Resampling.nearest,
            masked=True,
        )
        values = np.asarray(sampled.data, dtype=np.float32)
        valid = ~np.ma.getmaskarray(sampled)
        valid &= _raster_valid(values, source.nodata)
    return values, valid


def _colorize_ndvi(values: np.ndarray, valid: np.ndarray) -> Image.Image:
    """Apply the same six fixed NDVI classes to both observation panels."""

    if np.any(valid & ((values < -1.001) | (values > 1.001))):
        raise ValueError("An NDVI comparison raster contains values outside the physical range [-1, 1].")
    colors = np.asarray(
        [tuple(bytes.fromhex(color.lstrip("#"))) for color in NDVI_CLASS_COLORS],
        dtype=np.uint8,
    )
    class_limits = np.asarray(NDVI_CLASS_BOUNDARIES[1:-1], dtype=np.float32)
    indices = np.searchsorted(class_limits, np.clip(values, -1.0, 1.0), side="right")
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    rgba[..., :3] = colors[indices]
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


class DifferenceRange(NamedTuple):
    """The stretch used to draw panel (d), plus the untouched observed range."""

    display_maximum: float
    observed_minimum: float
    observed_maximum: float
    observed_absolute: float
    saturated_pixels: int
    valid_pixels: int


def _difference_display_range(path: Path) -> DifferenceRange:
    """Stretch panel (d) to a percentile of |difference|, not to one outlier."""

    counts = np.zeros(DIFFERENCE_HISTOGRAM_BINS, dtype=np.int64)
    bins_per_unit = DIFFERENCE_HISTOGRAM_BINS / DIFFERENCE_MAXIMUM_MAGNITUDE
    observed_minimum = math.inf
    observed_maximum = -math.inf
    valid_pixels = 0

    with rasterio.open(path) as source:
        for _, window in source.block_windows(1):
            values = source.read(1, window=window).astype(np.float32, copy=False)
            valid = _raster_valid(values, source.nodata)
            if not np.any(valid):
                continue
            kept = values[valid]
            observed_minimum = min(observed_minimum, float(np.min(kept)))
            observed_maximum = max(observed_maximum, float(np.max(kept)))
            valid_pixels += int(kept.size)
            magnitudes = np.clip(np.abs(kept), 0.0, DIFFERENCE_MAXIMUM_MAGNITUDE)
            indices = np.minimum(
                (magnitudes * bins_per_unit).astype(np.int64),
                DIFFERENCE_HISTOGRAM_BINS - 1,
            )
            counts += np.bincount(indices, minlength=DIFFERENCE_HISTOGRAM_BINS)

    if valid_pixels == 0:
        raise ValueError("The selected-pair NDVI difference has no valid pixels to display.")
    if not math.isfinite(observed_minimum) or not math.isfinite(observed_maximum):
        raise ValueError("The selected-pair NDVI difference contains invalid values.")

    observed_absolute = max(abs(observed_minimum), abs(observed_maximum))
    cumulative = np.cumsum(counts)
    target = DIFFERENCE_DISPLAY_PERCENTILE / 100.0 * valid_pixels
    bin_index = min(
        int(np.searchsorted(cumulative, target, side="left")),
        DIFFERENCE_HISTOGRAM_BINS - 1,
    )
    # Upper edge of the bin, so the stated range covers the percentile.
    display_maximum = max((bin_index + 1) / bins_per_unit, DIFFERENCE_DISPLAY_FLOOR)
    # Never claim a range wider than the data actually spans.
    display_maximum = min(display_maximum, observed_absolute)

    return DifferenceRange(
        display_maximum=display_maximum,
        observed_minimum=observed_minimum,
        observed_maximum=observed_maximum,
        observed_absolute=observed_absolute,
        saturated_pixels=_count_beyond(path, display_maximum),
        valid_pixels=valid_pixels,
    )


def _count_beyond(path: Path, magnitude: float) -> int:
    """Count valid pixels drawn at full colour because they exceed the stretch."""

    if magnitude <= 0:
        return 0
    beyond = 0
    with rasterio.open(path) as source:
        for _, window in source.block_windows(1):
            values = source.read(1, window=window).astype(np.float32, copy=False)
            valid = _raster_valid(values, source.nodata)
            if np.any(valid):
                beyond += int(np.count_nonzero(np.abs(values[valid]) > magnitude))
    return beyond


def _colorize_difference(
    values: np.ndarray,
    valid: np.ndarray,
    maximum_absolute_change: float,
) -> Image.Image:
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    if maximum_absolute_change == 0:
        rgba[..., :3] = CHANGE_ZERO
    else:
        normalized = np.clip(values[valid] / maximum_absolute_change, -1.0, 1.0)
        rendered = np.empty((normalized.size, 3), dtype=np.uint8)
        negative = normalized < 0
        if np.any(negative):
            fraction = (normalized[negative] + 1.0)[:, None]
            rendered[negative] = np.rint(
                np.asarray(CHANGE_NEGATIVE) * (1.0 - fraction)
                + np.asarray(CHANGE_ZERO) * fraction
            ).astype(np.uint8)
        if np.any(~negative):
            fraction = normalized[~negative][:, None]
            rendered[~negative] = np.rint(
                np.asarray(CHANGE_ZERO) * (1.0 - fraction)
                + np.asarray(CHANGE_POSITIVE) * fraction
            ).astype(np.uint8)
        rgba[..., :3][valid] = rendered
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


def _wrap_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    """Break text into lines by measured pixel width rather than by characters."""

    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            line = candidate
            continue
        if line:
            lines.append(line)
        while draw.textlength(word, font=font) > max_width:
            split_at = max(1, int(len(word) * max_width / draw.textlength(word, font=font)))
            lines.append(word[:split_at])
            word = word[split_at:]
        line = word
    if line:
        lines.append(line)
    return lines


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    *,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_spacing: int = 4,
) -> int:
    """Draw text wrapped by measured pixel width and return its final y."""

    x, y = xy
    for line in _wrap_lines(draw, text, font=font, max_width=max_width):
        draw.text((x, y), line, font=font, fill=fill)
        y += draw.textbbox((x, y), line, font=font)[3] - draw.textbbox((x, y), line, font=font)[1] + line_spacing
    return y


def _wrapped_height(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    font: ImageFont.ImageFont,
    max_width: int,
    line_spacing: int = 4,
) -> int:
    """Height _draw_wrapped would occupy, so a panel can be sized before drawing."""

    height = 0
    for line in _wrap_lines(draw, text, font=font, max_width=max_width):
        box = draw.textbbox((0, 0), line, font=font)
        height += box[3] - box[1] + line_spacing
    return height


def _paste_contained(
    canvas: Image.Image,
    source: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    thumbnail = ImageOps.contain(
        source.convert("RGBA"),
        (right - left, bottom - top),
        method=Image.Resampling.LANCZOS,
    )
    position = (
        left + (right - left - thumbnail.width) // 2,
        top + (bottom - top - thumbnail.height) // 2,
    )
    canvas.paste(thumbnail, position, thumbnail.getchannel("A"))


def _gradient_labels(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    maximum: float,
    saturated: bool,
    font: ImageFont.ImageFont,
) -> tuple[str, str, str]:
    """Pick end labels that fit the ramp, dropping the wording when narrow."""

    limit = "≤ −" if saturated else "−"
    upper = "≥ +" if saturated else "+"
    described = (
        f"{limit}{maximum:.4f} · potential decline",
        "0 · little change",
        f"{upper}{maximum:.4f} · increase",
    )
    bare = (f"{limit}{maximum:.4f}", "0", f"{upper}{maximum:.4f}")
    gap = draw.textlength("    ", font=font)
    start, middle, end = (draw.textlength(text, font=font) for text in described)
    # The middle label is centred, so each end has only half the ramp to work
    # with: the three widths summing to less than the ramp is not enough.
    if max(start, end) + gap + middle / 2 <= width / 2:
        return described
    return bare


def _draw_gradient(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    *,
    maximum: float,
    font: ImageFont.ImageFont,
    saturated: bool = False,
) -> None:
    left, top, right, bottom = box
    width = right - left
    height = bottom - top
    if maximum == 0:
        draw.rectangle(box, fill=CHANGE_ZERO)
        draw.rectangle(box, outline="#64748b", width=1)
        draw.text(
            (left + width // 2, bottom + 9),
            "0 · all valid pixels show no measured difference",
            font=font,
            fill="#334155",
            anchor="mm",
        )
        return
    for x in range(width):
        normalized = 2.0 * x / max(1, width - 1) - 1.0
        if normalized < 0:
            fraction = normalized + 1.0
            color = tuple(
                round(a * (1 - fraction) + b * fraction)
                for a, b in zip(CHANGE_NEGATIVE, CHANGE_ZERO)
            )
        else:
            color = tuple(
                round(a * (1 - normalized) + b * normalized)
                for a, b in zip(CHANGE_ZERO, CHANGE_POSITIVE)
            )
        draw.line((left + x, top, left + x, bottom), fill=color)
    draw.rectangle(box, outline="#64748b", width=1)
    text_y = bottom + 9
    texts = _gradient_labels(draw, width=width, maximum=maximum, saturated=saturated, font=font)
    for x, label in zip((left, left + width // 2, right), texts):
        anchor = "mm" if x == left + width // 2 else ("lm" if x == left else "rm")
        draw.text((x, text_y), label, font=font, fill="#334155", anchor=anchor)


class ComparisonFigureService:
    """Build a 2×2 export and the raster panels used by the responsive UI."""

    def render(
        self,
        *,
        previous_rgb_path: Path,
        previous_ndvi_path: Path,
        recent_ndvi_path: Path,
        difference_path: Path,
        output_directory: Path,
        forest_area_id: int,
        forest_area_name: str,
        job_id: int,
        previous_image_id: int,
        recent_image_id: int,
        imagery: dict[str, object],
    ) -> dict[str, object]:
        paths = (previous_rgb_path, previous_ndvi_path, recent_ndvi_path, difference_path)
        if any(not path.is_file() for path in paths):
            raise ValueError("A required job-specific raster or previous RGB image is missing.")

        with rasterio.open(previous_ndvi_path) as previous, rasterio.open(recent_ndvi_path) as recent, rasterio.open(difference_path) as change:
            first_grid = (previous.crs, previous.transform, previous.width, previous.height, previous.res)
            if previous.crs is None or any(
                (source.crs, source.transform, source.width, source.height, source.res) != first_grid
                for source in (recent, change)
            ):
                raise ValueError("The selected-pair figure rasters do not share one aligned CRS, transform, and resolution.")
            raster_crs = str(previous.crs)
            raster_transform = list(previous.transform)[:6]
            raster_width = previous.width
            raster_height = previous.height
            grid = imagery.get("grid")
            grid_bounds = grid.get("bounds") if isinstance(grid, dict) else None
            rgb_bounds = imagery.get("previous", {}).get("bounds") if isinstance(imagery.get("previous"), dict) else None
            if (
                not isinstance(grid_bounds, list)
                or not isinstance(rgb_bounds, list)
                or len(grid_bounds) != 4
                or len(rgb_bounds) != 4
                or not np.allclose(grid_bounds, rgb_bounds, rtol=0, atol=1e-6)
            ):
                raise ValueError("The previous RGB preview and NDVI comparison do not share the same map extent.")

            with Image.open(previous_rgb_path) as previous_rgb_file:
                previous_rgb = previous_rgb_file.convert("RGBA")
            rgb_width, rgb_height = previous_rgb.size
            raster_aspect = previous.width / previous.height
            rgb_aspect = rgb_width / rgb_height
            if not math.isclose(raster_aspect, rgb_aspect, rel_tol=0.01, abs_tol=0.01):
                raise ValueError("The previous RGB preview is not aligned with the selected-pair raster extent.")

            previous_values, previous_valid = _read_display_raster(
                previous_ndvi_path, width=rgb_width, height=rgb_height
            )
            recent_values, recent_valid = _read_display_raster(
                recent_ndvi_path, width=rgb_width, height=rgb_height
            )
            change_values, change_valid = _read_display_raster(
                difference_path, width=rgb_width, height=rgb_height
            )

        if not previous_valid.any() or not recent_valid.any() or not change_valid.any():
            raise ValueError("A required figure panel has no valid forest-boundary pixels.")
        difference_range = _difference_display_range(difference_path)
        maximum_change = difference_range.display_maximum

        panels = (
            ("(a)", "Previous observation · true-colour RGB", "previous", previous_rgb),
            ("(b)", "Previous observation · NDVI", "previous", _colorize_ndvi(previous_values, previous_valid)),
            ("(c)", "Recent observation · NDVI", "recent", _colorize_ndvi(recent_values, recent_valid)),
            ("(d)", "NDVI difference · recent − previous", "difference", _colorize_difference(change_values, change_valid, maximum_change)),
        )

        output_directory.mkdir(parents=True, exist_ok=True)
        panel_assets: dict[str, dict[str, object]] = {}
        for panel_key, image in (
            ("previous_rgb", previous_rgb),
            ("previous_ndvi", panels[1][3]),
            ("recent_ndvi", panels[2][3]),
            ("ndvi_difference", panels[3][3]),
        ):
            panel_path = (
                previous_rgb_path
                if panel_key == "previous_rgb"
                else output_directory / f"{panel_key}_panel.png"
            )
            if panel_key != "previous_rgb":
                image.save(panel_path, format="PNG", optimize=True)
            panel_assets[panel_key] = {
                "filename": panel_path.name,
                "width": image.width,
                "height": image.height,
                "sha256": hashlib.sha256(panel_path.read_bytes()).hexdigest(),
            }
        figure_info: dict[str, object] = {
            "source": {
                "forest_area_id": forest_area_id,
                "analysis_job_id": job_id,
                "previous_satellite_image_id": previous_image_id,
                "recent_satellite_image_id": recent_image_id,
                "previous_product_id": imagery["previous"]["product_id"],
                "recent_product_id": imagery["recent"]["product_id"],
                "previous_acquisition_date": imagery["previous"]["acquisition_date"],
                "recent_acquisition_date": imagery["recent"]["acquisition_date"],
            },
            "ndvi_scale": {
                "boundaries": list(NDVI_CLASS_BOUNDARIES),
                "colors": list(NDVI_CLASS_COLORS),
                "labels": list(NDVI_CLASS_LABELS),
            },
            "difference_scale": {
                "minimum": -maximum_change,
                "maximum": maximum_change,
                "display_maximum_absolute_difference": maximum_change,
                "display_percentile": DIFFERENCE_DISPLAY_PERCENTILE,
                "display_floor": DIFFERENCE_DISPLAY_FLOOR,
                "saturated_pixels": difference_range.saturated_pixels,
                "valid_pixels": difference_range.valid_pixels,
                "maximum_absolute_valid_difference": difference_range.observed_absolute,
                "observed_minimum": difference_range.observed_minimum,
                "observed_maximum": difference_range.observed_maximum,
                "method": (
                    f"Symmetric display stretch at the {DIFFERENCE_DISPLAY_PERCENTILE:g}th percentile of "
                    f"|difference| (floor ±{DIFFERENCE_DISPLAY_FLOOR:g}, never wider than the observed range). "
                    "More extreme pixels are drawn saturated; the stored raster retains every original value."
                ),
                "sign_convention": "recent_minus_previous",
            },
            "metrics": {
                "mean_previous_ndvi": imagery.get("mean_previous_ndvi"),
                "mean_recent_ndvi": imagery.get("mean_recent_ndvi"),
                "mean_ndvi_change": imagery.get("mean_ndvi_change"),
                "valid_comparison_pixels": imagery.get("valid_comparison_pixels"),
                "potential_decline_area_hectares": imagery.get("affected_area_hectares"),
            },
            "pixel_crs": raster_crs,
            "pixel_transform": raster_transform,
            "raster_width": raster_width,
            "raster_height": raster_height,
            "panels": panel_assets,
        }

        figure_path = output_directory / "scientific_comparison.png"
        info = self._render_layout(
            path=figure_path,
            panels=panels,
            imagery=imagery,
            forest_area_name=forest_area_name,
            job_id=job_id,
            difference_range=difference_range,
            columns=2,
            rows=2,
            canvas_width=2400,
        )
        info["sha256"] = hashlib.sha256(figure_path.read_bytes()).hexdigest()
        figure_info["desktop"] = info
        return figure_info

    def _footer_text(
        self,
        imagery: dict[str, object],
        difference_range: DifferenceRange,
    ) -> tuple[str, str]:
        """The measured summary and the caveat drawn under the shared legends."""

        mean_previous = imagery.get("mean_previous_ndvi")
        mean_recent = imagery.get("mean_recent_ndvi")
        mean_change = imagery.get("mean_ndvi_change")
        valid_pixels = imagery.get("valid_comparison_pixels")
        affected = imagery.get("affected_area_hectares")
        metric_line = (
            (
                f"Common clear pixels: {int(valid_pixels):,}   ·   "
                f"Mean NDVI previous / recent / change: {float(mean_previous):.3f} / "
                f"{float(mean_recent):.3f} / {float(mean_change):+.3f}   ·   "
                f"Potential vegetation decline: {float(affected):.2f} ha"
            )
            if all(
                value is not None
                for value in (mean_previous, mean_recent, mean_change, valid_pixels, affected)
            )
            else "Summary statistics are unavailable for this job."
        )
        saturated = difference_range.saturated_pixels
        note = (
            "NDVI decline is a potential vegetation-change indicator, not proof of deforestation. "
            f"Panel (d) is stretched to ±{difference_range.display_maximum:.4f}, the "
            f"{DIFFERENCE_DISPLAY_PERCENTILE:g}th percentile of |difference|, so a few extreme pixels "
            f"cannot flatten the map. Observed range {difference_range.observed_minimum:+.4f} to "
            f"{difference_range.observed_maximum:+.4f}; "
            + (
                f"{saturated:,} of {difference_range.valid_pixels:,} valid pixels "
                f"({100.0 * saturated / difference_range.valid_pixels:.2f}%) fall beyond the stretch and "
                "are drawn saturated. "
                if saturated
                else "no valid pixel falls beyond the stretch. "
            )
            + "The stored raster keeps every original value. White/transparent gaps are outside the forest "
            "boundary or excluded by the existing quality masks."
        )
        return metric_line, note

    def _render_layout(
        self,
        *,
        path: Path,
        panels: tuple,
        imagery: dict[str, object],
        forest_area_name: str,
        job_id: int,
        difference_range: DifferenceRange,
        columns: int,
        rows: int,
        canvas_width: int,
    ) -> dict[str, object]:
        maximum_change = difference_range.display_maximum
        margin = 48
        gap = 32
        panel_width = (canvas_width - margin * 2 - gap * (columns - 1)) // columns
        canvas_width = margin * 2 + panel_width * columns + gap * (columns - 1)
        map_height = int(panel_width * 0.62)
        panel_height = map_height + 190
        title_height = 152
        panels_bottom = title_height + margin + rows * panel_height + gap * (rows - 1)

        title_font = _font(34 if columns == 2 else 31, bold=True)
        subtitle_font = _font(23 if columns == 2 else 21)
        panel_title_font = _font(24 if columns == 2 else 23, bold=True)
        small_font = _font(18 if columns == 2 else 19)
        tiny_font = _font(17 if columns == 2 else 18)

        metric_line, note = self._footer_text(imagery, difference_range)
        # The note grows with the number of saturated pixels and the observed
        # range, so the footer is measured rather than assumed, or the closing
        # caveat is clipped off the bottom of the export.
        measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        note_width = (
            (canvas_width - margin - 20) - (canvas_width // 2 + 18)
            if columns == 2
            else canvas_width - margin * 2 - 48
        )
        text_height = sum(
            _wrapped_height(measure, text, font=tiny_font, max_width=note_width, line_spacing=3)
            for text in (metric_line, note)
        )
        footer_height = max(268 if columns == 2 else 430, 163 + text_height)
        canvas_height = panels_bottom + footer_height + margin
        canvas = Image.new("RGB", (canvas_width, canvas_height), "#f1f5f3")
        draw = ImageDraw.Draw(canvas)
        draw.text((margin, 22), "Scientific Sentinel-2 and NDVI comparison", font=title_font, fill="#123b2b")
        draw.text((margin, 68), f"{forest_area_name} · selected-pair analysis job #{job_id}", font=subtitle_font, fill="#334155")
        previous = imagery["previous"]
        recent = imagery["recent"]
        dates_line = (
            f"Previous: {previous['acquisition_date']} ({previous['product_id']})    "
            f"Recent: {recent['acquisition_date']} ({recent['product_id']})"
        )
        _draw_wrapped(
            draw,
            dates_line,
            (margin, 108),
            font=small_font,
            fill="#475569",
            max_width=canvas_width - margin * 2,
            line_spacing=3,
        )

        map_box_height = map_height
        for index, (label, title, side, image) in enumerate(panels):
            row, column = divmod(index, columns)
            x = margin + column * (panel_width + gap)
            y = title_height + margin + row * (panel_height + gap)
            right = x + panel_width
            bottom = y + panel_height
            draw.rounded_rectangle((x, y, right, bottom), radius=18, fill="#ffffff", outline="#cbd5d1", width=2)
            draw.text((x + 20, y + 16), label, font=panel_title_font, fill="#166534")
            draw.text((x + 80, y + 16), title, font=panel_title_font, fill="#0f172a")
            if side in {"previous", "recent"}:
                observation = imagery[side]
                subtitle = (
                    f"{observation['acquisition_date']} · {observation['product_id']} · "
                    f"catalogue cloud {float(observation['cloud_cover_percentage']):.1f}%"
                )
            else:
                subtitle = "Negative = potential decline · near zero = little change · positive = increase"
            _draw_wrapped(
                draw,
                subtitle,
                (x + 20, y + 52),
                font=small_font,
                fill="#475569",
                max_width=panel_width - 40,
                line_spacing=2,
            )
            map_top = y + 118
            map_bottom = map_top + map_box_height
            draw.rounded_rectangle(
                (x + 16, map_top, right - 16, map_bottom),
                radius=8,
                fill="#f8fafc",
                outline="#e2e8f0",
                width=1,
            )
            _paste_contained(canvas, image, (x + 22, map_top + 6, right - 22, map_bottom - 6))
            if side == "difference":
                gradient_width = min(panel_width - 100, 540 if columns == 2 else 620)
                gradient_left = x + (panel_width - gradient_width) // 2
                _draw_gradient(
                    draw,
                    (gradient_left, map_bottom + 10, gradient_left + gradient_width, map_bottom + 26),
                    maximum=maximum_change,
                    font=tiny_font,
                    saturated=bool(difference_range.saturated_pixels),
                )
            else:
                draw.text(
                    (x + 20, map_bottom + 18),
                    "Boundary-clipped · invalid, cloudy and shadowed pixels omitted",
                    font=tiny_font,
                    fill="#475569",
                )

        footer_top = panels_bottom + 14
        footer_left = margin
        footer_right = canvas_width - margin
        draw.rounded_rectangle(
            (footer_left, footer_top, footer_right, canvas_height - margin),
            radius=16,
            fill="#ffffff",
            outline="#cbd5d1",
            width=2,
        )

        if columns == 2:
            separator = canvas_width // 2
            left_box = (footer_left + 20, footer_top + 14, separator - 18, canvas_height - margin - 14)
            right_box = (separator + 18, footer_top + 14, footer_right - 20, canvas_height - margin - 14)
            draw.line((separator, footer_top + 20, separator, canvas_height - margin - 20), fill="#e2e8f0", width=2)
        else:
            left_box = (footer_left + 24, footer_top + 14, footer_right - 24, footer_top + 146)
            right_box = (footer_left + 24, footer_top + 156, footer_right - 24, canvas_height - margin - 12)

        draw.text((left_box[0], left_box[1]), "Shared NDVI classes · same fixed scale in panels (b) and (c)", font=small_font, fill="#0f172a")
        legend_y = left_box[1] + 39
        cell_width = max(1, (left_box[2] - left_box[0]) // len(NDVI_CLASS_COLORS))
        for index, (color, label) in enumerate(zip(NDVI_CLASS_COLORS, NDVI_CLASS_LABELS)):
            cell_x = left_box[0] + index * cell_width
            draw.rectangle((cell_x, legend_y, cell_x + 27, legend_y + 22), fill=color, outline="#64748b", width=1)
            draw.text((cell_x, legend_y + 29), label, font=tiny_font, fill="#334155")

        draw.text((right_box[0], right_box[1]), "NDVI difference scale · recent minus previous", font=small_font, fill="#0f172a")
        diff_width = min(right_box[2] - right_box[0] - 10, 560 if columns == 2 else 800)
        diff_left = right_box[0]
        gradient_top = right_box[1] + 39
        _draw_gradient(
            draw,
            (diff_left, gradient_top, diff_left + diff_width, gradient_top + 20),
            maximum=maximum_change,
            font=tiny_font,
            saturated=bool(difference_range.saturated_pixels),
        )
        note_x = right_box[0]
        note_y = gradient_top + 74
        note_y = _draw_wrapped(
            draw,
            metric_line,
            (note_x, note_y),
            font=tiny_font,
            fill="#123b2b",
            max_width=right_box[2] - right_box[0],
            line_spacing=3,
        )
        note_y += 6
        _draw_wrapped(
            draw,
            note,
            (note_x, note_y),
            font=tiny_font,
            fill="#475569",
            max_width=right_box[2] - right_box[0],
            line_spacing=3,
        )

        path.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(path, format="PNG", dpi=(FIGURE_DPI, FIGURE_DPI), optimize=True)
        return {
            "filename": path.name,
            "width": canvas.width,
            "height": canvas.height,
            "dpi": FIGURE_DPI,
            "layout": f"{rows}x{columns}",
        }
