"""
ForestWatch Zambia
-----------------------------------------------------------
Module: Create Administrator

Purpose:
    Creates the first administrator account for development.

Important:
    This script imports the application's ORM models before
    querying User so SQLAlchemy can configure relationships.
"""

# ---------------------------------------------------------
# Load all ORM models first
# ---------------------------------------------------------

import app.models.district
import app.models.province
import app.models.forest_area
import app.models.analysis_job
import app.models.detection
import app.models.alert
import app.models.alert_recipient
import app.models.email_queue
import app.models.satellite_image

# ---------------------------------------------------------
# Application imports
# ---------------------------------------------------------

from app.database.session import SessionLocal
from app.models.user import User
from app.models.enums import UserRole
from app.core.security import hash_password


# ---------------------------------------------------------
# Development administrator credentials
# ---------------------------------------------------------

ADMIN_NAME = "System Administrator"
ADMIN_EMAIL = "admin@forestwatch.zm"
ADMIN_PASSWORD = "Admin@12345"


# ---------------------------------------------------------
# Create Administrator
# ---------------------------------------------------------

def create_admin() -> None:
    """
    Create the first administrator account.
    """

    db = SessionLocal()

    try:
        # -------------------------------------------------
        # Check whether administrator already exists
        # -------------------------------------------------

        existing_user = (
            db.query(User)
            .filter(
                User.email == ADMIN_EMAIL,
            )
            .first()
        )

        if existing_user is not None:

            print(
                "Administrator already exists."
            )

            print(
                f"ID: {existing_user.id}"
            )

            print(
                f"Email: {existing_user.email}"
            )

            print(
                f"Role: {existing_user.role.value}"
            )

            return

        # -------------------------------------------------
        # Create administrator
        # -------------------------------------------------

        admin = User(
            full_name=ADMIN_NAME,
            email=ADMIN_EMAIL,
            password_hash=hash_password(
                ADMIN_PASSWORD
            ),
            must_change_password=True,
            role=UserRole.ADMIN,
            is_active=True,
        )

        # -------------------------------------------------
        # Save user
        # -------------------------------------------------

        db.add(admin)

        db.commit()

        db.refresh(admin)

        # -------------------------------------------------
        # Display result
        # -------------------------------------------------

        print()
        print("=" * 55)
        print("ForestWatch Zambia")
        print("Administrator Created Successfully")
        print("=" * 55)
        print(f"ID       : {admin.id}")
        print(f"Name     : {admin.full_name}")
        print(f"Email    : {admin.email}")
        print(f"Role     : {admin.role.value}")
        print(f"Active   : {admin.is_active}")
        print(f"Password : {ADMIN_PASSWORD}")
        print("=" * 55)
        print()
        print(
            "IMPORTANT: Change this development password "
            "after your first login."
        )

    except Exception as exc:

        db.rollback()

        print()
        print("ERROR: Administrator could not be created.")
        print(f"Reason: {exc}")
        print()

        raise

    finally:

        db.close()


# ---------------------------------------------------------
# Entry Point
# ---------------------------------------------------------

if __name__ == "__main__":
    create_admin()