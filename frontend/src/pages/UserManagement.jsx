/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: User Management Page
 *
 * Purpose:
 *   Lets an administrator provision officer accounts and
 *   assign the area each one is responsible for.
 *
 * Responsibilities:
 *   - List every account with its role and jurisdiction.
 *   - Create an officer account.
 *   - Reassign an officer's role or jurisdiction.
 *   - Deactivate an account, and restore it later.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Note:
 *   Assigning a jurisdiction here is what makes an officer
 *   account usable. Until one is assigned, the server
 *   refuses every record and the officer sees empty lists.
 *
 *   This page is shown only to administrators, but that is
 *   presentation. The endpoints it calls are themselves
 *   restricted to administrators, so hiding the page is not
 *   what protects them.
 * ===========================================================
 */

import { useCallback, useEffect, useState } from "react";

import {
  AlertTriangle,
  Check,
  Copy,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  ShieldCheck,
  UserCheck,
  UserX,
  X,
} from "lucide-react";

import api from "../services/api";
import { getApiErrorMessage } from "../services/apiError";
import { ROLES } from "../services/auth";
import {
  normalizeZambianPhoneNumber,
  validateZambianPhoneNumber,
} from "../services/phoneNumber";

// ---------------------------------------------------------
// Role options offered when provisioning an account
// ---------------------------------------------------------

const ROLE_OPTIONS = [
  {
    value: ROLES.DISTRICT_OFFICER,
    label: "District Forestry Officer",
    help: "Sees forest areas, detections and alerts in one district.",
  },
  {
    value: ROLES.PROVINCIAL_OFFICER,
    label: "Provincial Forestry Officer",
    help: "Sees every district within one province.",
  },
  {
    value: ROLES.ADMIN,
    label: "Administrator",
    help:
      "Provisions accounts and configures thresholds. " +
      "Holds no operational alert duties.",
  },
];

const EMPTY_FORM = {
  full_name: "",
  email: "",
  phone_number: "",
  password: "",
  role: ROLES.DISTRICT_OFFICER,
  province_id: "",
  district_id: "",
};

/**
 * Describe an account's jurisdiction for the table.
 *
 * @param {object} user
 * @param {Array} districts
 * @param {Array} provinces
 * @returns {string}
 */
function jurisdictionLabel(user, districts, provinces) {
  if (user.role === ROLES.ADMIN) {
    return "National";
  }

  if (user.role === ROLES.DISTRICT_OFFICER) {
    const district = districts.find(
      (item) => item.id === user.district_id
    );

    return district
      ? `${district.name} District`
      : "Not assigned";
  }

  if (user.role === ROLES.PROVINCIAL_OFFICER) {
    const province = provinces.find(
      (item) => item.id === user.province_id
    );

    return province
      ? `${province.name} Province`
      : "Not assigned";
  }

  return "Not assigned";
}

/**
 * Report whether an officer account cannot yet see records.
 *
 * @param {object} user
 * @returns {boolean}
 */
function isUnassigned(user) {
  if (user.role === ROLES.ADMIN) {
    return false;
  }

  if (user.role === ROLES.DISTRICT_OFFICER) {
    return !user.district_id;
  }

  if (user.role === ROLES.PROVINCIAL_OFFICER) {
    return !user.province_id;
  }

  return true;
}

function UserManagement() {
  const [users, setUsers] = useState([]);
  const [districts, setDistricts] = useState([]);
  const [provinces, setProvinces] = useState([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // -------------------------------------------------------
  // Password reset
  //
  // resetTarget is the account the confirmation dialog is
  // asking about. issuedPassword holds the generated
  // password for as long as its dialog is open, and only
  // that long: it is never written to localStorage, never
  // added to the users list, and discarded when the dialog
  // closes. An administrator who loses it issues another
  // one, which is the safe direction to fail in.
  // -------------------------------------------------------

  const [resetTarget, setResetTarget] = useState(null);
  const [resetting, setResetting] = useState(false);
  const [issuedPassword, setIssuedPassword] = useState(null);
  const [copied, setCopied] = useState(false);

  // -------------------------------------------------------
  // Load accounts and the jurisdictions they can be given
  // -------------------------------------------------------

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const [userList, districtList, provinceList] =
        await Promise.all([
          api.get("/users"),
          api.get("/districts"),
          api.get("/provinces"),
        ]);

      setUsers(userList.data || []);
      setDistricts(districtList.data || []);
      setProvinces(provinceList.data || []);

      return Array.isArray(userList.data) ? userList.data : [];
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          "Accounts could not be loaded."
      );

      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // -------------------------------------------------------
  // Form handling
  // -------------------------------------------------------

  const updateField = (field, value) => {
    setForm((previous) => {
      const next = { ...previous, [field]: value };

      // Changing the role clears the previous jurisdiction.
      // The server rejects a district on a provincial
      // officer, so leaving a stale value behind would
      // produce a confusing rejection.
      if (field === "role") {
        next.province_id = "";
        next.district_id = "";
      }

      return next;
    });
  };

  const openCreateForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormOpen(true);
    setNotice(null);
  };

  const openEditForm = (user) => {
    setEditingId(user.id);

    setForm({
      full_name: user.full_name || "",
      email: user.email || "",
      phone_number: user.phone_number || "",
      password: "",
      role: user.role,
      province_id: user.province_id || "",
      district_id: user.district_id || "",
    });

    setFormOpen(true);
    setNotice(null);
  };

  const closeForm = () => {
    setFormOpen(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
  };

  /**
   * Build the request body.
   *
   * Jurisdiction fields are sent only when they apply to
   * the chosen role, because the server rejects a
   * combination that states an authority twice.
   */
  const buildPayload = () => {
    const payload = {
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      phone_number: form.phone_number.trim() || null,
      role: form.role,
      province_id: null,
      district_id: null,
    };

    if (form.role === ROLES.DISTRICT_OFFICER) {
      payload.district_id = Number(form.district_id) || null;
    }

    if (form.role === ROLES.PROVINCIAL_OFFICER) {
      payload.province_id = Number(form.province_id) || null;
    }

    return payload;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    const phoneError = validateZambianPhoneNumber(
      form.phone_number
    );

    if (phoneError) {
      setError(phoneError);
      setNotice(null);
      return;
    }

    setSaving(true);
    setError(null);
    setNotice(null);

    try {
      const payload = buildPayload();
      const expectedPhoneNumber = normalizeZambianPhoneNumber(
        payload.phone_number
      );
      let savedUser;

      if (editingId) {
        const response = await api.put(
          `/users/${editingId}`,
          payload
        );
        savedUser = response.data;
      } else {
        const response = await api.post("/users", {
          ...payload,
          password: form.password,
        });
        savedUser = response.data;
      }

      if (
        !savedUser ||
        !Object.prototype.hasOwnProperty.call(
          savedUser,
          "phone_number"
        ) ||
        (savedUser.phone_number || null) !== expectedPhoneNumber
      ) {
        throw new Error(
          "The API did not confirm the saved phone number. " +
          "Check that the running FastAPI backend includes " +
          "phone-number support."
        );
      }

      const refreshedUsers = await load();
      const refreshedUser = refreshedUsers?.find(
        (user) => user.id === savedUser.id
      );

      if (
        !refreshedUser ||
        (refreshedUser.phone_number || null) !== expectedPhoneNumber
      ) {
        throw new Error(
          "The refreshed user list did not confirm the saved phone number. " +
          "The account may have been updated, but its saved value could " +
          "not be verified. Check the API and reload the list."
        );
      }

      closeForm();
      setNotice(editingId ? "Account updated." : "Account created.");
    } catch (requestError) {
      setError(
        getApiErrorMessage(
          requestError,
          "The account could not be saved."
        )
      );
    } finally {
      setSaving(false);
    }
  };

  /**
   * Withdraw or restore an account's access.
   *
   * The account is never deleted. Detections an officer
   * verified and alerts they acted on stay attributed to
   * them, so removing the record would leave that history
   * pointing at nobody.
   *
   * The server refuses a change that would leave nobody
   * able to administer the system, and that refusal is
   * shown here rather than being second-guessed before the
   * request is sent.
   *
   * @param {object} user
   * @param {boolean} nextActive
   */
  const handleSetActive = async (user, nextActive) => {
    const confirmed = window.confirm(
      nextActive
        ? `Restore access for ${user.full_name}? ` +
            "They will be able to sign in again."
        : `Deactivate the account for ${user.full_name}? ` +
            "They will no longer be able to sign in."
    );

    if (!confirmed) {
      return;
    }

    setError(null);

    try {
      await api.post(
        `/users/${user.id}/${
          nextActive ? "activate" : "deactivate"
        }`
      );

      setNotice(
        nextActive
          ? `${user.full_name} was reactivated.`
          : `${user.full_name} was deactivated.`
      );

      await load();
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          (nextActive
            ? "The account could not be reactivated."
            : "The account could not be deactivated.")
      );
    }
  };

  // -------------------------------------------------------
  // Password reset
  // -------------------------------------------------------

  /**
   * Generate a temporary password for the selected account.
   *
   * The administrator supplies nothing: the password is
   * made on the server from a cryptographic random source.
   * This only asks for one and shows what came back.
   */
  const handleResetPassword = async () => {
    // A second click while the first request is in flight
    // would reset the password twice and leave the
    // administrator holding a password that no longer works.
    if (!resetTarget || resetting) {
      return;
    }

    setResetting(true);
    setError(null);

    try {
      const response = await api.post(
        `/users/${resetTarget.id}/reset-password`
      );

      setIssuedPassword({
        fullName:
          response.data?.full_name || resetTarget.full_name,
        email: response.data?.email || resetTarget.email,
        password: response.data?.temporary_password || "",
      });

      setResetTarget(null);
      setCopied(false);

      /*
        The list is deliberately NOT reloaded here. It is
        reloaded when the dialog closes instead.

        Reloading now would put a request in flight while an
        unrecoverable password is on screen, and when an
        administrator resets their own password that request
        is refused: their token was issued under the password
        that has just been replaced, so the API client
        reports the session as ended, this page unmounts and
        the password goes with it, never having been read.
      */
    } catch (requestError) {
      /*
        Two different things return 404 here. The endpoint
        answers "User not found." when the account is gone.
        A server that does not carry this endpoint at all
        answers FastAPI's own "Not Found", which told an
        administrator nothing: the button simply reported two
        words and the feature looked broken.

        The usual cause is a running server older than the
        interface talking to it.
      */
      const status = requestError?.response?.status;

      const detail =
        requestError?.response?.data?.detail;

      const routeMissing =
        status === 404 &&
        typeof detail === "string" &&
        !detail.toLowerCase().includes("user");

      setError(
        routeMissing
          ? "This server does not provide the password " +
              "reset endpoint. It is running an older " +
              "version than this interface and needs to be " +
              "restarted or updated."
          : getApiErrorMessage(
              requestError,
              "The password could not be reset."
            )
      );

      setResetTarget(null);
    } finally {
      setResetting(false);
    }
  };

  /**
   * Copy the generated password to the clipboard.
   *
   * The Clipboard API needs a secure context and permission,
   * and has neither when the page is served over plain HTTP
   * to something other than localhost. A failure is reported
   * rather than silently doing nothing, because the password
   * is on screen and can still be read off it.
   */
  const handleCopyPassword = async () => {
    if (!issuedPassword?.password) {
      return;
    }

    try {
      await navigator.clipboard.writeText(
        issuedPassword.password
      );

      setCopied(true);
    } catch {
      setCopied(false);

      setError(
        "The password could not be copied automatically. " +
          "Select it and copy it manually."
      );
    }
  };

  /**
   * Dismiss the generated password.
   *
   * Once this runs the password is gone from the interface
   * and cannot be shown again.
   */
  const closeIssuedPassword = () => {
    setIssuedPassword(null);
    setCopied(false);

    setNotice(
      "A temporary password was issued. The officer must " +
        "set a new one at their next sign-in."
    );

    // Safe to reload now: the password has been read and
    // discarded, so a refused request can no longer cost
    // anything that cannot be recovered. An administrator
    // who reset their own password is signed out at this
    // point, which is correct — their token was issued
    // under the password they have just replaced.
    load();
  };

  // -------------------------------------------------------
  // Render
  // -------------------------------------------------------

  const unassignedCount = users.filter(isUnassigned).length;

  return (
    <div className="user-management-page">
      <div className="page-heading">
        <div>
          <h2>
            <ShieldCheck size={20} /> User Management
          </h2>

          <p>
            Provision officer accounts and assign the area
            each officer is responsible for.
          </p>
        </div>

        <button
          type="button"
          className="primary-button"
          onClick={openCreateForm}
        >
          <Plus size={16} /> New account
        </button>
      </div>

      {error && (
        <div className="jurisdiction-notice">
          <AlertTriangle size={18} />
          <div>
            <span>{error}</span>
          </div>
        </div>
      )}

      {notice && (
        <div className="success-notice">
          <Check size={18} />
          <span>{notice}</span>
        </div>
      )}

      {/*
        An officer with no jurisdiction is refused every
        record, so their account looks broken to them.
        Surfacing the count here means an administrator can
        see the problem without opening each account.
      */}
      {unassignedCount > 0 && (
        <div className="jurisdiction-notice">
          <AlertTriangle size={18} />
          <div>
            <strong>
              {unassignedCount} account
              {unassignedCount === 1 ? "" : "s"} without a
              jurisdiction.
            </strong>
            <span>
              These officers can sign in but will see no
              forest areas, detections or alerts until an
              area is assigned to them.
            </span>
          </div>
        </div>
      )}

      {formOpen && (
        <form
          className="user-form card"
          onSubmit={handleSubmit}
        >
          <div className="user-form-header">
            <h3>
              {editingId
                ? "Edit account"
                : "New officer account"}
            </h3>

            <button
              type="button"
              className="icon-button"
              onClick={closeForm}
              aria-label="Close"
            >
              <X size={18} />
            </button>
          </div>

          <div className="user-form-grid">
            <label>
              <span>Full name</span>
              <input
                type="text"
                required
                minLength={3}
                value={form.full_name}
                onChange={(event) =>
                  updateField(
                    "full_name",
                    event.target.value
                  )
                }
              />
            </label>

            <label>
              <span>Email address</span>
              <input
                type="email"
                required
                value={form.email}
                onChange={(event) =>
                  updateField("email", event.target.value)
                }
              />
            </label>

            <label>
              <span>Phone number for SMS alerts (optional)</span>
              <input
                type="tel"
                autoComplete="tel"
                inputMode="tel"
                value={form.phone_number}
                placeholder="+260 971 234 567"
                aria-describedby="officer-phone-help"
                onChange={(event) =>
                  updateField("phone_number", event.target.value)
                }
              />
              <small id="officer-phone-help">
                Use a Zambian mobile number. Leave blank if it has not
                been provided.
              </small>
            </label>

            {!editingId && (
              <label>
                <span>Temporary password</span>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={form.password}
                  onChange={(event) =>
                    updateField(
                      "password",
                      event.target.value
                    )
                  }
                />
                <small>
                  The officer is required to change this on
                  first sign-in.
                </small>
              </label>
            )}

            <label>
              <span>Role</span>
              <select
                value={form.role}
                onChange={(event) =>
                  updateField("role", event.target.value)
                }
              >
                {ROLE_OPTIONS.map((option) => (
                  <option
                    key={option.value}
                    value={option.value}
                  >
                    {option.label}
                  </option>
                ))}
              </select>
              <small>
                {
                  ROLE_OPTIONS.find(
                    (option) => option.value === form.role
                  )?.help
                }
              </small>
            </label>

            {/*
              Only the field that applies to the chosen role
              is offered. A district officer's province is
              implied by their district, and an
              administrator has no jurisdiction at all.
            */}
            {form.role === ROLES.DISTRICT_OFFICER && (
              <label>
                <span>District</span>
                <select
                  required
                  value={form.district_id}
                  onChange={(event) =>
                    updateField(
                      "district_id",
                      event.target.value
                    )
                  }
                >
                  <option value="">
                    Select a district
                  </option>

                  {districts.map((district) => (
                    <option
                      key={district.id}
                      value={district.id}
                    >
                      {district.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {form.role === ROLES.PROVINCIAL_OFFICER && (
              <label>
                <span>Province</span>
                <select
                  required
                  value={form.province_id}
                  onChange={(event) =>
                    updateField(
                      "province_id",
                      event.target.value
                    )
                  }
                >
                  <option value="">
                    Select a province
                  </option>

                  {provinces.map((province) => (
                    <option
                      key={province.id}
                      value={province.id}
                    >
                      {province.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            {form.role === ROLES.ADMIN && (
              <div className="role-note">
                An administrator is not assigned a
                jurisdiction. Administration is national.
              </div>
            )}
          </div>

          <div className="user-form-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={closeForm}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="primary-button"
              disabled={saving}
            >
              {saving
                ? "Saving..."
                : editingId
                  ? "Save changes"
                  : "Create account"}
            </button>
          </div>
        </form>
      )}

      <div className="card">
        {loading ? (
          <p className="muted">Loading accounts...</p>
        ) : users.length === 0 ? (
          <p className="muted">No accounts exist yet.</p>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Phone</th>
                <th>Role</th>
                <th>Jurisdiction</th>
                <th>Status</th>
                <th aria-label="Actions" />
              </tr>
            </thead>

            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.full_name}</td>

                  <td>{user.email}</td>

                  <td>{user.phone_number || "Not recorded"}</td>

                  <td>
                    {ROLE_OPTIONS.find(
                      (option) =>
                        option.value === user.role
                    )?.label || user.role}
                  </td>

                  <td>
                    <span
                      className={
                        isUnassigned(user)
                          ? "tag tag-warning"
                          : "tag"
                      }
                    >
                      {jurisdictionLabel(
                        user,
                        districts,
                        provinces
                      )}
                    </span>
                  </td>

                  <td>
                    <span
                      className={
                        user.is_active
                          ? "tag tag-success"
                          : "tag tag-muted"
                      }
                    >
                      {user.is_active
                        ? "Active"
                        : "Inactive"}
                    </span>
                  </td>

                  <td className="row-actions">
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => openEditForm(user)}
                      title="Edit account"
                      aria-label="Edit account"
                    >
                      <Pencil size={16} />
                    </button>

                    {/*
                      A deactivated account keeps its row
                      and its reactivation control. Without
                      one, withdrawing access is a decision
                      that cannot be reversed from the
                      interface, and an officer returning
                      from leave would need a second
                      account.
                    */}
                    {/*
                      Offered for any account, including a
                      deactivated one: an account is often
                      restored and reset in the same breath,
                      and the server refuses nothing here
                      that it would allow elsewhere.
                    */}
                    <button
                      type="button"
                      className="icon-button"
                      onClick={() => {
                        setError(null);
                        setResetTarget(user);
                      }}
                      title="Reset password"
                      aria-label={
                        `Reset password for ${user.full_name}`
                      }
                    >
                      <KeyRound size={16} />
                    </button>

                    {user.is_active ? (
                      <button
                        type="button"
                        className="icon-button danger"
                        onClick={() =>
                          handleSetActive(user, false)
                        }
                        title="Deactivate account"
                        aria-label="Deactivate account"
                      >
                        <UserX size={16} />
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="icon-button"
                        onClick={() =>
                          handleSetActive(user, true)
                        }
                        title="Reactivate account"
                        aria-label="Reactivate account"
                      >
                        <UserCheck size={16} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* =====================================================
          CONFIRM A RESET

          Names the officer and their email address. An
          administrator working down a list of accounts
          should not have to trust that the dialog refers to
          the row they meant to click.
          ===================================================== */}
      {resetTarget && (
        <div
          className="dialog-backdrop"
          role="presentation"
          onClick={() => {
            if (!resetting) {
              setResetTarget(null);
            }
          }}
        >
          <div
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-confirm-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="dialog-header">
              <KeyRound size={18} aria-hidden="true" />

              <h2 id="reset-confirm-title">
                Reset password
              </h2>
            </div>

            <div className="dialog-body">
              <p>
                A new temporary password will be generated
                for:
              </p>

              <div className="dialog-subject">
                <strong>{resetTarget.full_name}</strong>
                <span>{resetTarget.email}</span>
              </div>

              <p className="dialog-note">
                Their current password will stop working
                immediately, and any session they have open
                will end. They will be required to set a new
                password when they next sign in.
              </p>
            </div>

            <div className="dialog-actions">
              <button
                type="button"
                className="secondary-button"
                onClick={() => setResetTarget(null)}
                disabled={resetting}
              >
                Cancel
              </button>

              <button
                type="button"
                className="primary-button"
                onClick={handleResetPassword}
                disabled={resetting}
              >
                {resetting ? (
                  <>
                    <Loader2
                      size={16}
                      className="refresh-spin"
                      aria-hidden="true"
                    />
                    Generating...
                  </>
                ) : (
                  <>
                    <KeyRound size={16} aria-hidden="true" />
                    Generate Temporary Password
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================
          THE GENERATED PASSWORD

          Shown once. Closing this dialog discards it, and
          nothing in the interface can retrieve it again: the
          server keeps only the hash. An administrator who
          loses it issues another, which is the safe
          direction to fail in.

          The backdrop does not close this one. A stray click
          beside the dialog would throw away a password that
          cannot be recovered.
          ===================================================== */}
      {issuedPassword && (
        <div className="dialog-backdrop" role="presentation">
          <div
            className="dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="issued-password-title"
          >
            <div className="dialog-header">
              <Check size={18} aria-hidden="true" />

              <h2 id="issued-password-title">
                Temporary password issued
              </h2>
            </div>

            <div className="dialog-body">
              <div className="dialog-subject">
                <strong>{issuedPassword.fullName}</strong>
                <span>{issuedPassword.email}</span>
              </div>

              <label
                className="dialog-field-label"
                htmlFor="issued-password"
              >
                Temporary password
              </label>

              <div className="password-reveal">
                <input
                  id="issued-password"
                  type="text"
                  value={issuedPassword.password}
                  readOnly
                  // Selecting on focus gives a manual copy
                  // when the clipboard is unavailable, which
                  // it is over plain HTTP.
                  onFocus={(event) =>
                    event.target.select()
                  }
                />

                <button
                  type="button"
                  className="secondary-button"
                  onClick={handleCopyPassword}
                >
                  {copied ? (
                    <>
                      <Check size={15} aria-hidden="true" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy size={15} aria-hidden="true" />
                      Copy
                    </>
                  )}
                </button>
              </div>

              <div className="dialog-warning" role="note">
                <AlertTriangle size={16} aria-hidden="true" />

                <div>
                  <strong>
                    This password is shown once.
                  </strong>

                  <span>
                    Give it to the officer in person or by
                    telephone. Do not send it by email or
                    text message, and do not write it down
                    where it will outlive the sign-in. It
                    cannot be displayed again once this
                    dialog is closed.
                  </span>
                </div>
              </div>
            </div>

            <div className="dialog-actions">
              <button
                type="button"
                className="primary-button"
                onClick={closeIssuedPassword}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default UserManagement;
