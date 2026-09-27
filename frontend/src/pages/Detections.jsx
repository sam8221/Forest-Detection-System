/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Detections Page
 *
 * Purpose:
 *   Lists the areas of vegetation loss the system has found,
 *   and lets an officer confirm or dismiss each one.
 *
 * Responsibilities:
 *   - List detections within the officer's jurisdiction.
 *   - Show the evidence behind a detection.
 *   - Record a verdict of VERIFIED or REJECTED, with notes.
 *
 * How it works:
 *
 *   What a detection is
 *   -------------------
 *   A patch of ground where NDVI fell between the baseline
 *   and comparison windows by more than the configured
 *   threshold, and which covers at least half a hectare.
 *   That floor is 50 Sentinel-2 pixels at 10 m resolution,
 *   and it is taken from the area threshold in the Forests
 *   Act No. 4 of 2015, which defines a forest as land with
 *   "a tree canopy cover of more than ten percent and area
 *   of more than zero point five hectares". It also
 *   suppresses isolated noise pixels.
 *
 *   Only the area criterion is applied. The system does not
 *   measure canopy cover or tree height, so a detection is
 *   not a finding that a forest as legally defined has been
 *   cleared. That determination is the officer's, which is
 *   what the review on this screen records.
 *
 *   The system detects; it does not conclude. Every detection
 *   is a candidate awaiting human judgement, which is why the
 *   status begins as PENDING.
 *
 *   Why the readings are shown, not just the verdict
 *   ------------------------------------------------
 *   The review dialog shows ndvi_before, ndvi_after, the
 *   affected area and a confidence score, rather than only
 *   the conclusion. An officer deciding whether to send
 *   someone into the field needs to see the evidence, and
 *   storing the underlying readings also lets a detection be
 *   re-evaluated later if a threshold changes, without
 *   reprocessing the imagery.
 *
 *   The verdict is the evidence base for Chapter Five
 *   -------------------------------------------------
 *   Verification is what turns detections into a measurable
 *   result: confirmed detections are true positives and
 *   rejected ones are false positives, and the accuracy
 *   evaluation is built from that. The verdict is written to
 *   the server's audit trail, so the review can be traced to
 *   an officer and a time.
 *
 *   Verify and Reject appear only while a detection is
 *   PENDING. A decided detection is not re-decided here.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import React, { useEffect, useState } from "react";
import { Download } from "lucide-react";

import api from "../services/api";
import { downloadDetectionReport } from "../services/reports";

// =========================================================
// STATUS PILL
//
// A detection is PENDING until an officer reviews it, then
// VERIFIED or REJECTED. The tint for each is defined in the
// stylesheet under "DETECTIONS PAGE AND REVIEW DIALOG";
// this only selects between them.
//
// A status the interface does not recognise falls back to a
// neutral pill rather than rendering unstyled, so a value
// added to the API later is still legible here.
// =========================================================

const DETECTION_STATUSES = [
  "verified",
  "pending",
  "rejected",
];

// =========================================================
// VERDICT ENDPOINTS
//
// The server records a verdict through a separate endpoint
// for each outcome: PUT /detections/{id}/verify and
// PUT /detections/{id}/reject. The endpoint, not the request
// body, decides what is recorded, so this mapping is what
// guarantees that Reject rejects.
// =========================================================

const VERDICT_ENDPOINTS = {
  VERIFIED: "verify",
  REJECTED: "reject",
};

/**
 * Return the pill class for a detection status.
 *
 * @param {string} status
 *     Status as received from the API.
 * @returns {string}
 *     The shared pill class and its tint modifier.
 */
function statusClass(status) {
  const value = String(status || "").toLowerCase();

  const variant = DETECTION_STATUSES.includes(value)
    ? value
    : "unknown";

  return `detection-status detection-status--${variant}`;
}

export default function Detections() {
  const [detections, setDetections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedDetection, setSelectedDetection] = useState(null);
  const [verificationNotes, setVerificationNotes] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState("");

  // Tracked separately from actionLoading: downloading a
  // report neither changes the record nor should it disable
  // the verify and reject controls beside it.
  const [downloading, setDownloading] = useState(false);

  // =========================================================
  // DOWNLOAD THE EVIDENCE SHEET
  // =========================================================

  /**
   * Download this detection as a PDF.
   *
   * The report is rendered on the server from the database
   * of record, not from what this screen is showing, so the
   * document an officer takes into the field carries the
   * authoritative figures.
   *
   * @returns {Promise<void>}
   */
  const handleDownloadReport = async () => {
    if (!selectedDetection) {
      return;
    }

    setDownloading(true);
    setActionError("");

    try {
      await downloadDetectionReport(selectedDetection.id);
    } catch (err) {
      // The service raises messages written to be shown.
      setActionError(err.message);
    } finally {
      setDownloading(false);
    }
  };

  // =========================================================
  // FETCH DETECTIONS
  // =========================================================

  const fetchDetections = async () => {
    try {
      setLoading(true);
      setError("");

      const response = await api.get("/detections");

      const data = response.data;

      setDetections(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Detections Error:", err);

      if (err.response?.status === 401) {
        setError("Your session has expired. Please log in again.");
      } else {
        setError(
          err.response?.data?.detail ||
            err.message ||
            "Failed to load detection records."
        );
      }
    } finally {
      setLoading(false);
    }
  };

  // =========================================================
  // INITIAL LOAD
  // =========================================================

  useEffect(() => {
    fetchDetections();
  }, []);

  // =========================================================
  // FORMAT STATUS
  // =========================================================

  const formatStatus = (status) => {
    if (!status) return "UNKNOWN";

    return String(status)
      .replaceAll("_", " ")
      .toUpperCase();
  };

  // =========================================================
  // OPEN DETECTION
  // =========================================================

  const openDetection = (detection) => {
    setSelectedDetection(detection);
    setVerificationNotes(
      detection.verification_notes || ""
    );
    setActionError("");
  };

  // =========================================================
  // CLOSE DETECTION
  // =========================================================

  const closeDetection = () => {
    if (actionLoading) return;

    setSelectedDetection(null);
    setVerificationNotes("");
    setActionError("");
  };

  // =========================================================
  // DISMISS ON ESCAPE
  //
  // The dialog could already be dismissed by clicking the
  // dimmed area behind it, but not from the keyboard. An
  // officer working through a list of detections moves
  // between them without reaching for the mouse, so Escape
  // is bound to the same close path.
  //
  // The listener is attached only while a detection is open
  // and removed when it closes, so the page does not keep a
  // key handler alive for a dialog that is not on screen.
  // =========================================================

  useEffect(() => {
    if (!selectedDetection) {
      return undefined;
    }

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        closeDetection();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener(
        "keydown",
        handleKeyDown
      );
    };
  }, [selectedDetection, actionLoading]);

  // =========================================================
  // VERIFY / REJECT
  // =========================================================

  /**
   * Record the officer's verdict on the open detection.
   *
   * Each verdict has its own endpoint, and the endpoint is what
   * decides the outcome. The server ignores the `status` field
   * in the body for this purpose; the field is still sent only
   * because the request schema requires it.
   *
   * The endpoint must therefore match the verdict exactly.
   * Sending a rejection to /verify would mark the detection
   * VERIFIED and trigger the alert workflow, emailing officers
   * about a detection that had just been judged false, and
   * would record a false positive as a true positive in the
   * data the Chapter Five accuracy evaluation is built from.
   *
   * @param {"VERIFIED"|"REJECTED"} newStatus
   * @returns {Promise<void>}
   */
  const updateDetectionStatus = async (newStatus) => {
    if (!selectedDetection) return;

    const action = VERDICT_ENDPOINTS[newStatus];

    // Refuse rather than guess. Falling back to a default
    // endpoint is exactly how the original bug arose.
    if (!action) {
      setActionError(
        `Unsupported verdict "${newStatus}". The detection ` +
          "was not changed."
      );
      return;
    }

    try {
      setActionLoading(true);
      setActionError("");

      await api.put(
        `/detections/${selectedDetection.id}/${action}`,
        {
          status: newStatus,
          verification_notes:
            verificationNotes.trim() || null,
        }
      );

      setSelectedDetection(null);
      setVerificationNotes("");

      await fetchDetections();
    } catch (err) {
      console.error(
        "Detection Verification Error:",
        err
      );

      setActionError(
        err.response?.data?.detail ||
          err.message ||
          "Unable to update detection status."
      );
    } finally {
      setActionLoading(false);
    }
  };

  // =========================================================
  // RENDER
  // =========================================================

  return (
    <div className="forest-page">

      {/* PAGE HEADER */}

      <div className="page-header">

        <div>
          <h1>Detections</h1>

          <p>
            Review deforestation detections identified
            from satellite imagery across the Copperbelt,
            Zambia.
          </p>
        </div>

        <button
          className="refresh-button"
          onClick={fetchDetections}
          disabled={loading}
        >
          ↻ {loading ? "Loading..." : "Refresh"}
        </button>

      </div>

      {/* LOADING */}

      {loading && (
        <div className="message-card">

          <div className="loading-spinner">
            ⟳
          </div>

          <h3>Loading Detections</h3>

          <p>
            Retrieving deforestation detection records
            from the server...
          </p>

        </div>
      )}

      {/* ERROR */}

      {!loading && error && (
        <div className="error-card">

          <div className="error-icon">
            ⚠
          </div>

          <div>

            <h3>
              Unable to Load Detections
            </h3>

            <p>{error}</p>

            <button
              className="retry-button"
              onClick={fetchDetections}
            >
              Try Again
            </button>

          </div>

        </div>
      )}

      {/* DATA */}

      {!loading && !error && (
        <>

          <div className="section-heading">

            <div>

              <h2>
                Deforestation Detections
              </h2>

              <p>
                Detection records generated by the
                forest monitoring system.
              </p>

            </div>

            <div className="forest-count">
              {detections.length} Detections
            </div>

          </div>

          {/* TABLE */}

          {detections.length > 0 && (
            <div className="detection-table-wrapper">

              <table className="detection-table">

                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Forest Area</th>
                    <th>Affected Area</th>
                    <th>Confidence</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>

                <tbody>

                  {detections.map((detection) => (

                    <tr key={detection.id}>

                      <td>
                        <strong>
                          #{detection.id}
                        </strong>
                      </td>

                      <td>
                        <strong>
                          {detection.forest_name ||
                            detection.forest_area_name ||
                            detection.forest?.name ||
                            `Forest Area #${
                              detection.forest_area_id ||
                              detection.forest_id ||
                              "—"
                            }`}
                        </strong>
                      </td>

                      <td>
                        {Number(
                          detection.detected_area_hectares ??
                            detection.affected_area_hectares ??
                            detection.affected_area ??
                            0
                        ).toFixed(2)}{" "}
                        ha
                      </td>

                      <td>
                        {detection.confidence_score != null
                          ? `${Number(
                              detection.confidence_score
                            ).toFixed(2)}%`
                          : detection.confidence != null
                          ? `${Number(
                              detection.confidence
                            ).toFixed(2)}%`
                          : "—"}
                      </td>

                      <td>

                        <span
                          className={statusClass(
                            detection.status
                          )}
                        >
                          {formatStatus(
                            detection.status
                          )}
                        </span>

                      </td>

                      <td>

                        <button
                          type="button"
                          className="detection-view-button"
                          onClick={() =>
                            openDetection(detection)
                          }
                        >
                          View Details
                        </button>

                      </td>

                    </tr>

                  ))}

                </tbody>

              </table>

            </div>
          )}

          {/* NO DATA */}

          {detections.length === 0 && (
            <div className="message-card">

              <div className="loading-spinner">
                🌿
              </div>

              <h3>
                No Detections Found
              </h3>

              <p>
                There are currently no deforestation
                detection records available.
              </p>

            </div>
          )}

        </>
      )}

      {/* =====================================================
          DETECTION MODAL
      ====================================================== */}

      {selectedDetection && (
        <div
          className="detection-overlay"
          onClick={closeDetection}
        >

          <div
            className="detection-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="detection-dialog-title"
            onClick={(event) =>
              event.stopPropagation()
            }
          >

            {/* HEADER */}

            <div className="detection-dialog-header">

              <div>

                <h2 id="detection-dialog-title">
                  Detection #{selectedDetection.id}
                </h2>

                <p>
                  Detection review and verification
                </p>

              </div>

              <button
                type="button"
                aria-label="Close detection review"
                onClick={closeDetection}
                disabled={actionLoading}
                className="detection-dialog-close"
              >
                ×
              </button>

            </div>

            {/* STATUS */}

            <div className="detection-dialog-status">

              <span
                className={statusClass(
                  selectedDetection.status
                )}
              >
                {formatStatus(
                  selectedDetection.status
                )}
              </span>

            </div>

            {/* DETAILS */}

            <div className="detection-detail-grid">

              <DetailItem
                label="Forest Area"
                value={
                  selectedDetection.forest_name ||
                  selectedDetection.forest_area_name ||
                  selectedDetection.forest?.name ||
                  `Forest Area #${
                    selectedDetection.forest_area_id ||
                    selectedDetection.forest_id ||
                    "—"
                  }`
                }
              />

              <DetailItem
                label="Detection ID"
                value={`#${selectedDetection.id}`}
              />

              <DetailItem
                label="Affected Area"
                value={`${Number(
                  selectedDetection.detected_area_hectares ??
                    selectedDetection.affected_area_hectares ??
                    selectedDetection.affected_area ??
                    0
                ).toFixed(2)} ha`}
              />

              <DetailItem
                label="Confidence Score"
                value={
                  selectedDetection.confidence_score != null
                    ? `${Number(
                        selectedDetection.confidence_score
                      ).toFixed(2)}%`
                    : "—"
                }
              />

              <DetailItem
                label="Vegetation Loss"
                value={
                  selectedDetection
                    .vegetation_loss_percentage != null
                    ? `${Number(
                        selectedDetection
                          .vegetation_loss_percentage
                      ).toFixed(2)}%`
                    : "—"
                }
              />

              <DetailItem
                label="NDVI Before"
                value={
                  selectedDetection.ndvi_before != null
                    ? Number(
                        selectedDetection.ndvi_before
                      ).toFixed(4)
                    : "—"
                }
              />

              <DetailItem
                label="NDVI After"
                value={
                  selectedDetection.ndvi_after != null
                    ? Number(
                        selectedDetection.ndvi_after
                      ).toFixed(4)
                    : "—"
                }
              />

              <DetailItem
                label="Satellite Image ID"
                value={
                  selectedDetection.satellite_image_id ??
                  "—"
                }
              />

              <DetailItem
                label="Analysis Job ID"
                value={
                  selectedDetection.analysis_job_id ??
                  "—"
                }
              />

            </div>

            {/* NOTES */}

            <div className="detection-notes">

              <label htmlFor="verification-notes">
                Verification Notes
              </label>

              <textarea
                id="verification-notes"
                value={verificationNotes}
                onChange={(event) =>
                  setVerificationNotes(
                    event.target.value
                  )
                }
                placeholder="Enter verification notes..."
                rows={4}
                disabled={actionLoading}
              />

            </div>

            {/* ERROR */}

            {actionError && (
              <div
                className="detection-dialog-error"
                role="status"
                aria-live="polite"
              >
                {actionError}
              </div>
            )}

            {/* BUTTONS */}

            <div className="detection-dialog-actions">

              {/* Kept to the leading edge, away from Verify
                  and Reject. Downloading is not a decision
                  about the detection, and it stays available
                  whatever the status: an officer may need the
                  sheet for a record already reviewed. */}
              <button
                type="button"
                className="detection-button--report"
                onClick={handleDownloadReport}
                disabled={downloading}
              >
                <Download size={15} aria-hidden="true" />

                {downloading
                  ? "Preparing…"
                  : "Download report"}
              </button>

              <button
                type="button"
                className="detection-button--cancel"
                onClick={closeDetection}
                disabled={actionLoading}
              >
                Cancel
              </button>

              {String(
                selectedDetection.status || ""
              ).toUpperCase() === "PENDING" && (
                <>
                  <button
                    type="button"
                    onClick={() =>
                      updateDetectionStatus(
                        "REJECTED"
                      )
                    }
                    disabled={actionLoading}
                    className="detection-button--reject"
                  >
                    {actionLoading
                      ? "Processing..."
                      : "Reject Detection"}
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      updateDetectionStatus(
                        "VERIFIED"
                      )
                    }
                    disabled={actionLoading}
                    className="detection-button--verify"
                  >
                    {actionLoading
                      ? "Processing..."
                      : "Verify Detection"}
                  </button>
                </>
              )}

            </div>

          </div>

        </div>
      )}

    </div>
  );
}


// =========================================================
// DETAIL ITEM
// =========================================================

function DetailItem({ label, value }) {
  return (
    <div className="detection-detail">

      <div className="detection-detail-label">
        {label}
      </div>

      <div className="detection-detail-value">
        {value}
      </div>

    </div>
  );
}