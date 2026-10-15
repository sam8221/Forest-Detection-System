"""
Add RESOLVED to the alertstatus enum.

===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Revision: Add RESOLVED to the alertstatus enum

Revision ID: d4a1c6e82b19
Revises: c3f8a1d54b72

Purpose:
    Restores the admin alert-resolution endpoint, which
    could not complete because the Postgres enum behind
    alerts.status had no RESOLVED label while the Python
    AlertStatus enum did.

The failure this fixes:
    PUT /api/v1/alerts/{id}/resolve sets both
    alert.is_resolved and alert.status = AlertStatus.RESOLVED.
    The second assignment was rejected by Postgres with

        invalid input value for enum alertstatus: "RESOLVED"

    so the endpoint answered 500 and no alert could be
    resolved through the interface. Revision c3f8a1d54b72
    recreated three enum types whose values had drifted from
    the Python enums; alertstatus was not among them, and
    this completes that work.

Why the value is only added:
    ALTER TYPE ... ADD VALUE is additive and leaves every
    existing row untouched, so no alert loses its status.
    Rebuilding the type would mean rewriting the column
    across all alert rows for a single new label.

Note on existing data:
    At least one alert already carries is_resolved = true
    with status = 'PENDING', recorded when the status write
    failed but the resolution flag was committed. This
    migration does not correct those rows, because deciding
    what an alert's review status should be is a records
    decision rather than a schema one. They can be aligned
    afterwards with

        UPDATE alerts SET status = 'RESOLVED'
        WHERE is_resolved = true AND status <> 'RESOLVED';

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from alembic import op

# ---------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------

revision = "d4a1c6e82b19"
down_revision = "c3f8a1d54b72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the RESOLVED label to the alertstatus enum."""

    # IF NOT EXISTS keeps the migration safe to re-run and
    # safe on a database where the label was added by hand.
    op.execute(
        "ALTER TYPE alertstatus ADD VALUE IF NOT EXISTS 'RESOLVED'"
    )


def downgrade() -> None:
    """
    Remove the RESOLVED label from the alertstatus enum.

    Postgres cannot drop a single label, so the type is
    rebuilt without it. Any alert currently marked RESOLVED
    is moved to READ first, because the column cannot hold a
    label the new type does not define. The is_resolved flag
    and resolved_at timestamp are left alone, so the fact of
    resolution survives the downgrade even though the status
    label does not.
    """

    op.execute(
        "UPDATE alerts SET status = 'READ' "
        "WHERE status = 'RESOLVED'"
    )

    op.execute("ALTER TYPE alertstatus RENAME TO alertstatus_old")

    op.execute(
        "CREATE TYPE alertstatus AS ENUM "
        "('PENDING', 'SENT', 'FAILED', 'READ')"
    )

    op.execute(
        "ALTER TABLE alerts ALTER COLUMN status "
        "TYPE alertstatus USING status::text::alertstatus"
    )

    op.execute("DROP TYPE alertstatus_old")
