/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Alerts Page
 *
 * Purpose:
 *     Lists the deforestation alerts raised by the monitoring
 *     system and lets an officer work through them.
 *
 * Responsibilities:
 *     - Retrieve alert records for the signed-in officer.
 *     - Summarise them by state and priority.
 *     - Mark an alert as read, or resolve it.
 *
 * Note on styling:
 *     Layout and colour live in the stylesheet, under the
 *     "ALERTS PAGE" block in src/index.css, rather than as
 *     inline style objects on the elements. This lets the
 *     page inherit the shared corner radius and elevation
 *     scales, and lets the summary row reflow on a narrow
 *     screen, which an inline width cannot do.
 *
 * Author:
 *     Samuel Bikiloni
 *
 * Project:
 *     Web-Based Deforestation Detection and Alert System
 *     Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Version:
 *     1.0.0
 * ===========================================================
 */

import React, { useEffect, useState } from "react";

import { API_URL as CONFIG_API_URL } from "../config";
import {
  AlertTriangle,
  Bell,
  CheckCircle,
  Clock,
  RefreshCw,
  Eye,
  Check,
} from "lucide-react";

const API_URL = CONFIG_API_URL;

// =========================================================
// BADGE VARIANTS
//
// Priority and status are both rendered as a pill, and both
// arrive from the server as an uppercase string. The tint is
// selected by appending the lowercased value to the badge
// class, so a value the interface does not recognise falls
// back to a neutral grey rather than rendering unstyled.
//
// Declared once, outside the component, because the set does
// not change between renders.
// =========================================================

const PRIORITY_VARIANTS = [
  "critical",
  "high",
  "medium",
  "low",
];

const STATUS_VARIANTS = [
  "pending",
  "sent",
  "read",
  "failed",
  "resolved",
];

/**
 * Return the badge class for a server-supplied value.
 *
 * @param {string} value
 *     Priority or status as received from the API.
 * @param {string[]} allowed
 *     Variants the stylesheet defines a tint for.
 * @returns {string}
 *     Two class names: the shared badge shape and its tint.
 */
function badgeClass(value, allowed) {
  const normalised = String(value || "").toLowerCase();

  const variant = allowed.includes(normalised)
    ? normalised
    : "unknown";

  return `alert-badge alert-badge--${variant}`;
}

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
  //
  // The alert body arrives as plain text, one "Label: value"
  // pair per line. Emphasising the label lets an officer scan
  // down the left edge of the block instead of reading every
  // line in full.
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
          <strong>{label}:</strong>{" "}
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

          Announced politely: the message appears after the
          officer has acted, so a screen reader should finish
          the current phrase before reading it.
      ====================================================== */}

      {actionError && (
        <div
          className="alerts-action-error"
          role="status"
          aria-live="polite"
        >
          {actionError}
        </div>
      )}

      {/* =====================================================
          SUMMARY CARDS
      ====================================================== */}

      {!loading && !error && (
        <div className="alerts-summary">

          <SummaryCard
            icon={<Bell size={23} />}
            title="Total Alerts"
            value={alerts.length}
            variant="total"
          />

          <SummaryCard
            icon={<Clock size={23} />}
            title="Pending Alerts"
            value={pendingCount}
            variant="pending"
          />

          <SummaryCard
            icon={<AlertTriangle size={23} />}
            title="Critical Alerts"
            value={criticalCount}
            variant="critical"
          />

          <SummaryCard
            icon={<CheckCircle size={23} />}
            title="Resolved Alerts"
            value={resolvedCount}
            variant="resolved"
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
        <div className="alerts-panel">

          {/* LIST HEADER */}

          <div className="alerts-panel-header">

            <div>

              <h2>
                Deforestation Alerts
              </h2>

              <p>
                Alerts generated from
                detected forest changes.
              </p>

            </div>

            <strong className="alerts-panel-count">
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

                const priority =
                  String(
                    alert.priority || ""
                  ).toUpperCase();

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

                // Critical and high share the stronger icon
                // background; only critical takes the red
                // foreground with it.

                const iconClasses = [
                  "alert-entry-icon",
                  priority === "CRITICAL" ||
                  priority === "HIGH"
                    ? "is-severe"
                    : "",
                  priority === "CRITICAL"
                    ? "is-critical"
                    : "",
                ]
                  .filter(Boolean)
                  .join(" ");

                return (

                  <div
                    key={alert.id}
                    className="alert-entry"
                  >

                    {/* ICON */}

                    <div
                      className={iconClasses}
                      aria-hidden="true"
                    >
                      <AlertTriangle
                        size={22}
                      />
                    </div>

                    {/* INFORMATION */}

                    <div className="alert-entry-body">

                      {/* TITLE + PRIORITY */}

                      <div className="alert-entry-head">

                        <div>

                          <h3>
                            {alert.title}
                          </h3>

                          <div className="alert-entry-message">
                            {renderAlertMessage(
                              alert.message
                            )}
                          </div>

                        </div>

                        <span
                          className={badgeClass(
                            alert.priority,
                            PRIORITY_VARIANTS
                          )}
                        >
                          {alert.priority}
                        </span>

                      </div>

                      {/* INFORMATION */}

                      <div className="alert-entry-meta">

                        <span>
                          <strong>
                            Alert #{alert.id}
                          </strong>
                        </span>

                        <span>
                          <strong>
                            Detection #
                            {alert.detection_id}
                          </strong>
                        </span>

                        <span>
                          {alert.alert_type ||
                            "Deforestation"}
                        </span>

                        <span>
                          {formatDate(
                            alert.created_at
                          )}
                        </span>

                        {/* STATUS */}

                        <span
                          className={badgeClass(
                            alert.status,
                            STATUS_VARIANTS
                          )}
                        >
                          {String(
                            alert.status ||
                              "UNKNOWN"
                          ).toUpperCase()}
                        </span>

                        {/* RESOLVED */}

                        {isResolved && (
                          <span className="alert-entry-resolved">
                            <CheckCircle
                              size={15}
                            />

                            Resolved
                          </span>
                        )}

                      </div>

                      {/* =================================================
                          ACTION BUTTONS

                          Both controls are disabled while any
                          action on the page is in flight, so
                          two requests cannot be issued against
                          the same record at once.
                      ================================================== */}

                      <div className="alert-entry-actions">

                        {/* MARK AS READ */}

                        {!isRead &&
                          !isResolved && (

                            <button
                              type="button"
                              className="alert-action alert-action--read"
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

                            <span className="alert-read-flag">
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
                            className="alert-action alert-action--resolve"
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

            <div className="alerts-empty">

              <Bell
                size={40}
                color="#94A3B8"
                aria-hidden="true"
              />

              <h3>
                No Alerts Found
              </h3>

              <p>
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
//
// One figure from the alert list. The tint is chosen by a
// modifier class rather than passed in as a colour, so the
// four cards cannot drift apart from the palette.
// =========================================================

function SummaryCard({
  icon,
  title,
  value,
  variant,
}) {
  return (
    <div className="alerts-summary-card">

      <div
        className={`alerts-summary-icon is-${variant}`}
        aria-hidden="true"
      >
        {icon}
      </div>

      <div>

        <div className="alerts-summary-label">
          {title}
        </div>

        <strong className="alerts-summary-value">
          {value}
        </strong>

      </div>

    </div>
  );
}
