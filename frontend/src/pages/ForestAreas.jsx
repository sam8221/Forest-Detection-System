/**
 * =========================================================
 * ForestWatch Zambia
 * ---------------------------------------------------------
 * Module: Forest Areas Page
 *
 * Purpose:
 *     Displays registered forest areas and their monitoring
 *     information.
 *
 * Responsibilities:
 *     - Retrieve forest areas from the backend API.
 *     - Display official district names and codes.
 *     - Present forest monitoring and protection details.
 *     - Handle loading, empty, and error states.
 *     - Support manual data refresh.
 *     - Provide access to forest area registration.
 *     - Provide access to forest area details.
 *
 * Author:
 *     Samuel Bikiloni
 *
 * Project:
 *     Web-Based Deforestation Detection and Alert System
 *     Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Version:
 *     1.2.0
 * =========================================================
 */

import React, {
  useCallback,
  useEffect,
  useState,
} from "react";

const API_URL =
  "http://127.0.0.1:8000";

export default function ForestAreas({
  onRegister,
  onViewDetails,
}) {
  const [forests, setForests] =
    useState([]);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  // =======================================================
  // AUTHENTICATION
  // =======================================================

  const getAccessToken = () => {
    return (
      localStorage.getItem(
        "access_token"
      ) ||
      localStorage.getItem(
        "token"
      )
    );
  };

  // =======================================================
  // FORMAT ENUM VALUES
  // =======================================================

  const formatLabel = (
    value
  ) => {
    if (!value) {
      return "—";
    }

    return String(value)
      .replaceAll(
        "_",
        " "
      )
      .toLowerCase()
      .replace(
        /\b\w/g,
        (character) =>
          character.toUpperCase()
      );
  };

  // =======================================================
  // FORMAT AREA
  // =======================================================

  const formatArea = (
    value
  ) => {
    const area =
      Number(value);

    if (
      !Number.isFinite(area)
    ) {
      return "—";
    }

    return `${area.toLocaleString(
      undefined,
      {
        maximumFractionDigits: 2,
      }
    )} Ha`;
  };

  // =======================================================
  // FETCH FOREST AREAS
  // =======================================================

  const fetchForestAreas =
    useCallback(
      async () => {
        try {
          setLoading(true);
          setError("");

          const token =
            getAccessToken();

          const response =
            await fetch(
              `${API_URL}/api/v1/forest-areas`,
              {
                method: "GET",
                headers: {
                  Accept:
                    "application/json",

                  ...(token
                    ? {
                        Authorization:
                          `Bearer ${token}`,
                      }
                    : {}),
                },
              }
            );

          if (!response.ok) {
            let message =
              `Unable to load forest areas. ` +
              `Server returned ${response.status}.`;

            try {
              const errorData =
                await response.json();

              if (
                errorData?.detail
              ) {
                message =
                  Array.isArray(
                    errorData.detail
                  )
                    ? errorData.detail
                        .map(
                          (item) =>
                            item.msg ||
                            "Invalid request."
                        )
                        .join(
                          ", "
                        )
                    : String(
                        errorData.detail
                      );
              }
            } catch {
              // Keep default error.
            }

            throw new Error(
              message
            );
          }

          const data =
            await response.json();

          setForests(
            Array.isArray(data)
              ? data
              : []
          );
        } catch (err) {
          console.error(
            "Forest Areas Error:",
            err
          );

          setError(
            err instanceof Error
              ? err.message
              : "Failed to load forest areas."
          );
        } finally {
          setLoading(false);
        }
      },
      []
    );

  // =======================================================
  // INITIAL LOAD
  // =======================================================

  useEffect(() => {
    fetchForestAreas();
  }, [
    fetchForestAreas,
  ]);

  // =======================================================
  // OPEN FOREST DETAILS
  // =======================================================

  const handleViewDetails =
    (forestId) => {
      if (
        !forestId
      ) {
        return;
      }

      if (
        typeof onViewDetails ===
        "function"
      ) {
        onViewDetails(
          forestId
        );
      }
    };

  // =======================================================
  // RENDER
  // =======================================================

  return (
    <div className="forest-page">

      {/* =================================================
          PAGE HEADER
          ================================================= */}

      <div className="page-header">

        <div>

          <span className="eyebrow">
            FOREST MONITORING
          </span>

          <h1>
            Forest Areas
          </h1>

          <p>
            Manage and monitor registered
            forest areas across the
            Copperbelt, Zambia.
          </p>

        </div>

        <div className="page-header-actions">

          <button
            type="button"
            className="register-button"
            onClick={onRegister}
          >
            + Register Forest Area
          </button>

          <button
            type="button"
            className="refresh-button"
            onClick={
              fetchForestAreas
            }
            disabled={loading}
          >
            ↻{" "}
            {loading
              ? "Loading..."
              : "Refresh"}
          </button>

        </div>

      </div>

      {/* =================================================
          LOADING
          ================================================= */}

      {loading && (
        <div className="message-card">

          <div className="loading-spinner">
            ⟳
          </div>

          <h3>
            Loading Forest Areas
          </h3>

          <p>
            Retrieving monitored forest
            areas from the ForestWatch
            server.
          </p>

        </div>
      )}

      {/* =================================================
          ERROR
          ================================================= */}

      {!loading &&
        error && (
          <div className="error-card">

            <div className="error-icon">
              ⚠
            </div>

            <div>

              <h3>
                Unable to Load
                Forest Areas
              </h3>

              <p>
                {error}
              </p>

              <button
                type="button"
                className="retry-button"
                onClick={
                  fetchForestAreas
                }
              >
                Try Again
              </button>

            </div>

          </div>
        )}

      {/* =================================================
          FOREST DATA
          ================================================= */}

      {!loading &&
        !error && (
          <>

            {/* SECTION HEADER */}

            <div className="section-heading">

              <div>

                <h2>
                  Monitored Forest Areas
                </h2>

                <p>
                  Forest areas currently
                  registered and monitored
                  by ForestWatch Zambia.
                </p>

              </div>

              <div className="forest-count">

                {forests.length}{" "}

                {forests.length ===
                1
                  ? "Area"
                  : "Areas"}

              </div>

            </div>

            {/* =================================================
                FOREST CARDS
                ================================================= */}

            {forests.length >
              0 && (
              <div className="forest-grid">

                {forests.map(
                  (forest) => {

                    const priority =
                      String(
                        forest.priority_level ||
                          "LOW"
                      ).toLowerCase();

                    return (
                      <article
                        className="forest-card"
                        key={
                          forest.id
                        }
                      >

                        {/* CARD HEADER */}

                        <div className="forest-card-top">

                          <div className="forest-card-icon">
                            🌲
                          </div>

                          <span
                            className={
                              `priority priority-${priority}`
                            }
                          >
                            {formatLabel(
                              forest.priority_level ||
                                "LOW"
                            )}
                          </span>

                        </div>

                        {/* NAME */}

                        <h3>
                          {forest.name ||
                            "Unnamed Forest Area"}
                        </h3>

                        {/* CODE */}

                        <p className="forest-code">
                          {forest.forest_code ||
                            "No forest code"}
                        </p>

                        {/* DETAILS */}

                        <div className="forest-details">

                          {/* AREA */}

                          <div className="detail">

                            <span>
                              Area
                            </span>

                            <strong>
                              {formatArea(
                                forest.area_hectares
                              )}
                            </strong>

                          </div>

                          {/* DISTRICT */}

                          <div className="detail">

                            <span>
                              District
                            </span>

                            <strong>
                              {forest.district_name ||
                                "Unknown District"}
                            </strong>

                            {forest.district_code && (
                              <small>
                                {
                                  forest.district_code
                                }
                              </small>
                            )}

                          </div>

                          {/* MONITORING */}

                          <div className="detail">

                            <span>
                              Monitoring
                            </span>

                            <strong>
                              {formatLabel(
                                forest.monitoring_frequency
                              )}
                            </strong>

                          </div>

                          {/* PROTECTION */}

                          <div className="detail">

                            <span>
                              Protection
                            </span>

                            <strong>
                              {formatLabel(
                                forest.protected_status
                              )}
                            </strong>

                          </div>

                        </div>

                        {/* DESCRIPTION */}

                        <div className="forest-description">

                          {forest.description ||
                            "No description available."}

                        </div>

                        {/* STATUS */}

                        <div className="forest-status">

                          <span
                            className={
                              forest.is_active
                                ? "status-dot active"
                                : "status-dot inactive"
                            }
                          />

                          <span>
                            {forest.is_active
                              ? "Active Monitoring"
                              : "Inactive"}
                          </span>

                        </div>

                        {/* =================================================
                            VIEW DETAILS BUTTON
                            ================================================= */}

                        <button
                          type="button"
                          className="view-details-button"
                          onClick={() =>
                            handleViewDetails(
                              forest.id
                            )
                          }
                        >
                          View Details
                          <span>
                            →
                          </span>
                        </button>

                      </article>
                    );
                  }
                )}

              </div>
            )}

            {/* =================================================
                EMPTY STATE
                ================================================= */}

            {forests.length ===
              0 && (
              <div className="message-card">

                <div className="loading-spinner">
                  🌲
                </div>

                <h3>
                  No Forest Areas Found
                </h3>

                <p>
                  There are currently no
                  forest areas registered
                  in the system.
                </p>

                <button
                  type="button"
                  className="register-button"
                  onClick={
                    onRegister
                  }
                >
                  + Register First
                  Forest Area
                </button>

              </div>
            )}

          </>
        )}

    </div>
  );
}