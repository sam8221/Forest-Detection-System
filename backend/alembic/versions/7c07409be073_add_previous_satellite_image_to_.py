"""
Add previous satellite image to analysis jobs

===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Revision: Add previous satellite image to analysis jobs

Revision ID: 7c07409be073
Revises: e91c6f2a4b7e

Purpose:
    Gives an analysis job a second image reference, so it
    records both sides of the comparison it performed.

Changes:
    analysis_jobs.previous_satellite_image_id  added, with
    an index.

Why this is needed:
    NDVI change detection compares two acquisitions. A job
    that stored only one of them recorded the result without
    recording what produced it, which made a detection
    impossible to re-examine later.

    Holding both means a detection can be traced back to the
    exact pair of products behind it, which the accuracy
    evaluation in Chapter Five depends on: a false positive
    can only be explained if the two images that generated it
    can be retrieved.

    The column is nullable, because jobs created before this
    revision have no second image and cannot be given one
    retrospectively.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# =========================================================
# REVISION IDENTIFIERS
# =========================================================

revision: str = "7c07409be073"

down_revision: Union[str, Sequence[str], None] = "e91c6f2a4b7e"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# =========================================================
# UPGRADE
# =========================================================

def upgrade() -> None:
    """
    Add support for two-date satellite-image analysis.

    The existing satellite_image_id represents the latest
    image.

    previous_satellite_image_id represents the baseline
    image used for comparison.
    """

    # -----------------------------------------------------
    # Add previous satellite image
    # -----------------------------------------------------

    op.add_column(
        "analysis_jobs",
        sa.Column(
            "previous_satellite_image_id",
            sa.Integer(),
            nullable=True,
            comment=(
                "Previous Sentinel-2 image used as the "
                "baseline for change detection."
            ),
        ),
    )

    # -----------------------------------------------------
    # Index
    # -----------------------------------------------------

    op.create_index(
        "ix_analysis_jobs_previous_satellite_image_id",
        "analysis_jobs",
        ["previous_satellite_image_id"],
        unique=False,
    )

    # -----------------------------------------------------
    # Foreign key
    # -----------------------------------------------------

    op.create_foreign_key(
        "fk_analysis_jobs_previous_satellite_image_id",
        "analysis_jobs",
        "satellite_images",
        ["previous_satellite_image_id"],
        ["id"],
    )


# =========================================================
# DOWNGRADE
# =========================================================

def downgrade() -> None:
    """
    Remove previous satellite image support.
    """

    op.drop_constraint(
        "fk_analysis_jobs_previous_satellite_image_id",
        "analysis_jobs",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_analysis_jobs_previous_satellite_image_id",
        table_name="analysis_jobs",
    )

    op.drop_column(
        "analysis_jobs",
        "previous_satellite_image_id",
    )