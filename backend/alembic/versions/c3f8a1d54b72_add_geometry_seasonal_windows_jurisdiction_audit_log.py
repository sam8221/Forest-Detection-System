"""
Add detection geometry, seasonal windows, user jurisdiction
and the audit log.

===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Revision: Add detection geometry, seasonal windows, user
          jurisdiction and the audit log

Revision ID: c3f8a1d54b72
Revises: 7c07409be073

Purpose:
    Completes the schema the system needs to map detections,
    compare seasonal windows, enforce jurisdiction and keep
    an audit trail. This is the current head of the chain.

Changes:
    1. detections.geometry, in EPSG:32735 (UTM 35S), with a
       GiST index. A projected CRS is used so areas come out
       in square metres and the half-hectare threshold needs
       no conversion.
    2. Four date columns on analysis_jobs: baseline_start,
       baseline_end, comparison_start and comparison_end.
    3. province_id and district_id on users, which is what
       requirement FR-04 is enforced against.
    4. The audit_logs table, write-once, for FR-19.
    5. Recreates three Postgres enum types whose values had
       drifted from the Python enums.

Why seasonal windows and not two dates:
    Miombo woodland across the Copperbelt loses leaf every
    dry season. Comparing consecutive months would report
    deforestation across the entire province. Analysis
    therefore compares equivalent calendar windows in
    different years, and the schema records both windows so
    the comparison a detection came from can be reproduced.
    This is the main methodological defence of the project.

Why the audit table has no updated_at:
    Audit records are write-once. AuditMixin is deliberately
    not used, because it adds an onupdate timestamp that
    would imply a mutability this table must not have, and
    there is no update method anywhere for it.

Before running this against real data:
    Take a pg_dump. The enum recreation in step 5 rewrites
    columns in place.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia
===========================================================
"""

from typing import Sequence, Union

from alembic import op
import geoalchemy2
import sqlalchemy as sa


# =========================================================
# REVISION IDENTIFIERS
# =========================================================

revision: str = "c3f8a1d54b72"

down_revision: Union[str, Sequence[str], None] = "7c07409be073"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# =========================================================
# UPGRADE
# =========================================================

def upgrade() -> None:
    """
    Complete the schema required for mapping, seasonal
    comparison, jurisdiction-scoped access and auditing.

    This revision makes five changes:

        1. Gives every detection a map geometry.
        2. Gives every analysis job an explicit baseline and
           comparison window.
        3. Gives every user a jurisdiction.
        4. Adds the write-once audit trail.
        5. Removes enum values that the application no
           longer defines.
    """

    # =====================================================
    # 1. DETECTION GEOMETRY
    #
    # SRID 32735 is WGS 84 / UTM Zone 35S, covering the
    # Copperbelt. A projected CRS is used so that areas and
    # distances are measured directly in metres.
    #
    # The column is nullable because detections recorded
    # before this revision have no stored outline.
    # =====================================================

    op.add_column(
        "detections",
        sa.Column(
            "geometry",
            geoalchemy2.types.Geometry(
                geometry_type="MULTIPOLYGON",
                srid=32735,
                dimension=2,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=True,
                spatial_index=False,
            ),
            nullable=True,
            comment=(
                "Outline of the detected clearing, "
                "UTM Zone 35S (EPSG:32735)."
            ),
        ),
    )

    # -----------------------------------------------------
    # Spatial index
    #
    # Created as raw SQL with IF NOT EXISTS, matching the
    # approach already used for forest_areas.geometry.
    # -----------------------------------------------------

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_detections_geometry "
        "ON detections USING gist (geometry)"
    )

    # =====================================================
    # 2. SEASONAL COMPARISON WINDOWS
    #
    # Miombo woodland NDVI falls across the whole province
    # every dry season, so a baseline must be drawn from the
    # same calendar window in an earlier year rather than
    # from the preceding months.
    # =====================================================

    op.add_column(
        "analysis_jobs",
        sa.Column(
            "baseline_start",
            sa.Date(),
            nullable=True,
            comment=(
                "First acquisition date of the "
                "baseline window."
            ),
        ),
    )

    op.add_column(
        "analysis_jobs",
        sa.Column(
            "baseline_end",
            sa.Date(),
            nullable=True,
            comment=(
                "Last acquisition date of the "
                "baseline window."
            ),
        ),
    )

    op.add_column(
        "analysis_jobs",
        sa.Column(
            "comparison_start",
            sa.Date(),
            nullable=True,
            comment=(
                "First acquisition date of the "
                "comparison window."
            ),
        ),
    )

    op.add_column(
        "analysis_jobs",
        sa.Column(
            "comparison_end",
            sa.Date(),
            nullable=True,
            comment=(
                "Last acquisition date of the "
                "comparison window."
            ),
        ),
    )

    # =====================================================
    # 3. USER JURISDICTION
    #
    # Both columns are nullable: an administrator holds no
    # jurisdiction, and each officer holds only the one that
    # matches their role.
    # =====================================================

    op.add_column(
        "users",
        sa.Column(
            "province_id",
            sa.Integer(),
            nullable=True,
            comment=(
                "Province a provincial officer is "
                "responsible for."
            ),
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "district_id",
            sa.Integer(),
            nullable=True,
            comment=(
                "District a district officer is "
                "responsible for."
            ),
        ),
    )

    op.create_index(
        "ix_users_province_id",
        "users",
        ["province_id"],
        unique=False,
    )

    op.create_index(
        "ix_users_district_id",
        "users",
        ["district_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_users_province_id",
        "users",
        "provinces",
        ["province_id"],
        ["id"],
    )

    op.create_foreign_key(
        "fk_users_district_id",
        "users",
        "districts",
        ["district_id"],
        ["id"],
    )

    # =====================================================
    # 4. AUDIT LOG
    #
    # Requirement FR-19. Rows are written once and never
    # updated, so the table carries created_at with no
    # updated_at counterpart.
    #
    # The subject of an action is stored as a type plus an
    # identifier rather than a foreign key, so that deleting
    # a record cannot delete the evidence of what was done
    # to it.
    # =====================================================

    op.create_table(
        "audit_logs",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=True,
            comment=(
                "Officer who performed the action, or null "
                "when performed by the system."
            ),
        ),

        sa.Column(
            "action",
            sa.String(length=60),
            nullable=False,
            comment=(
                "Action performed, for example LOGIN, "
                "ANALYSIS_RUN or ALERT_STATUS_CHANGE."
            ),
        ),

        sa.Column(
            "entity_type",
            sa.String(length=60),
            nullable=True,
            comment=(
                "Type of record acted upon, for example "
                "Detection or AnalysisJob."
            ),
        ),

        sa.Column(
            "entity_id",
            sa.Integer(),
            nullable=True,
            comment="Identifier of the record acted upon.",
        ),

        sa.Column(
            "detail",
            sa.Text(),
            nullable=True,
            comment=(
                "Human-readable description of what "
                "changed."
            ),
        ),

        sa.Column(
            "ip_address",
            sa.String(length=45),
            nullable=True,
            comment="Origin address of the request.",
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment=(
                "Date and time the action was performed."
            ),
        ),

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_audit_logs_id",
        "audit_logs",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_user_id",
        "audit_logs",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_action",
        "audit_logs",
        ["action"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_entity_type",
        "audit_logs",
        ["entity_type"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_entity_id",
        "audit_logs",
        ["entity_id"],
        unique=False,
    )

    op.create_index(
        "ix_audit_logs_created_at",
        "audit_logs",
        ["created_at"],
        unique=False,
    )

    # =====================================================
    # 5. ENUM CLEAN-UP
    #
    # PostgreSQL cannot remove a value from an existing enum
    # type, so each affected type is rebuilt: the column is
    # detached to text, any row holding a removed value is
    # remapped, the old type is dropped and a new one with
    # the correct values is created.
    #
    # The remapping UPDATE statements run before the cast
    # back, because a value absent from the new type would
    # otherwise make the cast fail.
    # =====================================================

    # -----------------------------------------------------
    # userrole
    #
    # FORESTRY_OFFICER is replaced by two roles that differ
    # in jurisdiction. Existing officers become district
    # officers, the narrower of the two, so that the change
    # cannot silently widen anyone's access. RESEARCHER is
    # removed: the system is restricted to Forestry
    # Department officers.
    # -----------------------------------------------------

    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role DROP DEFAULT"
    )

    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role TYPE VARCHAR(50) "
        "USING role::text"
    )

    op.execute(
        "UPDATE users "
        "SET role = 'DISTRICT_FORESTRY_OFFICER' "
        "WHERE role IN ('FORESTRY_OFFICER', 'RESEARCHER')"
    )

    op.execute("DROP TYPE userrole")

    op.execute(
        "CREATE TYPE userrole AS ENUM ("
        "'ADMIN', "
        "'PROVINCIAL_FORESTRY_OFFICER', "
        "'DISTRICT_FORESTRY_OFFICER'"
        ")"
    )

    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role TYPE userrole "
        "USING role::userrole"
    )

    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role "
        "SET DEFAULT 'DISTRICT_FORESTRY_OFFICER'"
    )

    # -----------------------------------------------------
    # protectedstatus
    #
    # National parks and game management areas fall outside
    # the scope of this system.
    # -----------------------------------------------------

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN protected_status DROP DEFAULT"
    )

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN protected_status TYPE VARCHAR(50) "
        "USING protected_status::text"
    )

    op.execute(
        "UPDATE forest_areas "
        "SET protected_status = 'PROTECTED_FOREST' "
        "WHERE protected_status IN "
        "('NATIONAL_PARK', 'GAME_MANAGEMENT_AREA')"
    )

    op.execute("DROP TYPE protectedstatus")

    op.execute(
        "CREATE TYPE protectedstatus AS ENUM ("
        "'PROTECTED_FOREST', "
        "'COMMUNITY_FOREST', "
        "'PRIVATE_FOREST'"
        ")"
    )

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN protected_status TYPE protectedstatus "
        "USING protected_status::protectedstatus"
    )

    # -----------------------------------------------------
    # monitoringfrequency
    #
    # Sentinel-2 revisits the same tile roughly every five
    # days, so daily and two-day monitoring promise an
    # update frequency the data cannot deliver.
    # -----------------------------------------------------

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN monitoring_frequency DROP DEFAULT"
    )

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN monitoring_frequency TYPE VARCHAR(50) "
        "USING monitoring_frequency::text"
    )

    op.execute(
        "UPDATE forest_areas "
        "SET monitoring_frequency = 'WEEKLY' "
        "WHERE monitoring_frequency IN "
        "('DAILY', 'EVERY_2_DAYS')"
    )

    op.execute("DROP TYPE monitoringfrequency")

    op.execute(
        "CREATE TYPE monitoringfrequency AS ENUM ("
        "'WEEKLY', "
        "'MONTHLY'"
        ")"
    )

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN monitoring_frequency "
        "TYPE monitoringfrequency "
        "USING monitoring_frequency::monitoringfrequency"
    )


# =========================================================
# DOWNGRADE
# =========================================================

def downgrade() -> None:
    """
    Reverse this revision.

    The enum types are restored to their previous set of
    values, but rows that were remapped during the upgrade
    keep their new value. The original value of such a row
    is not recoverable, because the enum carried no record
    of what it had been.
    """

    # =====================================================
    # 5. ENUM CLEAN-UP (reversed)
    # =====================================================

    # -----------------------------------------------------
    # monitoringfrequency
    # -----------------------------------------------------

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN monitoring_frequency DROP DEFAULT"
    )

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN monitoring_frequency TYPE VARCHAR(50) "
        "USING monitoring_frequency::text"
    )

    op.execute("DROP TYPE monitoringfrequency")

    op.execute(
        "CREATE TYPE monitoringfrequency AS ENUM ("
        "'DAILY', "
        "'EVERY_2_DAYS', "
        "'WEEKLY', "
        "'MONTHLY'"
        ")"
    )

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN monitoring_frequency "
        "TYPE monitoringfrequency "
        "USING monitoring_frequency::monitoringfrequency"
    )

    # -----------------------------------------------------
    # protectedstatus
    # -----------------------------------------------------

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN protected_status DROP DEFAULT"
    )

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN protected_status TYPE VARCHAR(50) "
        "USING protected_status::text"
    )

    op.execute("DROP TYPE protectedstatus")

    op.execute(
        "CREATE TYPE protectedstatus AS ENUM ("
        "'PROTECTED_FOREST', "
        "'NATIONAL_PARK', "
        "'GAME_MANAGEMENT_AREA', "
        "'COMMUNITY_FOREST', "
        "'PRIVATE_FOREST'"
        ")"
    )

    op.execute(
        "ALTER TABLE forest_areas "
        "ALTER COLUMN protected_status TYPE protectedstatus "
        "USING protected_status::protectedstatus"
    )

    # -----------------------------------------------------
    # userrole
    # -----------------------------------------------------

    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role DROP DEFAULT"
    )

    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role TYPE VARCHAR(50) "
        "USING role::text"
    )

    op.execute(
        "UPDATE users "
        "SET role = 'FORESTRY_OFFICER' "
        "WHERE role IN ("
        "'PROVINCIAL_FORESTRY_OFFICER', "
        "'DISTRICT_FORESTRY_OFFICER'"
        ")"
    )

    op.execute("DROP TYPE userrole")

    op.execute(
        "CREATE TYPE userrole AS ENUM ("
        "'ADMIN', "
        "'FORESTRY_OFFICER', "
        "'RESEARCHER'"
        ")"
    )

    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role TYPE userrole "
        "USING role::userrole"
    )

    op.execute(
        "ALTER TABLE users "
        "ALTER COLUMN role "
        "SET DEFAULT 'FORESTRY_OFFICER'"
    )

    # =====================================================
    # 4. AUDIT LOG (reversed)
    # =====================================================

    op.drop_index(
        "ix_audit_logs_created_at",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_entity_id",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_entity_type",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_action",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_user_id",
        table_name="audit_logs",
    )

    op.drop_index(
        "ix_audit_logs_id",
        table_name="audit_logs",
    )

    op.drop_table("audit_logs")

    # =====================================================
    # 3. USER JURISDICTION (reversed)
    # =====================================================

    op.drop_constraint(
        "fk_users_district_id",
        "users",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_users_province_id",
        "users",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_users_district_id",
        table_name="users",
    )

    op.drop_index(
        "ix_users_province_id",
        table_name="users",
    )

    op.drop_column("users", "district_id")

    op.drop_column("users", "province_id")

    # =====================================================
    # 2. SEASONAL COMPARISON WINDOWS (reversed)
    # =====================================================

    op.drop_column("analysis_jobs", "comparison_end")

    op.drop_column("analysis_jobs", "comparison_start")

    op.drop_column("analysis_jobs", "baseline_end")

    op.drop_column("analysis_jobs", "baseline_start")

    # =====================================================
    # 1. DETECTION GEOMETRY (reversed)
    # =====================================================

    op.execute(
        "DROP INDEX IF EXISTS idx_detections_geometry"
    )

    op.drop_column("detections", "geometry")
