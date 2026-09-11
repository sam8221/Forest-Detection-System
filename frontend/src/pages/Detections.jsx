import React, { useEffect, useState } from "react";
import api from "../services/api";

export default function Detections() {
  const [detections, setDetections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedDetection, setSelectedDetection] = useState(null);
  const [verificationNotes, setVerificationNotes] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState("");

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
  // STATUS STYLE
  // =========================================================

  const getStatusStyle = (status) => {
    const value = String(status || "").toLowerCase();

    if (value === "verified") {
      return {
        backgroundColor: "#DCFCE7",
        color: "#15803D",
        border: "1px solid #86EFAC",
      };
    }

    if (value === "pending") {
      return {
        backgroundColor: "#FEF3C7",
        color: "#B45309",
        border: "1px solid #FCD34D",
      };
    }

    if (value === "rejected") {
      return {
        backgroundColor: "#FEE2E2",
        color: "#B91C1C",
        border: "1px solid #FCA5A5",
      };
    }

    return {
      backgroundColor: "#F1F5F9",
      color: "#475569",
      border: "1px solid #CBD5E1",
    };
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
  // VERIFY / REJECT
  // =========================================================

  const updateDetectionStatus = async (newStatus) => {
    if (!selectedDetection) return;

    try {
      setActionLoading(true);
      setActionError("");

      await api.put(
        `/detections/${selectedDetection.id}/verify`,
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
                          style={{
                            ...getStatusStyle(
                              detection.status
                            ),
                            display: "inline-flex",
                            alignItems: "center",
                            justifyContent: "center",
                            minWidth: "95px",
                            padding: "7px 14px",
                            borderRadius: "999px",
                            fontSize: "12px",
                            fontWeight: "700",
                            letterSpacing: "0.3px",
                            textTransform: "uppercase",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {formatStatus(
                            detection.status
                          )}
                        </span>

                      </td>

                      <td>

                        <button
                          type="button"
                          onClick={() =>
                            openDetection(detection)
                          }
                          style={{
                            border: "none",
                            background: "#E8F5E9",
                            color: "#15803D",
                            padding: "8px 14px",
                            borderRadius: "8px",
                            cursor: "pointer",
                            fontWeight: "700",
                            fontSize: "13px",
                          }}
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
          style={{
            position: "fixed",
            inset: 0,
            backgroundColor:
              "rgba(15, 23, 42, 0.55)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
            padding: "20px",
          }}
          onClick={closeDetection}
        >

          <div
            style={{
              width: "100%",
              maxWidth: "650px",
              maxHeight: "90vh",
              overflowY: "auto",
              background: "#FFFFFF",
              borderRadius: "16px",
              padding: "28px",
              boxShadow:
                "0 20px 60px rgba(0,0,0,0.25)",
            }}
            onClick={(event) =>
              event.stopPropagation()
            }
          >

            {/* HEADER */}

            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                marginBottom: "24px",
              }}
            >

              <div>

                <h2
                  style={{
                    margin: 0,
                    fontSize: "24px",
                    color: "#14532D",
                  }}
                >
                  Detection #{selectedDetection.id}
                </h2>

                <p
                  style={{
                    marginTop: "6px",
                    color: "#64748B",
                  }}
                >
                  Detection review and verification
                </p>

              </div>

              <button
                type="button"
                onClick={closeDetection}
                disabled={actionLoading}
                style={{
                  border: "none",
                  background: "#F1F5F9",
                  width: "36px",
                  height: "36px",
                  borderRadius: "50%",
                  cursor: "pointer",
                  fontSize: "20px",
                }}
              >
                ×
              </button>

            </div>

            {/* STATUS */}

            <div style={{ marginBottom: "20px" }}>

              <span
                style={{
                  ...getStatusStyle(
                    selectedDetection.status
                  ),
                  display: "inline-flex",
                  padding: "8px 16px",
                  borderRadius: "999px",
                  fontSize: "12px",
                  fontWeight: "700",
                }}
              >
                {formatStatus(
                  selectedDetection.status
                )}
              </span>

            </div>

            {/* DETAILS */}

            <div
              style={{
                display: "grid",
                gridTemplateColumns:
                  "repeat(2, minmax(0, 1fr))",
                gap: "16px",
                marginBottom: "24px",
              }}
            >

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

            <div style={{ marginBottom: "20px" }}>

              <label
                htmlFor="verification-notes"
                style={{
                  display: "block",
                  fontWeight: "700",
                  marginBottom: "8px",
                  color: "#334155",
                }}
              >
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
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  padding: "12px",
                  border: "1px solid #CBD5E1",
                  borderRadius: "8px",
                  resize: "vertical",
                  fontFamily: "inherit",
                  fontSize: "14px",
                }}
              />

            </div>

            {/* ERROR */}

            {actionError && (
              <div
                style={{
                  background: "#FEF2F2",
                  color: "#B91C1C",
                  border:
                    "1px solid #FCA5A5",
                  borderRadius: "8px",
                  padding: "12px",
                  marginBottom: "18px",
                  fontSize: "14px",
                }}
              >
                {actionError}
              </div>
            )}

            {/* BUTTONS */}

            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: "10px",
                flexWrap: "wrap",
              }}
            >

              <button
                type="button"
                onClick={closeDetection}
                disabled={actionLoading}
                style={{
                  padding: "11px 18px",
                  borderRadius: "8px",
                  border:
                    "1px solid #CBD5E1",
                  background: "#FFFFFF",
                  color: "#475569",
                  cursor: actionLoading
                    ? "not-allowed"
                    : "pointer",
                  fontWeight: "700",
                }}
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
                    style={{
                      padding: "11px 18px",
                      borderRadius: "8px",
                      border:
                        "1px solid #FCA5A5",
                      background: "#FEE2E2",
                      color: "#B91C1C",
                      cursor: actionLoading
                        ? "not-allowed"
                        : "pointer",
                      fontWeight: "700",
                    }}
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
                    style={{
                      padding: "11px 18px",
                      borderRadius: "8px",
                      border:
                        "1px solid #86EFAC",
                      background: "#DCFCE7",
                      color: "#15803D",
                      cursor: actionLoading
                        ? "not-allowed"
                        : "pointer",
                      fontWeight: "700",
                    }}
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
    <div
      style={{
        background: "#F8FAFC",
        border: "1px solid #E2E8F0",
        borderRadius: "10px",
        padding: "14px",
      }}
    >

      <div
        style={{
          fontSize: "12px",
          color: "#64748B",
          marginBottom: "5px",
          fontWeight: "700",
        }}
      >
        {label}
      </div>

      <div
        style={{
          fontSize: "15px",
          color: "#1E293B",
          fontWeight: "700",
          wordBreak: "break-word",
        }}
      >
        {value}
      </div>

    </div>
  );
}