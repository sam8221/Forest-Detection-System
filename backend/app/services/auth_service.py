"""
===========================================================
ForestWatch Zambia
-----------------------------------------------------------
Module: Authentication Service

Purpose:
    Implements the business logic for authentication and
    user account management.

Responsibilities:
    - Register new users.
    - Authenticate users.
    - Generate JWT access tokens.
    - Validate login credentials.

Author:
    Samuel Bikiloni

Project:
    Web-Based Deforestation Detection and Alert System
    Using Sentinel-2 Imagery in the Copperbelt, Zambia

Version:
    1.0.0
===========================================================
"""
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    ChangePasswordRequest,
    Token,
    UserCreate,
)


class AuthService:
    """
    Handles authentication and user management.

    This service contains business logic only.
    It does not interact directly with FastAPI.
    """

    def __init__(self, db: Session):
        """
        Initialize the authentication service.

        Args:
            db:
                SQLAlchemy database session.
        """
        self.repository = UserRepository(db)

        # Held so that a change to an account can be
        # recorded in the same transaction that makes it.
        # An audit trail written separately can be missing
        # the entry for a change that did happen.
        self.db = db

    # ---------------------------------------------------------
    # Register User
    # ---------------------------------------------------------
    def register_user(self, user_data: UserCreate) -> User:
        """
        Register a new user.

        Args:
            user_data:
                Validated user information.

        Returns:
            Newly created User object.

        Raises:
            ValueError:
                If the email address already exists.
        """

        existing_user = self.repository.get_by_email(
            user_data.email
        )

        if existing_user:
            raise ValueError(
                "A user with this email already exists."
            )

        user = User(
            full_name=user_data.full_name,
            email=user_data.email,
            password_hash=hash_password(
                user_data.password
            ),
            role=user_data.role,

            # Every account is provisioned by someone other
            # than the person who will use it, with a
            # password that person chose. Until it is
            # changed, the administrator can sign in as the
            # officer, so an action in the audit trail
            # cannot be attributed to the officer alone.
            must_change_password=True,

            # The jurisdiction is stored with the account.
            # It is read from the database on every request,
            # never carried in the access token, so an
            # administrator's reassignment takes effect at
            # once instead of when the token next expires.
            province_id=user_data.province_id,
            district_id=user_data.district_id,
        )

        return self.repository.create(user)

    # ---------------------------------------------------------
    # Authenticate User
    # ---------------------------------------------------------
    def authenticate_user(
        self,
        email: str,
        password: str,
    ) -> User | None:
        """
        Validate login credentials.

        Args:
            email:
                User email.

            password:
                Plain text password.

        Returns:
            User if authentication succeeds,
            otherwise None.
        """

        user = self.repository.get_by_email(email)

        if user is None:
            return None

        if not verify_password(
            password,
            user.password_hash,
        ):
            return None

        return user

    # ---------------------------------------------------------
    # Login
    # ---------------------------------------------------------
    def login(
        self,
        email: str,
        password: str,
    ) -> Token:
        """
        Authenticate a user and generate
        an access token.

        Args:
            email:
                User email.

            password:
                User password.

        Returns:
            JWT access token.

        Raises:
            ValueError:
                If credentials are invalid.
        """

        user = self.authenticate_user(
            email,
            password,
        )

        if user is None:
            raise ValueError(
                "Invalid email or password."
            )

        token = create_access_token(
            {
                "sub": user.email,
                "role": user.role.value,
            }
        )

        return Token(
            access_token=token,
            token_type="bearer",
        )

    # ---------------------------------------------------------
    # Get User
    # ---------------------------------------------------------
    def get_user_by_email(
        self,
        email: str,
    ) -> User | None:
        """
        Retrieve a user by email.
        """

        return self.repository.get_by_email(email)
        # ---------------------------------------------------------
    # Update User
    # ---------------------------------------------------------
    def update_user(
        self,
        user_id: int,
        user_data,
    ) -> User:
        """
        Update an existing user.
        """

        user = self.repository.get_by_id(user_id)

        if user is None:
            raise ValueError("User not found.")

        update_data = user_data.model_dump(
            exclude_unset=True,
        )

        for field, value in update_data.items():
            setattr(
                user,
                field,
                value,
            )

        return self.repository.update(user)
        # ---------------------------------------------------------
    # Change Password
    # ---------------------------------------------------------
    def change_password(
        self,
        email: str,
        password_data: ChangePasswordRequest,
    ) -> User:
        """
        Change a user's password.
        """

        user = self.repository.get_by_email(email)

        if user is None:
            raise ValueError("User not found.")

        if not verify_password(
            password_data.current_password,
            user.password_hash,
        ):
            raise ValueError(
                "Current password is incorrect."
            )

        user.password_hash = hash_password(
            password_data.new_password
        )

        user.must_change_password = False

        return self.repository.update(user)

    # ---------------------------------------------------------
    # Update Last Login
    # ---------------------------------------------------------
    def update_last_login(
        self,
        user: User,
    ) -> User:
        """
        Update the user's last login timestamp.
        """

        from datetime import UTC, datetime

        user.last_login = datetime.now(UTC)

        return self.repository.update(user)

    # ---------------------------------------------------------
    # Deactivate User
    # ---------------------------------------------------------
    def deactivate_user(
        self,
        email: str,
    ) -> User:
        """
        Deactivate a user account.
        """

        user = self.repository.get_by_email(email)

        if user is None:
            raise ValueError("User not found.")

        user.is_active = False

        return self.repository.update(user)

    # ---------------------------------------------------------
    # Activate or Deactivate an Account
    # ---------------------------------------------------------
    def set_account_active(
        self,
        user_id: int,
        is_active: bool,
        performed_by: User,
    ) -> User:
        """
        Activate or deactivate an officer's account.

        Args:
            user_id:
                Account to change.

            is_active:
                True to restore access, False to withdraw
                it.

            performed_by:
                Administrator making the change, recorded
                in the audit trail.

        Returns:
            The updated account.

        Raises:
            ValueError:
                The account does not exist, or the change
                would leave the system unusable.

        Deactivation withdraws access without destroying
        the account. The record is kept because detections
        an officer verified, and alerts they acted on,
        remain attributed to them: deleting the account
        would leave that history pointing at nobody.
        """

        user = self.repository.get_by_id(user_id)

        if user is None:
            raise ValueError("User not found.")

        # -----------------------------------------------------
        # Guards
        #
        # Only checked when withdrawing access. Restoring it
        # can never lock anybody out.
        # -----------------------------------------------------

        if not is_active:

            # An administrator who deactivates their own
            # account is signed out by their next request
            # and cannot reverse it, because reversing it
            # requires an administrator.
            if user.id == performed_by.id:
                raise ValueError(
                    "An administrator cannot deactivate "
                    "their own account."
                )

            # Deactivating the last administrator leaves
            # nobody able to provision accounts, which is
            # recoverable only from the server console.
            if (
                user.role == UserRole.ADMIN
                and self.repository.count_other_active_admins(
                    user.id
                )
                == 0
            ):
                raise ValueError(
                    "This is the only active administrator. "
                    "Assign another administrator before "
                    "deactivating this account."
                )

        # -----------------------------------------------------
        # Apply the change
        #
        # Returned unchanged when the account is already in
        # the requested state, so that repeating the request
        # does not write a second audit entry for a change
        # that did not happen.
        # -----------------------------------------------------

        if user.is_active == is_active:
            return user

        user.is_active = is_active

        self.db.add(
            AuditLog(
                user_id=performed_by.id,
                action=(
                    "USER_ACTIVATED"
                    if is_active
                    else "USER_DEACTIVATED"
                ),
                entity_type="User",
                entity_id=user.id,
                detail=(
                    f"Account {user.email} "
                    f"{'activated' if is_active else 'deactivated'} "
                    f"by {performed_by.email}."
                ),
            )
        )

        return self.repository.update(user)