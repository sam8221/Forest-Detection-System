"""Add the officer SMS preference and allow test-message records.

Revision ID: d9f4a7c1e835
Revises: a6b29b1042ef

Two changes, both additive:

  users.sms_notifications_enabled records whether an officer
  wants automatic deforestation alert SMS. It is NOT NULL with
  a server default of true, so existing accounts keep
  receiving what they receive today and no row is rewritten by
  hand. The preference is kept separate from phone_number so
  that switching notifications off does not discard a
  registered number.

  sms_queue.alert_id becomes nullable. The test message an
  officer sends themselves while registering a number belongs
  to no alert, and recording it with a fabricated alert
  reference would corrupt the notification record that
  requirement FR-19 depends on. A NULL alert_id is the marker
  that a row is a registration test rather than a real
  notification.

Dropping NOT NULL cannot fail on existing data, and no
existing row is modified.

Note on the unique constraints: uq_sms_queue_alert_recipient
and uq_sms_queue_alert_user both lead with alert_id. In
PostgreSQL a NULL is never equal to another NULL, so rows with
a NULL alert_id do not collide with each other. Repeated test
messages to one number therefore remain possible, while the
one-message-per-officer-per-alert rule is untouched for real
alerts.
"""

import sqlalchemy as sa
from alembic import op


revision = "d9f4a7c1e835"
down_revision = "a6b29b1042ef"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the preference column and free the test-message record."""

    op.add_column(
        "users",
        sa.Column(
            "sms_notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment=(
                "Whether automatic deforestation alert SMS are "
                "sent to this officer."
            ),
        ),
    )

    op.alter_column(
        "sms_queue",
        "alert_id",
        existing_type=sa.Integer(),
        nullable=True,
        comment=(
            "Alert this message notifies. Null for the test "
            "message an officer sends themselves when "
            "registering a number, which belongs to no alert."
        ),
        existing_comment="Alert this message notifies.",
    )


def downgrade() -> None:
    """Return to one message per alert and no stored preference."""

    # Any registration test messages recorded while this
    # revision was applied have no alert, so they cannot be
    # kept once the column is NOT NULL again. They are
    # removed rather than reassigned to an unrelated alert,
    # which would put a message in that alert's record that
    # was never sent for it.
    op.execute("DELETE FROM sms_queue WHERE alert_id IS NULL")

    op.alter_column(
        "sms_queue",
        "alert_id",
        existing_type=sa.Integer(),
        nullable=False,
        comment="Alert this message notifies.",
        existing_comment=(
            "Alert this message notifies. Null for the test "
            "message an officer sends themselves when "
            "registering a number, which belongs to no alert."
        ),
    )

    op.drop_column("users", "sms_notifications_enabled")
