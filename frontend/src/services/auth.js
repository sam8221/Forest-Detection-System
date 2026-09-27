/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Authentication Service
 *
 * Purpose:
 *   Holds the signed-in officer's identity and jurisdiction.
 *
 * Responsibilities:
 *   - Sign an officer in and store their access token.
 *   - Retrieve the signed-in officer's profile.
 *   - Describe the jurisdiction an account covers.
 *   - Answer role questions asked by the interface.
 *   - Sign an officer out.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import api from "./api";

// ---------------------------------------------------------
// Storage key
//
// Kept in one place so the token is never written under a
// second name by mistake, which would leave a stale token
// behind after signing out.
// ---------------------------------------------------------

export const TOKEN_KEY = "access_token";

// ---------------------------------------------------------
// Roles
//
// These strings must match the UserRole enum on the server.
// ---------------------------------------------------------

export const ROLES = {
  ADMIN: "ADMIN",
  PROVINCIAL_OFFICER: "PROVINCIAL_FORESTRY_OFFICER",
  DISTRICT_OFFICER: "DISTRICT_FORESTRY_OFFICER",
};

/**
 * Sign an officer in and store their access token.
 *
 * The endpoint expects OAuth2 password-form fields, so the
 * body is form-encoded and the email is sent as "username".
 *
 * @param {string} email
 * @param {string} password
 * @returns {Promise<string>} the access token
 */
export async function login(email, password) {
  const form = new URLSearchParams();

  form.append("username", email.trim());
  form.append("password", password);

  const response = await api.post("/auth/login", form, {
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
  });

  const token = response.data?.access_token;

  if (!token) {
    throw new Error("No access token returned by the server.");
  }

  localStorage.setItem(TOKEN_KEY, token);

  return token;
}

/**
 * Retrieve the signed-in officer's profile.
 *
 * Includes the district or province the account covers,
 * with names already resolved by the server.
 *
 * @returns {Promise<object>} the current user
 */
export async function fetchCurrentUser() {
  const response = await api.get("/auth/me");

  return response.data;
}

/**
 * Sign the officer out.
 *
 * Only clears local state. The token itself stays valid on
 * the server until it expires, which is why tokens are
 * short-lived rather than revoked here.
 */
export function logout() {
  localStorage.removeItem(TOKEN_KEY);

  // A token may also be held under this second key. Both
  // are cleared, because a token left behind under either
  // name would let the interface consider the officer
  // signed in after they asked to leave.
  localStorage.removeItem("token");
}

/**
 * Report whether a token is currently stored.
 *
 * This says nothing about whether the token is still valid.
 * Only the server can decide that, and it does so on every
 * request.
 *
 * @returns {boolean}
 */
export function hasStoredToken() {
  return Boolean(localStorage.getItem(TOKEN_KEY));
}

/**
 * Report whether a user administers the system.
 *
 * @param {object|null} user
 * @returns {boolean}
 */
export function isAdministrator(user) {
  return user?.role === ROLES.ADMIN;
}

/**
 * Describe the area an account is responsible for.
 *
 * Used for the label shown beside the officer's name.
 *
 * An administrator is described as national because
 * administration is not tied to a place: the role
 * provisions accounts and configures thresholds rather
 * than reviewing alerts in a particular district.
 *
 * An officer with no jurisdiction assigned is described as
 * unassigned rather than as covering everything, which
 * matches how the server treats them: such an account is
 * refused access to every record until an administrator
 * assigns it a district or province.
 *
 * @param {object|null} user
 * @returns {string}
 */
export function describeJurisdiction(user) {
  if (!user) {
    return "";
  }

  if (isAdministrator(user)) {
    return "All provinces";
  }

  if (user.role === ROLES.DISTRICT_OFFICER) {
    return user.district_name
      ? `${user.district_name} District`
      : "No district assigned";
  }

  if (user.role === ROLES.PROVINCIAL_OFFICER) {
    return user.province_name
      ? `${user.province_name} Province`
      : "No province assigned";
  }

  return "No jurisdiction assigned";
}

/**
 * Present a role in the wording officers use.
 *
 * @param {object|null} user
 * @returns {string}
 */
export function describeRole(user) {
  switch (user?.role) {
    case ROLES.ADMIN:
      return "Administrator";

    case ROLES.PROVINCIAL_OFFICER:
      return "Provincial Forestry Officer";

    case ROLES.DISTRICT_OFFICER:
      return "District Forestry Officer";

    default:
      return "Forestry Department";
  }
}

/**
 * Build the initials shown in the avatar.
 *
 * @param {object|null} user
 * @returns {string}
 */
export function initialsFor(user) {
  const name = user?.full_name?.trim();

  if (!name) {
    return "FD";
  }

  const parts = name.split(/\s+/).filter(Boolean);

  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }

  return (
    parts[0][0] + parts[parts.length - 1][0]
  ).toUpperCase();
}

/**
 * Report whether a user supervises more than one district.
 *
 * True for a Provincial Forestry Officer, whose province
 * contains several districts, and for an Administrator,
 * whose remit is national.
 *
 * False for a District Forestry Officer: comparing one
 * district against itself tells them nothing, and comparing
 * it against others is what requirement FR-04 forbids.
 *
 * This decides what the interface OFFERS. The server
 * decides what it returns, and refuses the request for a
 * district officer regardless.
 *
 * @param {object|null} user
 * @returns {boolean}
 */
export function supervisesMultipleDistricts(user) {
  return (
    user?.role === ROLES.ADMIN ||
    user?.role === ROLES.PROVINCIAL_OFFICER
  );
}

/**
 * Report whether an account can act but has nowhere to act.
 *
 * An officer with no district or province assigned will see
 * empty lists everywhere, because the server refuses every
 * record rather than defaulting to national access. Saying
 * so plainly avoids it being mistaken for "no deforestation
 * has been detected".
 *
 * @param {object|null} user
 * @returns {boolean}
 */
export function isAwaitingJurisdiction(user) {
  if (!user || isAdministrator(user)) {
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
