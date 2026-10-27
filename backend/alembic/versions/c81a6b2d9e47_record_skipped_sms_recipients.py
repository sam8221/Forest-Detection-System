"""Record skipped SMS recipients safely.

Revision ID: c81a6b2d9e47
Revises: f2c5d91a7e63

Adds an account reference and a non-sensitive skip reason to
the existing SMS queue. Existing queue rows are retained and
their new account and skip-reason columns remain NULL.
"""

import sqlalchemy as sa
from alembic import op


revision = "c81a6b2d9e47"
down_revision = "f2c5d91a7e63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Allow durable, deduplicated records for skipped officers."""

    op.execute(
        "ALTER TYPE smsqueuestatus "
        "ADD VALUE IF NOT EXISTS 'SKIPPED'"
    )

    op.add_column(
        "sms_queue",
        sa.Column(
            "recipient_user_id",
            sa.Integer(),
            nullable=True,
            comment=(
                "Officer account addressed. Null only for legacy "
                "queue rows whose account was not recorded."
            ),
        ),
    )

    op.add_column(
        "sms_queue",
        sa.Column(
            "skip_reason",
            sa.String(length=50),
            nullable=True,
            comment=(
                "Non-sensitive reason a recipient was skipped."
            ),
        ),
    )

    op.create_foreign_key(
        "fk_sms_queue_recipient_user_id_users",
        "sms_queue",
        "users",
        ["recipient_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Existing rows all have a recipient number. Allow NULL for
    # newly recorded SKIPPED rows without changing those records.
    op.alter_column(
        "sms_queue",
        "recipient_phone",
        existing_type=sa.String(length=20),
        nullable=True,
    )

    # Legacy rows have NULL recipient_user_id. The partial index
    # deduplicates all new rows per officer and alert, regardless
    # of whether a phone number was available at queue time.
    op.create_index(
        "uq_sms_queue_alert_user",
        "sms_queue",
        ["alert_id", "recipient_user_id"],
        unique=True,
        postgresql_where=sa.text(
            "recipient_user_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    """Refuse to discard skipped-notification history."""

    bind = op.get_bind()
    skipped_rows = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM sms_queue "
            "WHERE status = 'SKIPPED' OR recipient_phone IS NULL"
        )
    ).scalar_one()

    if skipped_rows:
        raise RuntimeError(
            "Cannot downgrade while skipped SMS records exist; "
            "export or retain that history before proceeding."
        )

    op.drop_index(
        "uq_sms_queue_alert_user",
        table_name="sms_queue",
    )
    op.drop_constraint(
        "fk_sms_queue_recipient_user_id_users",
        "sms_queue",
        type_="foreignkey",
    )
    op.drop_column("sms_queue", "skip_reason")
    op.drop_column("sms_queue", "recipient_user_id")
    op.alter_column(
        "sms_queue",
        "recipient_phone",
        existing_type=sa.String(length=20),
        nullable=False,
    )

    # PostgreSQL does not support removing one enum label in
    # place. The unused SKIPPED label is intentionally retained.
