"""
ForestWatch Zambia
-----------------------------------------------------------
Revision: Add user account fields

Revision ID: da8e3b0a7357
Revises: 51d7bbc4151b
Create Date: 2026-08-05

Purpose:
    Adds the additional user account and audit fields
    required by the current User model.

Important:
    PostGIS-managed tables such as spatial_ref_sys must
    not be modified by this migration.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ---------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------

revision: str = "da8e3b0a7357"

down_revision: Union[
    str,
    Sequence[str],
    None,
] = "51d7bbc4151b"

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


# ---------------------------------------------------------
# Upgrade
# ---------------------------------------------------------

def upgrade() -> None:
    """
    Upgrade the database schema.

    Adds the fields required by the current User model.

    Existing PostGIS system tables are intentionally left
    untouched.
    """

    # -----------------------------------------------------
    # Add must_change_password
    # -----------------------------------------------------

    op.add_column(
        "users",
        sa.Column(
            "must_change_password",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment=(
                "Forces the user to change password "
                "after first login."
            ),
        ),
    )

    # -----------------------------------------------------
    # Add last_login
    # -----------------------------------------------------

    op.add_column(
        "users",
        sa.Column(
            "last_login",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful login.",
        ),
    )

    # -----------------------------------------------------
    # Add updated_at
    # -----------------------------------------------------

    op.add_column(
        "users",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment=(
                "Date and time the record was last updated."
            ),
        ),
    )

    # -----------------------------------------------------
    # Existing column comments
    # -----------------------------------------------------

    op.alter_column(
        "users",
        "full_name",
        existing_type=sa.VARCHAR(length=150),
        comment="Full name of the user.",
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "email",
        existing_type=sa.VARCHAR(length=255),
        comment="User email address.",
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.VARCHAR(length=255),
        comment="Encrypted password.",
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "role",
        existing_type=postgresql.ENUM(
            "ADMIN",
            "FORESTRY_OFFICER",
            "RESEARCHER",
            name="userrole",
        ),
        comment="Assigned user role.",
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment="Account status.",
        existing_nullable=False,
    )

    # -----------------------------------------------------
    # created_at timezone
    # -----------------------------------------------------

    op.alter_column(
        "users",
        "created_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.DateTime(timezone=True),
        comment="Date and time the record was created.",
        existing_nullable=False,
    )

    # -----------------------------------------------------
    # Remove temporary server defaults
    #
    # The Python model already provides application-level
    # defaults. Keeping the migration clean avoids forcing
    # PostgreSQL to maintain unnecessary defaults.
    # -----------------------------------------------------

    op.alter_column(
        "users",
        "must_change_password",
        server_default=None,
    )

    op.alter_column(
        "users",
        "updated_at",
        server_default=None,
    )


# ---------------------------------------------------------
# Downgrade
# ---------------------------------------------------------

def downgrade() -> None:
    """
    Reverse the user schema changes.

    PostGIS system tables are intentionally left untouched.
    """

    # -----------------------------------------------------
    # Restore created_at
    # -----------------------------------------------------

    op.alter_column(
        "users",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=postgresql.TIMESTAMP(),
        comment=None,
        existing_comment=(
            "Date and time the record was created."
        ),
        existing_nullable=False,
    )

    # -----------------------------------------------------
    # Remove updated_at
    # -----------------------------------------------------

    op.drop_column(
        "users",
        "updated_at",
    )

    # -----------------------------------------------------
    # Remove last_login
    # -----------------------------------------------------

    op.drop_column(
        "users",
        "last_login",
    )

    # -----------------------------------------------------
    # Remove must_change_password
    # -----------------------------------------------------

    op.drop_column(
        "users",
        "must_change_password",
    )

    # -----------------------------------------------------
    # Restore comments
    # -----------------------------------------------------

    op.alter_column(
        "users",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment="Account status.",
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "role",
        existing_type=postgresql.ENUM(
            "ADMIN",
            "FORESTRY_OFFICER",
            "RESEARCHER",
            name="userrole",
        ),
        comment=None,
        existing_comment="Assigned user role.",
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.VARCHAR(length=255),
        comment=None,
        existing_comment="Encrypted password.",
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "email",
        existing_type=sa.VARCHAR(length=255),
        comment=None,
        existing_comment="User email address.",
        existing_nullable=False,
    )

    op.alter_column(
        "users",
        "full_name",
        existing_type=sa.VARCHAR(length=150),
        comment=None,
        existing_comment="Full name of the user.",
        existing_nullable=False,
    )
    