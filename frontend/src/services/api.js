/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: API Client
 *
 * Purpose:
 *   Sends authenticated requests to the ForestWatch API.
 *
 * Responsibilities:
 *   - Attach the access token to every request.
 *   - Detect an expired or rejected session.
 *   - Notify the application when a session ends.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import axios from "axios";

import { API_V1 } from "../config";

const api = axios.create({
  baseURL: API_V1,
  headers: {
    "Content-Type": "application/json",
  },
});

// ---------------------------------------------------------
// Session-expiry subscribers
//
// The API client cannot navigate on its own, so it reports
// an ended session and lets the application decide what to
// show.
// ---------------------------------------------------------

const sessionExpiredHandlers = new Set();

/**
 * Register a callback for when the session ends.
 *
 * @param {Function} handler
 * @returns {Function} unsubscribe
 */
export function onSessionExpired(handler) {
  sessionExpiredHandlers.add(handler);

  return () => sessionExpiredHandlers.delete(handler);
}

/**
 * Report an ended session to every subscriber.
 *
 * The response interceptor below calls this for requests
 * made through this client. Pages that call fetch() directly
 * -- the satellite download status and acquisition requests
 * do, because they need per-request abort signals -- must
 * call it themselves, otherwise an expired token surfaces as
 * a bare "Could not validate credentials." message and the
 * officer is left on a page that can no longer load anything.
 */
export function notifySessionExpired() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("token");

  sessionExpiredHandlers.forEach((handler) => {
    try {
      handler();
    } catch {
      // A failing subscriber must not stop the others
      // from being told the session ended.
    }
  });
}

/**
 * Report an ended session seen by a fetch() caller.
 *
 * The response interceptor below covers everything sent
 * through this client, but several pages call fetch()
 * directly and never reach it. Without this, an expired
 * token on one of those pages surfaces as the server's own
 * sentence about credentials, on a page that can no longer
 * load anything, and the officer is given nothing to act
 * on.
 *
 * Call it with the response, before checking response.ok.
 * It leaves anything other than 401 alone, so a 403 still
 * reaches the page as a refusal rather than signing the
 * officer out of a session that is perfectly valid.
 *
 * The body is read from a clone, so the caller can still
 * read the response itself afterwards.
 *
 * @param {Response} response
 * @returns {Promise<void>} resolves unless the session ended
 * @throws {Error} when the session has ended
 */
export async function assertSessionAlive(response) {
  if (!response || response.status !== 401) {
    return;
  }

  let detail = "";

  try {
    const body = await response.clone().json();

    detail =
      typeof body?.detail === "string" ? body.detail : "";
  } catch {
    // A 401 without a readable body is still a 401.
  }

  notifySessionExpired();

  throw new Error(
    detail ||
      "Your session has expired. Please sign in again."
  );
}

// ---------------------------------------------------------
// Attach JWT token automatically
// ---------------------------------------------------------

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("access_token");

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// ---------------------------------------------------------
// Handle an ended session in one place
//
// Tokens expire while the interface is open, and every
// request after that returns 401. Handling it here means a
// page does not have to check for it before trusting a
// response, and an expired session cannot be mistaken for
// an empty result.
//
// 403 is deliberately NOT treated the same way. It means
// the officer is signed in correctly but asked for
// something outside their jurisdiction, which is a refusal
// to show the record, not a reason to sign them out.
// ---------------------------------------------------------

api.interceptors.response.use(
  (response) => response,

  (error) => {
    const status = error?.response?.status;

    const isLoginAttempt = error?.config?.url?.includes(
      "/auth/login"
    );

    if (status === 401 && !isLoginAttempt) {
      notifySessionExpired();
    }

    return Promise.reject(error);
  }
);

export default api;
