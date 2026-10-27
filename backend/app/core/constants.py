"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Processing Constants

Purpose:
    Defines the fixed numeric values shared by the raster
    processing pipeline.

Role in the system:
    Imported by the services that write and read NDVI
    rasters: cloud_mask_service, sentinel_processor_service,
    persistence_service and detection_service. Holding the
    values here means the service that writes a raster and
    the service that later reads it cannot disagree about
    what the pixels mean.

Why these are not in config.py:
    app/core/config.py holds settings an administrator may
    change, such as the NDVI threshold and the minimum
    detection area. The values here are not adjustable.
    Changing NDVI_NODATA would not reinterpret rasters that
    have already been written; it would make the stored
    fill value indistinguishable from real data, and the
    masked pixels would re-enter the statistics as
    vegetation readings. They are therefore constants of
    the data format, not configuration.

Dependencies:
    None. This module imports nothing, so it can be used by
    detection logic that must run without FastAPI, a
    database or a network call.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""

# ---------------------------------------------------------
# NDVI nodata sentinel
#
# Written into NDVI rasters wherever a pixel carries no
# usable reading: cloud, cloud shadow, snow or saturation
# rejected by the Sentinel-2 SCL band, and ground outside
# the requested area.
#
# The value must lie outside the range NDVI can take. NDVI
# is bounded to -1.0 to 1.0 by its own definition,
# (NIR - Red) / (NIR + Red), so -9999.0 cannot collide with
# a genuine reading. A sentinel inside the valid range,
# such as 0.0 or -1.0, would be read back as bare ground
# and counted as vegetation loss.
#
# It is stored as a float because NDVI rasters are written
# as float32. Comparisons against the integer -9999
# evaluate identically in NumPy, so either spelling matches
# the same pixels.
# ---------------------------------------------------------

NDVI_NODATA: float = -9999.0

# ---------------------------------------------------------
# NDVI valid range
#
# The bounds of the index itself, used to reject a raster
# whose values fall outside what NDVI can produce, which
# indicates the reflectance bands were misread or scaled
# incorrectly rather than that the ground is unusual.
# ---------------------------------------------------------

NDVI_MINIMUM: float = -1.0

NDVI_MAXIMUM: float = 1.0


# ---------------------------------------------------------
# Sentinel-2 processing level
#
# The pipeline requires Level-2A: bottom-of-atmosphere
# surface reflectance, which also carries the SCL band the
# cloud mask depends on. Level-1C is top-of-atmosphere and
# has no SCL band, so an L1C product cannot be masked and
# its NDVI is not comparable with an L2A scene's.
#
# The level therefore has to be checked before a product
# enters an analysis. The difficulty is that the same level
# reaches us under several names: the Copernicus OData
# catalogue reports the processingLevel attribute as
# "Level-2A" on some responses, copernicus_service falls
# back to the productType spelling "S2MSI2A" when the
# attribute is absent, and sentinel_service writes the short
# form "L2A" when it registers a product itself.
#
# Comparing against one literal spelling therefore rejected
# genuine Level-2A products depending only on which code
# path registered them. Recognition is done against an
# explicit set of accepted spellings rather than by pattern
# matching, so no Level-1C spelling can ever satisfy it by
# resembling one of these.
# ---------------------------------------------------------

#: The spelling stored for newly registered products.
SENTINEL2_LEVEL_2A: str = "L2A"

#: Accepted spellings of Level-2A, compared after folding to
#: upper case and discarding separators, so that "Level-2A",
#: "level_2a" and "LEVEL-2A" all reduce to "LEVEL2A".
SENTINEL2_LEVEL_2A_SPELLINGS: frozenset[str] = frozenset(
    {
        "L2A",
        "LEVEL2A",
        "S2MSI2A",
        "MSIL2A",
    }
)


def processing_level_key(value: object) -> str:
    """
    Reduce a processing level to its comparable form.

    Folds to upper case and drops every character that is
    not a letter or digit, so the hyphen in "Level-2A" and
    the underscore in "level_2a" do not make two spellings
    of one level look like two levels.
    """

    return "".join(
        character
        for character in str(value).upper()
        if character.isalnum()
    )


def is_level_2a(value: object) -> bool:
    """
    Report whether a recorded processing level is Level-2A.

    Returns False for None, for an empty value and for any
    unrecognised spelling, so a product whose level was
    never recorded is treated as unusable rather than
    assumed to be Level-2A.
    """

    return processing_level_key(value) in SENTINEL2_LEVEL_2A_SPELLINGS


def normalize_processing_level(value: object) -> str:
    """
    Return the spelling to store for a processing level.

    A recognised Level-2A spelling becomes the canonical
    "L2A" so that newly registered products are consistent
    with each other. Anything else is passed through
    unchanged: an unrecognised level is recorded as the
    catalogue reported it, because rewriting it would hide
    what was actually acquired.
    """

    if is_level_2a(value):
        return SENTINEL2_LEVEL_2A

    return str(value)
