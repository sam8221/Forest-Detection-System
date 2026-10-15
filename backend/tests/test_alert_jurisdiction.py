"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Alert Jurisdiction Tests

Purpose:
    Verify that alert queries are restricted to an
    officer's jurisdiction, requirement FR-04.

Responsibilities:
    - Confirm a district officer's alert query is filtered
      to their district.
    - Confirm a provincial officer's query is filtered to
      their province.
    - Confirm an administrator's query is unfiltered.
    - Confirm an officer with no jurisdiction matches
      nothing rather than matching rows with a null
      district.
    - Confirm the query joins through the detection to
      reach the forest area.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Note:
    These tests inspect the SQL the repository builds
    rather than executing it, so they need no database and
    no network. The regression they guard against is real:
    the alert endpoints once returned every alert in the
    country to any signed-in officer, because the router
    discarded the authenticated user and called the
    unscoped repository method. An alert names the forest
    area and location of suspected clearing, so that leak
    disclosed where the department was watching in
    districts an officer does not cover.
===========================================================
"""

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.alert_repository import AlertRepository


# =========================================================
# HELPERS
# =========================================================

COPPERBELT = 2

KITWE = 8


def compiled_sql(user: User) -> str:
    """
    Return the SQL a scoped alert query compiles to.

    The Session is never connected: building and compiling a
    query touches no database, which is what keeps these
    tests runnable with nothing installed but the
    dependencies.
    """

    session = Session()

    scoped = AlertRepository(session).scope_to_jurisdiction(
        session.query(Alert),
        user,
    )

    return str(
        scoped.statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def where_clause(user: User) -> str:
    """
    Return only the WHERE clause of a scoped alert query.

    The assertions below test the WHERE clause rather than
    the whole statement. Alert eager-loads its detection and
    forest area, so the SELECT list and the FROM clause
    mention district_id and join detections whatever the
    officer's role is. The restriction itself lives in the
    WHERE clause, and that is the part access control
    depends on.
    """

    sql = compiled_sql(user)

    if "WHERE" not in sql:
        return ""

    return sql[sql.index("WHERE"):]


def officer(
    role: UserRole,
    district_id: int | None = None,
    province_id: int | None = None,
) -> User:
    """Build an unsaved User carrying only a jurisdiction."""

    user = User()
    user.role = role
    user.district_id = district_id
    user.province_id = province_id

    return user


# =========================================================
# DISTRICT OFFICER
# =========================================================

def test_district_officer_query_is_filtered_to_district(
) -> None:
    """
    A Kitwe officer's alert query carries a district filter.

    This is the scenario demonstrated for Chapter Four: the
    restriction is in the SQL, so the database cannot return
    an alert from another district whatever the request
    asked for.
    """

    where = where_clause(
        officer(
            UserRole.DISTRICT_FORESTRY_OFFICER,
            district_id=KITWE,
        )
    )

    assert "forest_areas.district_id = 8" in where


def test_district_officer_query_joins_through_detection(
) -> None:
    """
    Reaching the forest area requires the detection join.

    An alert records only its detection, so the scope has to
    join Alert to Detection to ForestArea before it has a
    district to filter on. The filter naming
    forest_areas.district_id is what proves that chain was
    built: without the joins the statement would not compile
    against that column at all.
    """

    sql = compiled_sql(
        officer(
            UserRole.DISTRICT_FORESTRY_OFFICER,
            district_id=KITWE,
        )
    )

    assert "JOIN detections" in sql
    assert "JOIN forest_areas" in sql
    assert "forest_areas.district_id" in where_clause(
        officer(
            UserRole.DISTRICT_FORESTRY_OFFICER,
            district_id=KITWE,
        )
    )


# =========================================================
# PROVINCIAL OFFICER
# =========================================================

def test_provincial_officer_query_is_filtered_to_province(
) -> None:
    """A provincial officer is scoped to their province."""

    where = where_clause(
        officer(
            UserRole.PROVINCIAL_FORESTRY_OFFICER,
            province_id=COPPERBELT,
        )
    )

    assert "districts.province_id = 2" in where


# =========================================================
# ADMINISTRATOR
# =========================================================

def test_administrator_query_is_not_filtered() -> None:
    """
    An administrator's query carries no jurisdiction filter.

    Administration holds no jurisdiction, so there is
    nothing to scope to. The account provisions users and
    configures thresholds; it has no alert duties of its
    own, which is what keeps the audit trail independent.
    """

    assert where_clause(officer(UserRole.ADMIN)) == ""


# =========================================================
# UNASSIGNED ACCOUNT
# =========================================================

def test_officer_without_district_matches_nothing() -> None:
    """
    An officer with no district assigned matches no alert.

    The guard matters because SQLAlchemy renders
    `column == None` as `IS NULL`, which would return every
    alert whose district happens to be unset instead of
    returning none. An unassigned account is treated as not
    yet authorised.
    """

    where = where_clause(
        officer(
            UserRole.DISTRICT_FORESTRY_OFFICER,
            district_id=None,
        )
    )

    assert "false" in where.lower()
    assert "IS NULL" not in where


def test_officer_without_province_matches_nothing() -> None:
    """A provincial officer with no province matches none."""

    where = where_clause(
        officer(
            UserRole.PROVINCIAL_FORESTRY_OFFICER,
            province_id=None,
        )
    )

    assert "false" in where.lower()
    assert "IS NULL" not in where
