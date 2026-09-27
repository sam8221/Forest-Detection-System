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

    return Promise.reject(error);
  }
);

export default api;
