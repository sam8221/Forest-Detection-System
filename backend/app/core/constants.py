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
