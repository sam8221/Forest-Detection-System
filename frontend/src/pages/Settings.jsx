/*
 * =========================================================
 * FORESTWATCH ZAMBIA
 * SETTINGS PAGE
 * =========================================================
 * Purpose:
 *   Provides authenticated account management functionality
 *   for ForestWatch Zambia users.
 *
 * Responsibilities:
 *   - Display the authenticated user's profile.
 *   - Update the user's full name.
 *   - Change the authenticated user's password.
 *   - Enforce password security requirements.
 *   - Display administrator-only user management.
 *   - Deactivate active user accounts.
 *
 * Layout:
 *   - Profile Settings: 500px
 *   - Change Password: 500px
 *   - User Management: 900px
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Author:
 *   Samuel Bikiloni
 * =========================================================
 */

import React, { useEffect, useState } from "react";

const API_URL = "http://127.0.0.1:8000";

export default function Settings() {
  /* Store the authenticated user's profile information. */
  const [profile, setProfile] = useState(null);

  /* Store registered users displayed to administrators. */
  const [users, setUsers] = useState([]);

  /* Track page, user-table, profile, and password loading states. */
  const [loading, setLoading] = useState(true);
  const [usersLoading, setUsersLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [passwordSaving, setPasswordSaving] = useState(false);

  /* Store general page feedback and password-specific errors. */
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [passwordError, setPasswordError] = useState("");

  /* Store editable profile information. */
  const [form, setForm] = useState({
    full_name: "",
    email: "",
  });

  /* Store password-change form values. */
  const [passwordForm, setPasswordForm] = useState({
    current_password: "",
    new_password: "",
    confirm_password: "",
  });

  /*
   * Retrieve the JWT access token created during authentication.
   */
  const getToken = () => {
    return (
      localStorage.getItem("access_token") ||
      localStorage.getItem("token")
    );
  };

  /*
   * Convert FastAPI error responses into readable messages.
   * Supports standard API errors and Pydantic validation errors.
   */
  const getErrorMessage = async (response, fallback) => {
    try {
      const data = await response.json();

      if (typeof data.detail === "string") {
        return data.detail;
      }

      if (Array.isArray(data.detail)) {
        return data.detail
          .map((item) => item.msg)
          .filter(Boolean)
          .join(", ");
      }

      return fallback;
    } catch {
      return fallback;
    }
  };

  /*
   * Retrieve the currently authenticated user's profile.
   */
  const loadProfile = async () => {
    try {
      const token = getToken();

      if (!token) {
        throw new Error(
          "No access token found. Please log in again."
        );
      }

      const response = await fetch(
        `${API_URL}/api/v1/users/profile`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(
          await getErrorMessage(
            response,
            "Unable to load your account information."
          )
        );
      }

      const data = await response.json();

      setProfile(data);

      setForm({
        full_name: data.full_name || "",
        email: data.email || "",
      });

      return data;
    } catch (err) {
      console.error("Settings profile error:", err);
      throw err;
    }
  };

  /*
   * Retrieve all registered users for administrator management.
   */
  const loadUsers = async () => {
    try {
      setUsersLoading(true);

      const token = getToken();

      if (!token) {
        throw new Error(
          "No access token found. Please log in again."
        );
      }

      const response = await fetch(
        `${API_URL}/api/v1/users`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(
          await getErrorMessage(
            response,
            "Unable to load system users."
          )
        );
      }

      const data = await response.json();

      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Users loading error:", err);
      throw err;
    } finally {
      setUsersLoading(false);
    }
  };

  /*
   * Load the authenticated profile when the settings page
   * is opened.
   */
  useEffect(() => {
    const initializeSettings = async () => {
      try {
        setLoading(true);
        setError("");

        const user = await loadProfile();

        /*
         * Only administrators require access to the
         * complete system-user list.
         */
        if (
          String(user?.role || "").toUpperCase() === "ADMIN"
        ) {
          await loadUsers();
        }
      } catch (err) {
        setError(
          err.message ||
            "Unable to load your settings."
        );
      } finally {
        setLoading(false);
      }
    };

    initializeSettings();
  }, []);

  /*
   * Update profile form state when an input changes.
   */
  const handleChange = (event) => {
    const { name, value } = event.target;

    setForm((previous) => ({
      ...previous,
      [name]: value,
    }));

    setError("");
  };

  /*
   * Update password fields and clear password-specific
   * validation messages as the user edits the form.
   */
  const handlePasswordChange = (event) => {
    const { name, value } = event.target;

    setPasswordForm((previous) => ({
      ...previous,
      [name]: value,
    }));

    setPasswordError("");
    setError("");
    setMessage("");
  };

  /*
   * Validate the password against the ForestWatch Zambia
   * password security policy.
   */
  const validatePassword = (password) => {
    if (password.length < 8) {
      return "Password must contain at least 8 characters.";
    }

    if (password.length > 128) {
      return "Password must not exceed 128 characters.";
    }

    if (!/[A-Z]/.test(password)) {
      return "Password must contain at least one uppercase letter.";
    }

    if (!/[a-z]/.test(password)) {
      return "Password must contain at least one lowercase letter.";
    }

    if (!/[0-9]/.test(password)) {
      return "Password must contain at least one number.";
    }

    if (!/[^A-Za-z0-9]/.test(password)) {
      return "Password must contain at least one special character.";
    }

    return "";
  };

  /*
   * Submit the authenticated user's profile changes.
   */
  const handleSave = async (event) => {
    event.preventDefault();

    try {
      setSaving(true);
      setError("");
      setMessage("");

      const token = getToken();

      if (!token) {
        throw new Error(
          "No access token found. Please log in again."
        );
      }

      if (!profile?.id) {
        throw new Error("User ID was not found.");
      }

      if (form.full_name.trim().length < 3) {
        throw new Error(
          "Full name must contain at least 3 characters."
        );
      }

      const response = await fetch(
        `${API_URL}/api/v1/users/${profile.id}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            full_name: form.full_name.trim(),
          }),
        }
      );

      if (!response.ok) {
        throw new Error(
          await getErrorMessage(
            response,
            "Unable to update your profile."
          )
        );
      }

      const data = await response.json();

      setProfile(data);

      setForm({
        full_name: data.full_name || "",
        email: data.email || "",
      });

      setMessage(
        "Profile updated successfully."
      );

      /*
       * Refresh administrator data after a successful
       * profile update so the user table remains current.
       */
      if (
        String(data.role || "").toUpperCase() === "ADMIN"
      ) {
        await loadUsers();
      }
    } catch (err) {
      console.error("Profile update error:", err);

      setError(
        err.message ||
          "Unable to update your profile."
      );
    } finally {
      setSaving(false);
    }
  };

  /*
   * Validate and submit the authenticated user's
   * password-change request.
   */
  const handleChangePassword = async (event) => {
    event.preventDefault();

    try {
      setPasswordSaving(true);
      setPasswordError("");
      setError("");
      setMessage("");

      const currentPassword =
        passwordForm.current_password;

      const newPassword =
        passwordForm.new_password;

      const confirmPassword =
        passwordForm.confirm_password;

      /*
       * Ensure all password fields have been completed.
       */
      if (
        !currentPassword ||
        !newPassword ||
        !confirmPassword
      ) {
        throw new Error(
          "Please complete all password fields."
        );
      }

      /*
       * Apply the same password policy enforced
       * by the backend Pydantic schema.
       */
      const passwordValidationError =
        validatePassword(newPassword);

      if (passwordValidationError) {
        throw new Error(
          passwordValidationError
        );
      }

      /*
       * Ensure the confirmation password matches
       * the new password.
       */
      if (newPassword !== confirmPassword) {
        throw new Error(
          "New password and confirmation password do not match."
        );
      }

      const token = getToken();

      if (!token) {
        throw new Error(
          "No access token found. Please log in again."
        );
      }

      /*
       * Submit the authenticated password-change request.
       * The FastAPI endpoint accepts POST requests.
       */
      const response = await fetch(
        `${API_URL}/api/v1/auth/change-password`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword,
          }),
        }
      );

      if (!response.ok) {
        const backendMessage =
          await getErrorMessage(
            response,
            "Unable to change your password."
          );

        throw new Error(backendMessage);
      }

      /*
       * Clear password fields after a successful
       * password update.
       */
      setPasswordForm({
        current_password: "",
        new_password: "",
        confirm_password: "",
      });

      setPasswordError("");

      setMessage(
        "Password changed successfully."
      );
    } catch (err) {
      console.error(
        "Password change error:",
        err
      );

      /*
       * Display password errors directly inside
       * the Change Password section.
       */
      setPasswordError(
        err.message ||
          "Unable to change your password."
      );
    } finally {
      setPasswordSaving(false);
    }
  };

  /*
   * Deactivate another user's account.
   * The authenticated administrator cannot deactivate
   * their own account.
   */
  const handleDeactivate = async (userId) => {
    if (userId === profile?.id) {
      setError(
        "You cannot deactivate your own administrator account."
      );
      return;
    }

    const confirmed = window.confirm(
      "Are you sure you want to deactivate this user account?"
    );

    if (!confirmed) {
      return;
    }

    try {
      setError("");
      setMessage("");

      const token = getToken();

      if (!token) {
        throw new Error(
          "No access token found. Please log in again."
        );
      }

      const response = await fetch(
        `${API_URL}/api/v1/users/${userId}`,
        {
          method: "DELETE",
          headers: {
            Accept: "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        throw new Error(
          await getErrorMessage(
            response,
            "Unable to deactivate user."
          )
        );
      }

      setMessage(
        "User account deactivated successfully."
      );

      await loadUsers();
    } catch (err) {
      console.error(
        "Deactivate user error:",
        err
      );

      setError(
        err.message ||
          "Unable to deactivate the user."
      );
    }
  };

  /*
   * Display a loading state while account information
   * is retrieved from the backend.
   */
  if (loading) {
    return (
      <div className="forest-page">
        <div className="message-card">
          <div className="loading-spinner">
            ⟳
          </div>

          <h3>Loading Settings</h3>

          <p>
            Retrieving your ForestWatch
            Zambia account information...
          </p>
        </div>
      </div>
    );
  }

  /*
   * Determine whether the authenticated user has
   * administrator privileges.
   */
  const isAdmin =
    String(profile?.role || "").toUpperCase() ===
    "ADMIN";

  return (
    <div className="forest-page">

      {/* =====================================================
          PAGE HEADER
      ===================================================== */}
      <div className="page-header">
        <div>
          <h1>Settings</h1>

          <p>
            Manage your ForestWatch Zambia
            account information and preferences.
          </p>
        </div>
      </div>

      {/* =====================================================
          GENERAL ERROR MESSAGE
      ===================================================== */}
      {error && (
        <div className="error-card">
          <div className="error-icon">
            ⚠
          </div>

          <div>
            <h3>
              Unable to Complete Request
            </h3>

            <p>{error}</p>

            <button
              type="button"
              className="retry-button"
              onClick={async () => {
                try {
                  setError("");

                  const user =
                    await loadProfile();

                  if (
                    String(
                      user?.role || ""
                    ).toUpperCase() === "ADMIN"
                  ) {
                    await loadUsers();
                  }
                } catch (err) {
                  setError(
                    err.message ||
                      "Unable to reload settings."
                  );
                }
              }}
            >
              Try Again
            </button>
          </div>
        </div>
      )}

      {/* =====================================================
          SUCCESS MESSAGE
      ===================================================== */}
      {message && (
        <div className="message-card">
          <h3>Success</h3>

          <p>{message}</p>
        </div>
      )}

      {profile && (
        <>
          {/* =================================================
              PROFILE SETTINGS
          ================================================= */}
          <div className="section-heading">
            <div>
              <h2>Profile Settings</h2>

              <p>
                View and update your
                ForestWatch Zambia account.
              </p>
            </div>
          </div>

          <div
            className="settings-card profile-settings-card"
            style={{
              width: "500px",
              maxWidth: "100%",
            }}
          >
            <form onSubmit={handleSave}>

              {/* Editable account name. */}
              <div className="settings-field">
                <label htmlFor="full_name">
                  Full Name
                </label>

                <input
                  id="full_name"
                  name="full_name"
                  type="text"
                  value={form.full_name}
                  onChange={handleChange}
                  placeholder="Enter your full name"
                  required
                />
              </div>

              {/* Email remains read-only from the settings page. */}
              <div className="settings-field">
                <label htmlFor="email">
                  Email Address
                </label>

                <input
                  id="email"
                  name="email"
                  type="email"
                  value={form.email}
                  disabled
                />

                <small>
                  Your email address cannot be
                  changed here.
                </small>
              </div>

              {/* Display the authenticated user's system role. */}
              <div className="settings-field">
                <label htmlFor="role">
                  Account Role
                </label>

                <input
                  id="role"
                  type="text"
                  value={
                    profile.role || "USER"
                  }
                  disabled
                />
              </div>

              {/* Display the current account status. */}
              <div className="settings-field">
                <label htmlFor="account-status">
                  Account Status
                </label>

                <input
                  id="account-status"
                  type="text"
                  value={
                    profile.is_active
                      ? "Active"
                      : "Inactive"
                  }
                  disabled
                />
              </div>

              {/* Save profile changes. */}
              <div className="settings-actions">
                <button
                  type="submit"
                  className="refresh-button"
                  disabled={saving}
                >
                  {saving
                    ? "Saving..."
                    : "Save Changes"}
                </button>
              </div>
            </form>
          </div>

          {/* =================================================
              CHANGE PASSWORD
          ================================================= */}
          <div
            className="section-heading"
            style={{
              marginTop: "34px",
            }}
          >
            <div>
              <h2>Change Password</h2>

              <p>
                Update your ForestWatch Zambia
                account password.
              </p>
            </div>
          </div>

          <div
            className="settings-card password-card"
            style={{
              width: "500px",
              maxWidth: "100%",
            }}
          >
            <form onSubmit={handleChangePassword}>

              {/* Verify the existing password. */}
              <div className="settings-field">
                <label htmlFor="current_password">
                  Current Password
                </label>

                <input
                  id="current_password"
                  name="current_password"
                  type="password"
                  value={
                    passwordForm.current_password
                  }
                  onChange={handlePasswordChange}
                  placeholder="Enter your current password"
                  required
                />
              </div>

              {/* Collect the new password. */}
              <div className="settings-field">
                <label htmlFor="new_password">
                  New Password
                </label>

                <input
                  id="new_password"
                  name="new_password"
                  type="password"
                  value={
                    passwordForm.new_password
                  }
                  onChange={handlePasswordChange}
                  placeholder="Enter your new password"
                  minLength={8}
                  maxLength={128}
                  required
                />

                <small>
                  Minimum 8 characters with uppercase,
                  lowercase, number, and special character.
                </small>
              </div>

              {/* Confirm the new password. */}
              <div className="settings-field">
                <label htmlFor="confirm_password">
                  Confirm New Password
                </label>

                <input
                  id="confirm_password"
                  name="confirm_password"
                  type="password"
                  value={
                    passwordForm.confirm_password
                  }
                  onChange={handlePasswordChange}
                  placeholder="Confirm your new password"
                  minLength={8}
                  maxLength={128}
                  required
                />
              </div>

              {/* Display password-specific validation feedback. */}
              {passwordError && (
                <div className="password-error-message">
                  <span>⚠</span>

                  <p>{passwordError}</p>
                </div>
              )}

              {/* Submit the password-change request. */}
              <div className="settings-actions">
                <button
                  type="submit"
                  className="refresh-button"
                  disabled={passwordSaving}
                >
                  {passwordSaving
                    ? "Changing..."
                    : "Change Password"}
                </button>
              </div>
            </form>
          </div>

          {/* =================================================
              ADMINISTRATOR USER MANAGEMENT
          ================================================= */}
          {isAdmin && (
            <div
              className="admin-user-section"
              style={{
                width: "900px",
                maxWidth: "100%",
                marginTop: "40px",
              }}
            >
              <div className="section-heading">
                <div>
                  <h2>User Management</h2>

                  <p>
                    Manage ForestWatch Zambia
                    system users.
                  </p>
                </div>

                <span>
                  {users.length} Users
                </span>
              </div>

              <div
                className="settings-card admin-user-card"
                style={{
                  width: "900px",
                  maxWidth: "100%",
                }}
              >
                {usersLoading ? (
                  <div className="message-card">
                    <div className="loading-spinner">
                      ⟳
                    </div>

                    <h3>Loading Users</h3>

                    <p>
                      Retrieving registered
                      system users...
                    </p>
                  </div>
                ) : users.length === 0 ? (
                  <div className="message-card">
                    <h3>No Users Found</h3>

                    <p>
                      No registered users
                      were found.
                    </p>
                  </div>
                ) : (
                  <div className="user-table-wrapper">
                    <table className="user-table">
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>Full Name</th>
                          <th>Email</th>
                          <th>Role</th>
                          <th>Status</th>
                          <th>Action</th>
                        </tr>
                      </thead>

                      <tbody>
                        {users.map((user) => (
                          <tr key={user.id}>
                            <td>
                              #{user.id}
                            </td>

                            <td>
                              <strong>
                                {user.full_name ||
                                  "Unnamed User"}
                              </strong>

                              {user.id ===
                                profile.id && (
                                <span>
                                  {" "}
                                  (You)
                                </span>
                              )}
                            </td>

                            <td>
                              {user.email}
                            </td>

                            <td>
                              <span className="user-role-badge">
                                {String(
                                  user.role || ""
                                ).toUpperCase()}
                              </span>
                            </td>

                            <td>
                              <span
                                className={
                                  user.is_active
                                    ? "user-status-active"
                                    : "user-status-inactive"
                                }
                              >
                                {user.is_active
                                  ? "ACTIVE"
                                  : "INACTIVE"}
                              </span>
                            </td>

                            <td>
                              {user.id ===
                              profile.id ? (
                                <span className="current-user-label">
                                  Current User
                                </span>
                              ) : user.is_active ? (
                                <button
                                  type="button"
                                  className="deactivate-user-button"
                                  onClick={() =>
                                    handleDeactivate(
                                      user.id
                                    )
                                  }
                                >
                                  Deactivate
                                </button>
                              ) : (
                                <span className="current-user-label">
                                  Deactivated
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}