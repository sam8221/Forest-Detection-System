/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Register Forest Area
 *
 * Purpose:
 *     Provides the interface for registering a new monitored
 *     forest area in the ForestWatch Zambia system.
 *
 * Responsibilities:
 *     - Load active Copperbelt districts from the API.
 *     - Collect forest area information.
 *     - Validate registration data before submission.
 *     - Submit forest area data to the backend.
 *     - Display validation and server errors.
 *     - Confirm successful registration.
 *     - Return the user to the Forest Areas module.
 *
 * Author:
 *     Samuel Bikiloni
 *
 * Project:
 *     Web-Based Deforestation Detection and Alert System
 *     Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Version:
 *     1.1.0
 * ===========================================================
 */

import React, {
  useEffect,
  useState,
} from "react";

const API_URL = "http://127.0.0.1:8000";

export default function RegisterForestArea({
  onBack,
  onRegistered,
}) {
  // ---------------------------------------------------------
  // District state
  // ---------------------------------------------------------

  const [districts, setDistricts] =
    useState([]);

  const [districtsLoading, setDistrictsLoading] =
    useState(true);

  const [districtError, setDistrictError] =
    useState("");

  // ---------------------------------------------------------
  // Form submission state
  // ---------------------------------------------------------

  const [submitting, setSubmitting] =
    useState(false);

  const [successMessage, setSuccessMessage] =
    useState("");

  const [errorMessage, setErrorMessage] =
    useState("");

  // ---------------------------------------------------------
  // Registration form state
  // ---------------------------------------------------------

  const [formData, setFormData] =
    useState({
      forest_code: "",
      name: "",
      district_id: "",
      area_hectares: "",
      protected_status:
        "COMMUNITY_FOREST",
      monitoring_frequency:
        "MONTHLY",
      priority_level:
        "MEDIUM",
      description: "",
      geometry: "",
    });

  // ---------------------------------------------------------
  // Authentication
  // ---------------------------------------------------------

  /**
   * Builds the authorization headers required by
   * protected ForestWatch API endpoints.
   */
  const getAuthHeaders = () => {
    const token =
      localStorage.getItem(
        "access_token"
      ) ||
      localStorage.getItem(
        "token"
      );

    return {
      Accept:
        "application/json",
      "Content-Type":
        "application/json",
      ...(token
        ? {
            Authorization:
              `Bearer ${token}`,
          }
        : {}),
    };
  };

  // ---------------------------------------------------------
  // District loading
  // ---------------------------------------------------------

  /**
   * Retrieves active districts from the backend.
   *
   * District information is loaded from the database
   * rather than being hardcoded in the frontend.
   */
  const fetchDistricts = async () => {
    try {
      setDistrictsLoading(true);
      setDistrictError("");

      const response =
        await fetch(
          `${API_URL}/api/v1/districts`,
          {
            method: "GET",
            headers:
              getAuthHeaders(),
          }
        );

      if (!response.ok) {
        throw new Error(
          `Unable to load districts. ` +
          `Server returned ${response.status}.`
        );
      }

      const data =
        await response.json();

      setDistricts(
        Array.isArray(data)
          ? data
          : []
      );
    } catch (error) {
      console.error(
        "District Loading Error:",
        error
      );

      setDistrictError(
        error instanceof Error
          ? error.message
          : "Failed to load districts."
      );
    } finally {
      setDistrictsLoading(
        false
      );
    }
  };

  /**
   * Load districts when the registration
   * page is initialized.
   */
  useEffect(() => {
    fetchDistricts();
  }, []);

  // ---------------------------------------------------------
  // Form helpers
  // ---------------------------------------------------------

  /**
   * Updates an individual registration field.
   */
  const handleChange = (
    event
  ) => {
    const {
      name,
      value,
    } = event.target;

    setFormData(
      (previous) => ({
        ...previous,
        [name]: value,
      })
    );

    setSuccessMessage("");
    setErrorMessage("");
  };

  /**
   * Resets the registration form to its
   * default configuration.
   */
  const resetForm = () => {
    setFormData({
      forest_code: "",
      name: "",
      district_id: "",
      area_hectares: "",
      protected_status:
        "COMMUNITY_FOREST",
      monitoring_frequency:
        "MONTHLY",
      priority_level:
        "MEDIUM",
      description: "",
      geometry: "",
    });
  };

  // ---------------------------------------------------------
  // WKT validation
  // ---------------------------------------------------------

  /**
   * Performs basic validation of a WKT polygon.
   *
   * This validation prevents obviously malformed values
   * from being submitted. The backend remains responsible
   * for authoritative PostGIS geometry validation.
   */
  const validateWktPolygon = (
    value
  ) => {
    const wkt =
      value.trim();

    const polygonPattern =
      /^POLYGON\s*\(\(\s*[-+]?\d*\.?\d+\s+[-+]?\d*\.?\d+(?:\s*,\s*[-+]?\d*\.?\d+?\s+[-+]?\d*\.?\d+?)+\s*\)\)$/i;

    if (!polygonPattern.test(wkt)) {
      return false;
    }

    const coordinateText =
      wkt
        .replace(
          /^POLYGON\s*\(\(/i,
          ""
        )
        .replace(
          /\)\)$/,
          ""
        );

    const coordinates =
      coordinateText
        .split(",")
        .map(
          (coordinate) =>
            coordinate
              .trim()
              .split(/\s+/)
              .map(Number)
        );

    if (
      coordinates.length <
      4
    ) {
      return false;
    }

    const first =
      coordinates[0];

    const last =
      coordinates[
        coordinates.length - 1
      ];

    if (
      first.length !== 2 ||
      last.length !== 2
    ) {
      return false;
    }

    return (
      first[0] === last[0] &&
      first[1] === last[1]
    );
  };

  // ---------------------------------------------------------
  // Form validation
  // ---------------------------------------------------------

  /**
   * Validates registration fields before sending
   * the request to the backend.
   */
  const validateForm = () => {
    const forestCode =
      formData.forest_code.trim();

    const name =
      formData.name.trim();

    const description =
      formData.description.trim();

    const geometry =
      formData.geometry.trim();

    if (!forestCode) {
      return "Please enter a forest code.";
    }

    if (
      forestCode.length <
      3
    ) {
      return (
        "Forest code must contain at least 3 characters."
      );
    }

    if (!name) {
      return "Please enter the forest area name.";
    }

    if (
      name.length <
      3
    ) {
      return (
        "Forest area name must contain at least 3 characters."
      );
    }

    if (!formData.district_id) {
      return "Please select a district.";
    }

    const area =
      Number(
        formData.area_hectares
      );

    if (
      !Number.isFinite(area) ||
      area <= 0
    ) {
      return (
        "Area in hectares must be greater than zero."
      );
    }

    if (
      !geometry
    ) {
      return (
        "Please provide the forest boundary as WKT."
      );
    }

    if (
      !validateWktPolygon(
        geometry
      )
    ) {
      return (
        "Please enter a valid closed WKT POLYGON."
      );
    }

    if (
      description.length >
      1000
    ) {
      return (
        "Description cannot exceed 1,000 characters."
      );
    }

    return null;
  };

  // ---------------------------------------------------------
  // Registration submission
  // ---------------------------------------------------------

  /**
   * Submits a validated forest area to the
   * ForestWatch REST API.
   */
  const handleSubmit = async (
    event
  ) => {
    event.preventDefault();

    setSuccessMessage("");
    setErrorMessage("");

    const validationError =
      validateForm();

    if (validationError) {
      setErrorMessage(
        validationError
      );
      return;
    }

    try {
      setSubmitting(true);

      const payload = {
        forest_code:
          formData.forest_code.trim(),

        name:
          formData.name.trim(),

        district_id:
          Number(
            formData.district_id
          ),

        geometry:
          formData.geometry.trim(),

        protected_status:
          formData.protected_status,

        monitoring_frequency:
          formData.monitoring_frequency,

        priority_level:
          formData.priority_level,

        area_hectares:
          Number(
            formData.area_hectares
          ),

        description:
          formData.description.trim() ||
          null,
      };

      const response =
        await fetch(
          `${API_URL}/api/v1/forest-areas`,
          {
            method: "POST",
            headers:
              getAuthHeaders(),
            body:
              JSON.stringify(
                payload
              ),
          }
        );

      const responseData =
        await response
          .json()
          .catch(
            () => null
          );

      if (!response.ok) {
        const detail =
          responseData?.detail ||
          "Unable to register the forest area.";

        const message =
          Array.isArray(
            detail
          )
            ? detail
                .map(
                  (item) =>
                    item.msg ||
                    "Invalid field."
                )
                .join(", ")
            : String(detail);

        throw new Error(
          message
        );
      }

      setSuccessMessage(
        "Forest area registered successfully."
      );

      resetForm();

      /*
       * Give the user a short confirmation before
       * returning to the Forest Areas module.
       */
      setTimeout(() => {
        if (
          typeof onRegistered ===
          "function"
        ) {
          onRegistered(
            responseData
          );
        }
      }, 800);
    } catch (error) {
      console.error(
        "Forest Area Registration Error:",
        error
      );

      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to register the forest area."
      );
    } finally {
      setSubmitting(false);
    }
  };

  // ---------------------------------------------------------
  // Render
  // ---------------------------------------------------------

  return (
    <div className="forest-page register-forest-page">

      {/* Page header and navigation controls. */}
      <div className="page-header">

        <div>

          <div className="eyebrow">
            FOREST MANAGEMENT
          </div>

          <h1>
            Register Forest Area
          </h1>

          <p>
            Add a new monitored forest area
            to ForestWatch Zambia.
          </p>

        </div>

        <div className="page-header-actions">

          <button
            type="button"
            className="refresh-button"
            onClick={onBack}
            disabled={submitting}
          >
            ← Back to Forest Areas
          </button>

        </div>

      </div>

      {/* Registration success notification. */}
      {successMessage && (
        <div className="message-card success-card">

          <div className="success-icon">
            ✓
          </div>

          <div>

            <h3>
              Registration Successful
            </h3>

            <p>
              {successMessage}
            </p>

          </div>

        </div>
      )}

      {/* Registration error notification. */}
      {errorMessage && (
        <div className="error-card">

          <div className="error-icon">
            !
          </div>

          <div>

            <h3>
              Registration Failed
            </h3>

            <p>
              {errorMessage}
            </p>

          </div>

        </div>
      )}

      {/* Main registration form. */}
      <div className="settings-card register-forest-card">

        <div className="section-heading">

          <div>

            <h2>
              Forest Area Information
            </h2>

            <p>
              Enter the details of the forest
              area you want to monitor.
            </p>

          </div>

        </div>

        <form
          onSubmit={
            handleSubmit
          }
        >

          {/* Forest identification fields. */}
          <div className="register-form-grid">

            <div className="settings-field">

              <label htmlFor="forest_code">
                Forest Code
              </label>

              <input
                id="forest_code"
                name="forest_code"
                type="text"
                value={
                  formData.forest_code
                }
                onChange={
                  handleChange
                }
                placeholder="e.g. FW-CB-005"
                maxLength={30}
                required
              />

              <small>
                Enter a unique ForestWatch
                identification code.
              </small>

            </div>

            <div className="settings-field">

              <label htmlFor="name">
                Forest Area Name
              </label>

              <input
                id="name"
                name="name"
                type="text"
                value={
                  formData.name
                }
                onChange={
                  handleChange
                }
                placeholder="e.g. Kitwe Community Forest"
                maxLength={200}
                required
              />

            </div>

          </div>

          {/* Location and area fields. */}
          <div className="register-form-grid">

            <div className="settings-field">

              <label htmlFor="district_id">
                District
              </label>

              <select
                id="district_id"
                name="district_id"
                value={
                  formData.district_id
                }
                onChange={
                  handleChange
                }
                disabled={
                  districtsLoading
                }
                required
              >

                <option value="">
                  {districtsLoading
                    ? "Loading districts..."
                    : "Select district"}
                </option>

                {districts.map(
                  (district) => (
                    <option
                      key={
                        district.id
                      }
                      value={
                        district.id
                      }
                    >
                      {
                        district.name
                      }{" "}
                      (
                      {
                        district.code
                      }
                      )
                    </option>
                  )
                )}

              </select>

              {districtError && (
                <small className="field-error">
                  {districtError}
                </small>
              )}

            </div>

            <div className="settings-field">

              <label htmlFor="area_hectares">
                Area (Hectares)
              </label>

              <input
                id="area_hectares"
                name="area_hectares"
                type="number"
                min="0.01"
                step="0.01"
                value={
                  formData.area_hectares
                }
                onChange={
                  handleChange
                }
                placeholder="e.g. 100"
                required
              />

            </div>

          </div>

          {/* Forest protection and monitoring configuration. */}
          <div className="register-form-grid register-form-grid-three">

            <div className="settings-field">

              <label htmlFor="protected_status">
                Protection Status
              </label>

              <select
                id="protected_status"
                name="protected_status"
                value={
                  formData.protected_status
                }
                onChange={
                  handleChange
                }
              >

                <option value="PROTECTED_FOREST">
                  Protected Forest
                </option>

                <option value="NATIONAL_PARK">
                  National Park
                </option>

                <option value="GAME_MANAGEMENT_AREA">
                  Game Management Area
                </option>

                <option value="COMMUNITY_FOREST">
                  Community Forest
                </option>

                <option value="PRIVATE_FOREST">
                  Private Forest
                </option>

              </select>

            </div>

            <div className="settings-field">

              <label htmlFor="monitoring_frequency">
                Monitoring Frequency
              </label>

              <select
                id="monitoring_frequency"
                name="monitoring_frequency"
                value={
                  formData.monitoring_frequency
                }
                onChange={
                  handleChange
                }
              >

                <option value="DAILY">
                  Daily
                </option>

                <option value="EVERY_2_DAYS">
                  Every 2 Days
                </option>

                <option value="WEEKLY">
                  Weekly
                </option>

                <option value="MONTHLY">
                  Monthly
                </option>

              </select>

            </div>

            <div className="settings-field">

              <label htmlFor="priority_level">
                Priority Level
              </label>

              <select
                id="priority_level"
                name="priority_level"
                value={
                  formData.priority_level
                }
                onChange={
                  handleChange
                }
              >

                <option value="LOW">
                  Low
                </option>

                <option value="MEDIUM">
                  Medium
                </option>

                <option value="HIGH">
                  High
                </option>

                <option value="CRITICAL">
                  Critical
                </option>

              </select>

            </div>

          </div>

          {/* Forest area description. */}
          <div className="settings-field">

            <label htmlFor="description">
              Description
            </label>

            <textarea
              id="description"
              name="description"
              value={
                formData.description
              }
              onChange={
                handleChange
              }
              placeholder="Provide a short description of the forest area..."
              rows={4}
              maxLength={1000}
            />

            <small>
              Optional. Maximum 1,000
              characters.
            </small>

          </div>

          {/* Forest boundary definition. */}
          <div className="settings-field">

            <label htmlFor="geometry">
              Forest Boundary (WKT)
            </label>

            <textarea
              id="geometry"
              name="geometry"
              value={
                formData.geometry
              }
              onChange={
                handleChange
              }
              placeholder={
                "POLYGON ((28.2 -12.8, 28.21 -12.8, " +
                "28.21 -12.81, 28.2 -12.81, 28.2 -12.8))"
              }
              rows={5}
              required
            />

            <small>
              Enter a closed WKT POLYGON
              using WGS84 coordinates
              (SRID 4326).
            </small>

          </div>

          {/* Registration controls. */}
          <div className="settings-actions">

            <button
              type="button"
              className="refresh-button"
              onClick={onBack}
              disabled={submitting}
            >
              Cancel
            </button>

            <button
              type="submit"
              className="register-button"
              disabled={
                submitting ||
                districtsLoading
              }
            >
              {submitting
                ? "Registering..."
                : "Register Forest Area"}
            </button>

          </div>

        </form>

      </div>

    </div>
  );
}