"""
Add previous satellite image to analysis jobs.

Revision ID: 7c07409be073
Revises: e91c6f2a4b7e
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