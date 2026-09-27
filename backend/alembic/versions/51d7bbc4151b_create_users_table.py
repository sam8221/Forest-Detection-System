"""
Create users table

===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Revision: Create users table

Revision ID: 51d7bbc4151b
Revises:
Create Date: 2026-08-04 13:26:08.029644

Purpose:
    The first migration in the project. Creates the users
    table, which every other table later references.

Position in the chain:
    down_revision is None, so this is the base revision. A
    fresh database is built by running the chain from here:

        users
          -> user account fields      (da8e3b0a7357)
          -> provinces, districts,
             forest areas             (dff42c735d8c)
          -> detections, alerts,
             analysis jobs, imagery   (e91c6f2a4b7e)
          -> previous image on job    (7c07409be073)
          -> geometry, seasonal
             windows, jurisdiction,
             audit log                (c3f8a1d54b72)

Note:
    Users come first because authorship and accountability
    run through them: forest areas record who registered
    them, detections who verified them, and analysis jobs who
    started them. Requirement FR-19 depends on those links
    existing, which is why no record in this system is
    anonymous.

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

# Revision identifiers, used by Alembic.
revision: str = "51d7bbc4151b"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Apply the database schema changes.

    Creates the users table together with its indexes.
    """

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum(
                "ADMIN",
                "FORESTRY_OFFICER",
                "RESEARCHER",
                name="userrole",
            ),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        op.f("ix_users_email"),
        "users",
        ["email"],
        unique=True,
    )

    op.create_index(
        op.f("ix_users_id"),
        "users",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    """
    Revert the database schema changes.

    Removes the users table and its indexes.
    """

    op.drop_index(
        op.f("ix_users_id"),
        table_name="users",
    )

    op.drop_index(
        op.f("ix_users_email"),
        table_name="users",
    )

    op.drop_table("users")