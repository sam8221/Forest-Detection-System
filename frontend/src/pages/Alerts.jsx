import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Bell,
  CheckCircle,
  Clock,
  RefreshCw,
  Eye,
  Check,
} from "lucide-react";

const API_URL = "http://127.0.0.1:8000";

export default function Alerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [actionLoading, setActionLoading] = useState(null);
  const [actionError, setActionError] = useState("");

  // =========================================================
  // TOKEN
  // =========================================================

  const getToken = () => {
    return (
      localStorage.getItem("access_token") ||
      localStorage.getItem("token")
    );
  };

  // =========================================================
  // FETCH ALERTS
  // =========================================================

  const fetchAlerts = async () => {
    try {
      setLoading(true);
      setError("");

      const token = getToken();

      if (!token) {
        throw new Error(
          "Authentication token not found. Please log in again."
        );
      }

      const response = await fetch(
        `${API_URL}/api/v1/alerts`,
        {
          method: "GET",
          headers: {
            Accept: "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error(
            "Your session has expired. Please log in again."
          );
        }

        throw new Error(
          `Unable to load alerts. Server returned ${response.status}.`
        );
      }

      const data = await response.json();

      setAlerts(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Alerts Error:", err);

      setError(
        err.message || "Failed to load alert records."
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAlerts();
  }, []);

  // =========================================================
  // ALERT ACTION
  // =========================================================

  const performAlertAction = async (alertId, action) => {
    try {
      setActionLoading(`${action}-${alertId}`);
      setActionError("");

      const token = getToken();

      if (!token) {
        throw new Error(
          "Authentication token not found. Please log in again."
        );
      }

      let endpoint = "";

      if (action === "read") {
        endpoint = `/api/v1/alerts/${alertId}/read`;
      }

      if (action === "resolve") {
        endpoint = `/api/v1/alerts/${alertId}/resolve`;
      }

      const response = await fetch(
        `${API_URL}${endpoint}`,
        {
          method: "PUT",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) {
        let message =
          `Unable to update alert. Server returned ${response.status}.`;

        try {
          const errorData = await response.json();

          if (errorData?.detail) {
            message = errorData.detail;
          }
        } catch {
          // Keep default message.
        }

        if (response.status === 403) {
          message =
            "You do not have permission to resolve this alert.";
        }

        if (response.status === 401) {
          message =
            "Your session has expired. Please log in again.";
        }

        throw new Error(message);
      }

      await fetchAlerts();
    } catch (err) {
      console.error(
        `Alert ${action} Error:`,
        err
      );

      setActionError(
        err.message ||
          "Unable to update the alert."
      );
    } finally {
      setActionLoading(null);
    }
  };

  // =========================================================
  // PRIORITY STYLE
  // =========================================================

  const getPriorityStyle = (priority) => {
    const value = String(priority || "").toLowerCase();

    if (value === "critical") {
      return {
        backgroundColor: "#FEE2E2",
        color: "#B91C1C",
        border: "1px solid #FCA5A5",
      };
    }

    if (value === "high") {
      return {
        backgroundColor: "#FFEDD5",
        color: "#C2410C",
        border: "1px solid #FDBA74",
      };
    }

    if (value === "medium") {
      return {
        backgroundColor: "#FEF3C7",
        color: "#B45309",
        border: "1px solid #FCD34D",
      };
    }

    if (value === "low") {
      return {
        backgroundColor: "#DCFCE7",
        color: "#15803D",
        border: "1px solid #86EFAC",
      };
    }

    return {
      backgroundColor: "#F1F5F9",
      color: "#475569",
      border: "1px solid #CBD5E1",
    };
  };

  // =========================================================
  // STATUS STYLE
  // =========================================================

  const getStatusStyle = (status) => {
    const value = String(status || "").toLowerCase();

    if (value === "pending") {
      return {
        backgroundColor: "#FEF3C7",
        color: "#B45309",
        border: "1px solid #FCD34D",
      };
    }

    if (value === "sent") {
      return {
        backgroundColor: "#DCFCE7",
        color: "#15803D",
        border: "1px solid #86EFAC",
      };
    }

    if (value === "read") {
      return {
        backgroundColor: "#DBEAFE",
        color: "#1D4ED8",
        border: "1px solid #93C5FD",
      };
    }

    if (value === "failed") {
      return {
        backgroundColor: "#FEE2E2",
        color: "#B91C1C",
        border: "1px solid #FCA5A5",
      };
    }

    if (value === "resolved") {
      return {
        backgroundColor: "#E0E7FF",
        color: "#4338CA",
        border: "1px solid #A5B4FC",
      };
    }

    return {
      backgroundColor: "#F1F5F9",
      color: "#475569",
      border: "1px solid #CBD5E1",
    };
  };

  // =========================================================
  // DATE
  // =========================================================

  const formatDate = (date) => {
    if (!date) {
      return "—";
    }

    try {
      return new Date(date).toLocaleString(
        "en-ZM",
        {
          dateStyle: "medium",
          timeStyle: "short",
        }
      );
    } catch {
      return date;
    }
  };

  // =========================================================
  // FORMAT ALERT MESSAGE
  // Bold labels, normal values
  // =========================================================

  const renderAlertMessage = (message) => {
    if (!message) {
      return "No alert message available.";
    }

    const lines = String(message).split("\n");

    return lines.map((line, index) => {
      const separatorIndex = line.indexOf(":");

      if (separatorIndex === -1) {
        return (
          <React.Fragment key={index}>
            {line}

            {index < lines.length - 1 && (
              <br />
            )}
          </React.Fragment>
        );
      }

      const label = line
        .substring(0, separatorIndex)
        .trim();

      const value = line
        .substring(separatorIndex + 1)
        .trim();

      return (
        <React.Fragment key={index}>
          <strong
            style={{
              color: "#073B2A",
              fontWeight: "700",
            }}
          >
            {label}:
          </strong>{" "}
          {value}

          {index < lines.length - 1 && (
            <br />
          )}
        </React.Fragment>
      );
    });
  };

  // =========================================================
  // COUNTS
  // =========================================================

  const pendingCount = alerts.filter(
    (alert) =>
      String(alert.status || "").toLowerCase() ===
      "pending"
  ).length;

  const criticalCount = alerts.filter(
    (alert) =>
      String(alert.priority || "").toLowerCase() ===
      "critical"
  ).length;

  const resolvedCount = alerts.filter(
    (alert) =>
      alert.is_resolved === true ||
      String(alert.status || "").toLowerCase() ===
        "resolved"
  ).length;

  // =========================================================
  // RENDER
  // =========================================================

  return (
    <div className="forest-page">

      {/* =====================================================
          HEADER
      ====================================================== */}

      <div className="page-header">

        <div>
          <h1>Alerts</h1>

          <p>
            Review and manage deforestation alerts
            generated by the ForestWatch Zambia
            monitoring system.
          </p>
        </div>

        <button
          className="refresh-button"
          onClick={fetchAlerts}
          disabled={loading}
        >
          <RefreshCw
            size={17}
            className={loading ? "spin" : ""}
          />

          {loading
            ? "Loading..."
            : "Refresh"}
        </button>

      </div>

      {/* =====================================================
          ACTION ERROR
      ====================================================== */}

      {actionError && (
        <div
          style={{
            background: "#FEF2F2",
            border: "1px solid #FCA5A5",
            color: "#B91C1C",
            borderRadius: "10px",
            padding: "12px 16px",
            marginBottom: "20px",
          }}
        >
          {actionError}
        </div>
      )}

      {/* =====================================================
          SUMMARY CARDS
      ====================================================== */}

      {!loading && !error && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns:
              "repeat(4, minmax(0, 1fr))",
            gap: "18px",
            marginBottom: "28px",
          }}
        >
          <SummaryCard
            icon={<Bell size={23} />}
            title="Total Alerts"
            value={alerts.length}
            background="#E8F5EC"
            color="#16834D"
          />

          <SummaryCard
            icon={<Clock size={23} />}
            title="Pending Alerts"
            value={pendingCount}
            background="#FEF3C7"
            color="#B45309"
          />

          <SummaryCard
            icon={<AlertTriangle size={23} />}
            title="Critical Alerts"
            value={criticalCount}
            background="#FEE2E2"
            color="#B91C1C"
          />

          <SummaryCard
            icon={<CheckCircle size={23} />}
            title="Resolved Alerts"
            value={resolvedCount}
            background="#E0E7FF"
            color="#4338CA"
          />
        </div>
      )}

      {/* =====================================================
          LOADING
      ====================================================== */}

      {loading && (
        <div className="message-card">

          <div className="loading-spinner">
            ⟳
          </div>

          <h3>
            Loading Alerts
          </h3>

          <p>
            Retrieving alert records from the
            ForestWatch Zambia server...
          </p>

        </div>
      )}

      {/* =====================================================
          ERROR
      ====================================================== */}

      {!loading && error && (
        <div className="error-card">

          <div className="error-icon">
            ⚠
          </div>

          <div>

            <h3>
              Unable to Load Alerts
            </h3>

            <p>
              {error}
            </p>

            <button
              className="retry-button"
              onClick={fetchAlerts}
            >
              Try Again
            </button>

          </div>

        </div>
      )}

      {/* =====================================================
          ALERT LIST
      ====================================================== */}

      {!loading && !error && (
        <div
          style={{
            background: "#FFFFFF",
            border:
              "1px solid #E2E8E5",
            borderRadius: "20px",
            overflow: "hidden",
          }}
        >

          {/* LIST HEADER */}

          <div
            style={{
              padding: "24px 28px",
              borderBottom:
                "1px solid #E2E8E5",
              display: "flex",
              justifyContent:
                "space-between",
              alignItems: "center",
            }}
          >

            <div>

              <h2
                style={{
                  margin: 0,
                  color: "#073B2A",
                }}
              >
                Deforestation Alerts
              </h2>

              <p
                style={{
                  margin:
                    "6px 0 0",
                  color: "#718096",
                }}
              >
                Alerts generated from
                detected forest changes.
              </p>

            </div>

            <strong
              style={{
                color: "#16834D",
                background: "#E8F5EC",
                padding:
                  "9px 15px",
                borderRadius: "12px",
              }}
            >
              {alerts.length} Alerts
            </strong>

          </div>

          {/* =================================================
              ALERTS
          ================================================== */}

          {alerts.length > 0 ? (

            <div>

              {alerts.map((alert) => {

                const status =
                  String(
                    alert.status || ""
                  ).toLowerCase();

                const isResolved =
                  alert.is_resolved === true ||
                  status === "resolved";

                const isRead =
                  status === "read";

                const readLoading =
                  actionLoading ===
                  `read-${alert.id}`;

                const resolveLoading =
                  actionLoading ===
                  `resolve-${alert.id}`;

                return (

                  <div
                    key={alert.id}
                    style={{
                      padding:
                        "22px 28px",
                      borderBottom:
                        "1px solid #EDF2EF",
                      display: "flex",
                      gap: "18px",
                      alignItems:
                        "flex-start",
                    }}
                  >

                    {/* ICON */}

                    <div
                      style={{
                        width: "46px",
                        height: "46px",
                        minWidth: "46px",
                        borderRadius:
                          "14px",
                        background:
                          alert.priority ===
                            "CRITICAL" ||
                          alert.priority ===
                            "HIGH"
                            ? "#FFF1EC"
                            : "#FEF8E8",
                        color:
                          alert.priority ===
                          "CRITICAL"
                            ? "#B91C1C"
                            : "#C2410C",
                        display: "flex",
                        alignItems:
                          "center",
                        justifyContent:
                          "center",
                      }}
                    >
                      <AlertTriangle
                        size={22}
                      />
                    </div>

                    {/* INFORMATION */}

                    <div
                      style={{
                        flex: 1,
                        minWidth: 0,
                      }}
                    >

                      {/* TITLE + PRIORITY */}

                      <div
                        style={{
                          display: "flex",
                          justifyContent:
                            "space-between",
                          gap: "20px",
                          alignItems:
                            "flex-start",
                        }}
                      >

                        <div>

                          <h3
                            style={{
                              margin: 0,
                              color:
                                "#073B2A",
                              fontSize:
                                "17px",
                            }}
                          >
                            {alert.title}
                          </h3>

                          {/* =================================================
                              FORMATTED ALERT MESSAGE
                          ================================================== */}

                          <div
                            style={{
                              margin:
                                "8px 0 0",
                              color:
                                "#64748B",
                              lineHeight:
                                "1.8",
                              fontSize:
                                "15px",
                            }}
                          >
                            {renderAlertMessage(
                              alert.message
                            )}
                          </div>

                        </div>

                        <span
                          style={{
                            ...getPriorityStyle(
                              alert.priority
                            ),
                            padding:
                              "6px 12px",
                            borderRadius:
                              "999px",
                            fontSize:
                              "11px",
                            fontWeight:
                              "700",
                            whiteSpace:
                              "nowrap",
                          }}
                        >
                          {alert.priority}
                        </span>

                      </div>

                      {/* INFORMATION */}

                      <div
                        style={{
                          display: "flex",
                          flexWrap:
                            "wrap",
                          gap: "16px",
                          alignItems:
                            "center",
                          marginTop:
                            "16px",
                        }}
                      >

                        <span
                          style={{
                            color:
                              "#718096",
                            fontSize:
                              "13px",
                          }}
                        >
                          <strong
                            style={{
                              color:
                                "#073B2A",
                            }}
                          >
                            Alert #{alert.id}
                          </strong>
                        </span>

                        <span
                          style={{
                            color:
                              "#718096",
                            fontSize:
                              "13px",
                          }}
                        >
                          <strong
                            style={{
                              color:
                                "#073B2A",
                            }}
                          >
                            Detection #
                            {alert.detection_id}
                          </strong>
                        </span>

                        <span
                          style={{
                            color:
                              "#718096",
                            fontSize:
                              "13px",
                          }}
                        >
                          {alert.alert_type ||
                            "Deforestation"}
                        </span>

                        <span
                          style={{
                            color:
                              "#718096",
                            fontSize:
                              "13px",
                          }}
                        >
                          {formatDate(
                            alert.created_at
                          )}
                        </span>

                        {/* STATUS */}

                        <span
                          style={{
                            ...getStatusStyle(
                              alert.status
                            ),
                            padding:
                              "6px 12px",
                            borderRadius:
                              "999px",
                            fontSize:
                              "11px",
                            fontWeight:
                              "700",
                          }}
                        >
                          {String(
                            alert.status ||
                              "UNKNOWN"
                          ).toUpperCase()}
                        </span>

                        {/* RESOLVED */}

                        {isResolved && (
                          <span
                            style={{
                              display:
                                "inline-flex",
                              alignItems:
                                "center",
                              gap: "5px",
                              color:
                                "#15803D",
                              fontSize:
                                "12px",
                              fontWeight:
                                "700",
                            }}
                          >
                            <CheckCircle
                              size={15}
                            />

                            Resolved
                          </span>
                        )}

                      </div>

                      {/* =================================================
                          ACTION BUTTONS
                      ================================================== */}

                      <div
                        style={{
                          display: "flex",
                          gap: "10px",
                          marginTop:
                            "18px",
                          flexWrap:
                            "wrap",
                        }}
                      >

                        {/* MARK AS READ */}

                        {!isRead &&
                          !isResolved && (

                            <button
                              type="button"
                              onClick={() =>
                                performAlertAction(
                                  alert.id,
                                  "read"
                                )
                              }
                              disabled={
                                actionLoading !==
                                null
                              }
                              style={{
                                display:
                                  "inline-flex",
                                alignItems:
                                  "center",
                                gap: "7px",
                                padding:
                                  "9px 14px",
                                borderRadius:
                                  "8px",
                                border:
                                  "1px solid #93C5FD",
                                background:
                                  "#EFF6FF",
                                color:
                                  "#1D4ED8",
                                cursor:
                                  actionLoading
                                    ? "not-allowed"
                                    : "pointer",
                                fontWeight:
                                  "700",
                                fontSize:
                                  "13px",
                              }}
                            >
                              <Eye
                                size={15}
                              />

                              {readLoading
                                ? "Marking..."
                                : "Mark as Read"}
                            </button>
                          )}

                        {/* ALREADY READ */}

                        {isRead &&
                          !isResolved && (

                            <span
                              style={{
                                display:
                                  "inline-flex",
                                alignItems:
                                  "center",
                                gap: "6px",
                                padding:
                                  "9px 14px",
                                borderRadius:
                                  "8px",
                                background:
                                  "#F1F5F9",
                                color:
                                  "#64748B",
                                fontSize:
                                  "13px",
                                fontWeight:
                                  "700",
                              }}
                            >
                              <Check
                                size={15}
                              />

                              Already Read
                            </span>
                          )}

                        {/* RESOLVE */}

                        {!isResolved && (

                          <button
                            type="button"
                            onClick={() =>
                              performAlertAction(
                                alert.id,
                                "resolve"
                              )
                            }
                            disabled={
                              actionLoading !==
                              null
                            }
                            style={{
                              display:
                                "inline-flex",
                              alignItems:
                                "center",
                              gap: "7px",
                              padding:
                                "9px 14px",
                              borderRadius:
                                "8px",
                              border:
                                "1px solid #86EFAC",
                              background:
                                "#F0FDF4",
                              color:
                                "#15803D",
                              cursor:
                                actionLoading
                                  ? "not-allowed"
                                  : "pointer",
                              fontWeight:
                                "700",
                              fontSize:
                                "13px",
                            }}
                          >
                            <CheckCircle
                              size={15}
                            />

                            {resolveLoading
                              ? "Resolving..."
                              : "Resolve Alert"}
                          </button>
                        )}

                      </div>

                    </div>

                  </div>
                );
              })}

            </div>

          ) : (

            <div
              style={{
                padding:
                  "60px 20px",
                textAlign:
                  "center",
              }}
            >

              <Bell
                size={40}
                color="#94A3B8"
              />

              <h3>
                No Alerts Found
              </h3>

              <p
                style={{
                  color:
                    "#718096",
                }}
              >
                There are currently no
                alert records available.
              </p>

            </div>
          )}

        </div>
      )}

    </div>
  );
}

// =========================================================
// SUMMARY CARD
// =========================================================

function SummaryCard({
  icon,
  title,
  value,
  background,
  color,
}) {
  return (
    <div
      style={{
        background: "#FFFFFF",
        border:
          "1px solid #E2E8E5",
        borderRadius: "18px",
        padding: "22px",
        display: "flex",
        alignItems: "center",
        gap: "16px",
      }}
    >

      <div
        style={{
          width: "48px",
          height: "48px",
          borderRadius: "14px",
          background,
          color,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {icon}
      </div>

      <div>

        <div
          style={{
            color: "#718096",
            fontSize: "14px",
          }}
        >
          {title}
        </div>

        <strong
          style={{
            fontSize: "25px",
            color: "#073B2A",
          }}
        >
          {value}
        </strong>

      </div>

    </div>
  );
}