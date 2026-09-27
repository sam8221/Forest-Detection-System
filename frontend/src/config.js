/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Frontend Configuration
 *
 * Purpose:
 *   Supplies the addresses the interface depends on.
 *
 * Responsibilities:
 *   - Resolve the API address for the current deployment.
 *   - Provide the imagery endpoints derived from it.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Note:
 *   The API address is defined once, here, and read from
 *   the environment rather than written into the pages that
 *   call it. Vite substitutes variables prefixed with VITE_
 *   at build time, so a deployment sets VITE_API_URL and no
 *   source file changes. An address hardcoded per page
 *   would tie the interface to the machine running the
 *   server.
 * ===========================================================
 */

/**
 * Base address of the ForestWatch API, with no trailing
 * slash.
 *
 * Resolution order:
 *
 *   1. VITE_API_URL, set for the deployment.
 *   2. The address the interface itself was served from,
 *      which is correct whenever the API is behind the same
 *      host or reverse proxy.
 *   3. The local development server.
 */
function resolveApiUrl() {
  const configured = import.meta.env?.VITE_API_URL;

  if (configured) {
    return String(configured).replace(/\/+$/, "");
  }

  // Served from a real host rather than a development
  // server: assume the API sits behind the same origin.
  if (
    typeof window !== "undefined" &&
    window.location &&
    !["localhost", "127.0.0.1"].includes(
      window.location.hostname
    )
  ) {
    return window.location.origin;
  }

  return "http://127.0.0.1:8000";
}

export const API_URL = resolveApiUrl();

/** Versioned API root, for example http://host/api/v1 */
export const API_V1 = `${API_URL}/api/v1`;

/** Sentinel-2 imagery proxy. */
export const SENTINEL_WMS_URL = `${API_V1}/sentinel/wms`;
