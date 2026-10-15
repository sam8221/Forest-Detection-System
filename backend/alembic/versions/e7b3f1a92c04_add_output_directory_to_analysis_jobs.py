"""
Record each analysis job's own output directory.

===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Revision: Add output_directory to analysis_jobs

Revision ID: e7b3f1a92c04
Revises: d4a1c6e82b19

Purpose:
    Lets a job record where its rasters were written, so its
    results can be read back years later without depending
    on a directory name computed at read time.

The failure this addresses:

    Outputs were written to a directory named after the
    FOREST AREA, so every analysis overwrote the one before
    it. Only the newest rasters survived, and asking for an
    older job returned the newest rasters under that job's
    observation dates. The numbers and the dates then
    described different observations, which is worse than
    reporting nothing.

    Outputs now go to a directory named after the JOB, which
    is immutable because a job is created before processing
    and its identifier never changes.

Why the column is nullable:

    Jobs that ran before this change have no directory of
    their own, and inventing one would point at files that
    are not there. NULL means "written under the old shared
    layout", which the storage resolver falls back to and
    which the API reports as legacy, so an officer is told
    the rasters may belong to a later analysis of the same
    area.

    No existing row is modified and no file is moved. The
    old outputs remain the only record of those analyses.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------

revision = "e7b3f1a92c04"
down_revision = "d4a1c6e82b19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the nullable output_directory column."""

    op.add_column(
        "analysis_jobs",
        sa.Column(
            "output_directory",
            sa.String(length=500),
            nullable=True,
            comment=(
                "Directory holding this job's raster "
                "outputs, relative to the imagery storage "
                "root. NULL for jobs written under the "
                "pre-job shared layout."
            ),
        ),
    )


def downgrade() -> None:
    """
    Remove the column.

    The files themselves are left where they are. Dropping
    the column loses the record of which directory belongs
    to which job, not the outputs.
    """

    op.drop_column("analysis_jobs", "output_directory")
