/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Report Download Service
 *
 * Purpose:
 *   Downloads the PDF reports the server generates.
 *
 * Responsibilities:
 *   - Request a report with the officer's token attached.
 *   - Hand the file to the browser as a download.
 *   - Report a refusal in words an officer can act on.
 *
 * How it works:
 *
 *   The report endpoints require authentication, and a plain
 *   link cannot carry an Authorization header: the browser
 *   issues the request itself and attaches nothing. Setting
 *   the token in the URL instead would put it in the browser
 *   history and in any server log the request passes
 *   through.
 *
 *   So the file is fetched like any other API call, with the
 *   token in the header, and the response body is turned
 *   into a blob. A temporary anchor pointing at that blob is
 *   clicked to start the save, then removed and the object
 *   URL revoked, which is what releases the memory the blob
 *   was holding.
 *
 *   The filename comes from the server's Content-Disposition
 *   header when one is present, so the browser and the
 *   server agree on what the file is called and an officer
 *   downloading several reports does not end up with a
 *   folder of files named download.pdf.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import { API_V1 } from "../config";
import { TOKEN_KEY } from "./auth";

/**
 * Read the filename the server asked the browser to use.
 *
 * @param {string|null} header
 *   The Content-Disposition header, if the response had one.
 * @param {string} fallback
 *   Name to use when the header is absent or unparseable.
 * @returns {string}
 */
function filenameFrom(header, fallback) {
  if (!header) {
    return fallback;
  }

  // filename="forestwatch-detection-59.pdf"
  const match = header.match(
    /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i
  );

  return match ? decodeURIComponent(match[1]) : fallback;
}

/**
 * Turn a failed response into a message worth showing.
 *
 * The status codes carry distinct operational meanings here
 * and are deliberately not collapsed into one message: an
 * officer who is out of jurisdiction needs different advice
 * from one whose session has ended.
 *
 * @param {Response} response
 * @returns {Promise<string>}
 */
async function describeFailure(response) {
  if (response.status === 401) {
    return "Your session has expired. Please log in again.";
  }

  if (response.status === 403 || response.status === 404) {
    return (
      "This record is not available to you. It may lie " +
      "outside your assigned jurisdiction."
    );
  }

  // The server sends a readable sentence in `detail` for a
  // validation failure, such as an inverted date range.
  try {
    const body = await response.json();

    if (body?.detail) {
      return String(body.detail);
    }
  } catch {
    // Body was not JSON; fall through to the status.
  }

  return (
    `The report could not be produced. Server returned ` +
    `${response.status}.`
  );
}

/**
 * Fetch a report and save it to the officer's device.
 *
 * @param {string} path
 *   Path beneath the API root, e.g. "/reports/summary".
 * @param {string} fallbackName
 *   Filename to use if the server does not supply one.
 * @returns {Promise<void>}
 *   Resolves once the download has started.
 * @throws {Error}
 *   With a message intended to be shown to the officer:
 *   an expired session, a record outside their
 *   jurisdiction, a validation failure, or the server
 *   being unreachable.
 */
async function downloadReport(path, fallbackName) {
  const token = localStorage.getItem(TOKEN_KEY);

  let response;

  try {
    response = await fetch(`${API_V1}${path}`, {
      method: "GET",
      headers: {
        Accept: "application/pdf",
        ...(token
          ? { Authorization: `Bearer ${token}` }
          : {}),
      },
    });
  } catch {
    throw new Error(
      "The server could not be reached, so the report was " +
        "not produced."
    );
  }

  if (!response.ok) {
    throw new Error(await describeFailure(response));
  }

  const blob = await response.blob();

  const objectUrl = URL.createObjectURL(blob);

  const anchor = document.createElement("a");

  anchor.href = objectUrl;

  anchor.download = filenameFrom(
    response.headers.get("Content-Disposition"),
    fallbackName
  );

  document.body.appendChild(anchor);

  anchor.click();

  // Cleaned up immediately. The browser has already taken
  // its own reference to the blob by this point, so the
  // save completes even though the URL is revoked here.
  anchor.remove();

  URL.revokeObjectURL(objectUrl);
}

/**
 * Download the evidence sheet for one detection.
 *
 * @param {number} detectionId
 * @returns {Promise<void>}
 * @throws {Error} See downloadReport.
 */
export function downloadDetectionReport(detectionId) {
  return downloadReport(
    `/reports/detections/${detectionId}`,
    `forestwatch-detection-${detectionId}.pdf`
  );
}

/**
 * Download a period summary for the officer's jurisdiction.
 *
 * @param {object} [period]
 * @param {string} [period.start] Start date, YYYY-MM-DD.
 * @param {string} [period.end] End date, YYYY-MM-DD.
 * @returns {Promise<void>}
 * @throws {Error} See downloadReport.
 */
export function downloadSummaryReport(period = {}) {
  const query = new URLSearchParams();

  if (period.start) {
    query.set("start", period.start);
  }

  if (period.end) {
    query.set("end", period.end);
  }

  const suffix = query.toString()
    ? `?${query.toString()}`
    : "";

  return downloadReport(
    `/reports/summary${suffix}`,
    "forestwatch-summary.pdf"
  );
}
