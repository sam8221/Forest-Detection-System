"""
Record what an analysis measured

===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Revision: Add analysis measurement summary

Revision ID: e3b7d2f5a916
Revises: d9f4a7c1e835
Create Date: 2026-11-02

Purpose:
    Adds analysis_jobs.measurement_summary, which records
    what a run measured rather than only what it concluded.

Why:
    A completed run reported "0.00%" vegetation change and
    "None detected" while carrying no evidence that a
    measurement had been taken. Both figures were correct:
    the steepest NDVI decline in the scene was 0.286 against
    a 0.30 threshold. But a correct negative result was
    indistinguishable from a broken pipeline, and was
    reported as a fault.

    Another run found 42 pixels past the threshold whose
    largest connected group covered 0.25 ha, below the 0.5
    ha minimum from the Forests Act criterion, and recorded
    nothing about having seen them.

    This column keeps that evidence: pixels compared, how
    much of the scene was usable, the NDVI change observed,
    the candidates found, and the thresholds applied.

Safety:
    Additive and nullable. Existing rows keep a null
    summary, which the interface reports as "not recorded
    for this run" rather than as a measurement of zero. No
    data is rewritten and nothing is dropped.
===========================================================
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------

revision: str = "e3b7d2f5a916"

down_revision: Union[
    str,
    Sequence[str],
    None,
] = "d9f4a7c1e835"

branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None

depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


def upgrade() -> None:
    """Add the measurement summary column."""

    op.add_column(
        "analysis_jobs",
        sa.Column(
            "measurement_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "What the analysis measured: pixels "
                "compared, NDVI change observed, candidates "
                "found and the thresholds applied. Null for "
                "a job that ran before this was recorded."
            ),
        ),
    )


def downgrade() -> None:
    """Remove the measurement summary column."""

    op.drop_column(
        "analysis_jobs",
        "measurement_summary",
    )
