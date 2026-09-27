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
  Pencil,
  Plus,
  ShieldCheck,
  UserCheck,
  UserX,
  X,
} from "lucide-react";

import api from "../services/api";
import { ROLES } from "../services/auth";

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
    } catch (requestError) {
      setError(
        requestError?.response?.data?.detail ||
          "Accounts could not be loaded."
      );
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

    setSaving(true);
    setError(null);
    setNotice(null);

    try {
      const payload = buildPayload();

      if (editingId) {
        await api.put(`/users/${editingId}`, payload);

        setNotice("Account updated.");
      } else {
        await api.post("/users", {
          ...payload,
          password: form.password,
        });

        setNotice("Account created.");
      }

      closeForm();
      await load();
    } catch (requestError) {
      const detail = requestError?.response?.data?.detail;

      // Validation failures arrive as a list of field
      // errors. The message is the useful part.
      const message = Array.isArray(detail)
        ? detail.map((item) => item.msg).join(" ")
        : detail;

      setError(
        message || "The account could not be saved."
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
    </div>
  );
}

export default UserManagement;
