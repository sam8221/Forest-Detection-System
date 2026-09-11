/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Forest Area Details
 *
 * Purpose:
 *     Displays detailed information about a selected forest
 *     area together with Sentinel-2 satellite imagery and
 *     the registered PostGIS forest boundary.
 *
 * Author:
 *     Samuel Bikiloni
 *
 * Project:
 *     Web-Based Deforestation Detection and Alert System
 *     Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Version:
 *     2.2.0
 * ===========================================================
 */

import React, {
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  LayersControl,
  MapContainer,
  Polygon,
  TileLayer,
  Tooltip,
  useMap,
  WMSTileLayer,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";


/* =========================================================
   API
   ========================================================= */

const API_URL =
  "http://127.0.0.1:8000";


/* =========================================================
   COPERNICUS DATA SPACE
   ========================================================= */

const SENTINEL_INSTANCE_ID =
  "0a0b0bc0-5f64-4a9b-826a-28a79ef8007b";

const SENTINEL_WMS_URL =
  `https://sh.dataspace.copernicus.eu/ogc/wms/${SENTINEL_INSTANCE_ID}`;


/* =========================================================
   WKT POLYGON → LEAFLET POSITIONS
   ========================================================= */

function parseWktPolygon(wkt) {
  if (
    typeof wkt !== "string" ||
    !wkt.trim()
  ) {
    return [];
  }

  const match = wkt
    .trim()
    .match(
      /^POLYGON\s*\(\((.*)\)\)$/i
    );

  if (!match) {
    return [];
  }

  return match[1]
    .split(",")
    .map((pair) => {
      const values = pair
        .trim()
        .split(/\s+/)
        .map(Number);

      if (
        values.length < 2 ||
        !Number.isFinite(values[0]) ||
        !Number.isFinite(values[1])
      ) {
        return null;
      }

      return [
        values[1],
        values[0],
      ];
    })
    .filter(Boolean);
}


/* =========================================================
   MAP VIEWPORT
   ========================================================= */

function MapViewport({
  positions,
}) {
  const map = useMap();

  useEffect(() => {
    if (
      !positions ||
      positions.length === 0
    ) {
      return;
    }

    map.fitBounds(
      positions,
      {
        padding: [
          40,
          40,
        ],
        maxZoom: 15,
      }
    );
  }, [
    map,
    positions,
  ]);

  return null;
}


/* =========================================================
   MAIN COMPONENT
   ========================================================= */

export default function ForestAreaDetails({
  forestId,
  onBack,
}) {
  const [forest, setForest] =
    useState(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const [
    analysisLoading,
    setAnalysisLoading,
  ] = useState(false);

  const [
    analysisMessage,
    setAnalysisMessage,
  ] = useState("");

  const [
    analysisError,
    setAnalysisError,
  ] = useState("");

  const [
    satelliteError,
    setSatelliteError,
  ] = useState(false);


  /* =======================================================
     AUTH HEADERS
     ======================================================= */

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


  /* =======================================================
     FETCH FOREST AREA
     ======================================================= */

  const fetchForestArea =
    async () => {
      if (!forestId) {
        setError(
          "No forest area was selected."
        );

        setLoading(false);

        return;
      }

      try {
        setLoading(true);
        setError("");

        const response =
          await fetch(
            `${API_URL}/api/v1/forest-areas/${forestId}`,
            {
              method: "GET",
              headers:
                getAuthHeaders(),
            }
          );

        if (!response.ok) {
          let message =
            `Unable to load forest area. ` +
            `Server returned ${response.status}.`;

          try {
            const data =
              await response.json();

            if (data?.detail) {
              message =
                Array.isArray(
                  data.detail
                )
                  ? data.detail
                      .map(
                        (item) =>
                          item.msg ||
                          "Invalid request."
                      )
                      .join(
                        ", "
                      )
                  : String(
                      data.detail
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

        setForest(data);

      } catch (err) {
        console.error(
          "Forest Area Details Error:",
          err
        );

        setError(
          err instanceof Error
            ? err.message
            : "Failed to load forest area."
        );

      } finally {
        setLoading(false);
      }
    };


  /* =======================================================
     LOAD FOREST
     ======================================================= */

  useEffect(() => {
    fetchForestArea();
  }, [
    forestId,
  ]);


  /* =======================================================
     PARSE FOREST GEOMETRY
     ======================================================= */

  const polygonPositions =
    useMemo(() => {
      if (!forest?.geometry) {
        return [];
      }

      return parseWktPolygon(
        forest.geometry
      );
    }, [
      forest,
    ]);


  /* =======================================================
     MAP CENTER
     ======================================================= */

  const mapCenter =
    useMemo(() => {
      if (
        polygonPositions.length ===
        0
      ) {
        return [
          -12.8,
          28.2,
        ];
      }

      let latitude = 0;
      let longitude = 0;

      polygonPositions.forEach(
        ([lat, lng]) => {
          latitude += lat;
          longitude += lng;
        }
      );

      return [
        latitude /
          polygonPositions.length,

        longitude /
          polygonPositions.length,
      ];
    }, [
      polygonPositions,
    ]);


  /* =======================================================
     FORMAT ENUM
     ======================================================= */

  const formatEnum =
    (value) => {
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
          (letter) =>
            letter.toUpperCase()
        );
    };


  /* =======================================================
     FORMAT AREA
     ======================================================= */

  const formatArea =
    (value) => {
      const number =
        Number(value);

      if (
        !Number.isFinite(
          number
        )
      ) {
        return "—";
      }

      return `${number.toLocaleString(
        undefined,
        {
          maximumFractionDigits: 2,
        }
      )} Ha`;
    };


  /* =======================================================
     RUN ANALYSIS
     ======================================================= */

  const handleRunAnalysis =
    async () => {
      if (!forest?.id) {
        return;
      }

      try {
        setAnalysisLoading(
          true
        );

        setAnalysisMessage("");
        setAnalysisError("");

        const response =
          await fetch(
            `${API_URL}/api/v1/forest-areas/${forest.id}/run-analysis`,
            {
              method: "POST",
              headers:
                getAuthHeaders(),
            }
          );

        const data =
          await response
            .json()
            .catch(
              () => null
            );

        if (!response.ok) {
          const detail =
            data?.detail ||
            "Unable to start deforestation analysis.";

          throw new Error(
            Array.isArray(detail)
              ? detail
                  .map(
                    (item) =>
                      item.msg ||
                      "Invalid request."
                  )
                  .join(
                    ", "
                  )
              : String(
                  detail
                )
          );
        }

        setAnalysisMessage(
          data?.message ||
            "Deforestation analysis has been started successfully."
        );

      } catch (err) {
        console.error(
          "Analysis Start Error:",
          err
        );

        setAnalysisError(
          err instanceof Error
            ? err.message
            : "Failed to start analysis."
        );

      } finally {
        setAnalysisLoading(
          false
        );
      }
    };


  /* =======================================================
     LOADING SCREEN
     ======================================================= */

  if (loading) {
    return (
      <div className="forest-page">

        <div className="page-header">

          <div>

            <div className="eyebrow">
              FOREST MONITORING
            </div>

            <h1>
              Forest Area Details
            </h1>

            <p>
              Loading forest monitoring
              information...
            </p>

          </div>

        </div>

        <div className="message-card">

          <div className="loading-spinner">
            ⟳
          </div>

          <h3>
            Loading Forest Area
          </h3>

          <p>
            Retrieving forest information
            from the ForestWatch server...
          </p>

        </div>

      </div>
    );
  }


  /* =======================================================
     ERROR SCREEN
     ======================================================= */

  if (error) {
    return (
      <div className="forest-page">

        <div className="page-header">

          <div>

            <div className="eyebrow">
              FOREST MONITORING
            </div>

            <h1>
              Forest Area Details
            </h1>

            <p>
              Unable to retrieve the
              selected forest area.
            </p>

          </div>

        </div>

        <div className="error-card">

          <div className="error-icon">
            !
          </div>

          <div>

            <h3>
              Unable to Load Forest Area
            </h3>

            <p>
              {error}
            </p>

            <div className="details-error-actions">

              <button
                type="button"
                className="refresh-button"
                onClick={onBack}
              >
                ← Back to Forest Areas
              </button>

              <button
                type="button"
                className="retry-button"
                onClick={
                  fetchForestArea
                }
              >
                Try Again
              </button>

            </div>

          </div>

        </div>

      </div>
    );
  }


  /* =======================================================
     MAIN PAGE
     ======================================================= */

  return (
    <div className="forest-page forest-details-page">

      {/* =================================================
          HEADER
          ================================================= */}

      <div className="page-header">

        <div>

          <div className="eyebrow">
            FOREST MONITORING
          </div>

          <h1>
            {forest?.name ||
              "Forest Area"}
          </h1>

          <p>
            Detailed monitoring information,
            Sentinel-2 imagery and geographical
            boundary.
          </p>

        </div>

        <div className="page-header-actions">

          <button
            type="button"
            className="refresh-button"
            onClick={onBack}
          >
            ← Back to Forest Areas
          </button>

        </div>

      </div>


      {/* =================================================
          FOREST IDENTITY
          ================================================= */}

      <div className="forest-details-identity">

        <div>

          <span>
            FOREST CODE
          </span>

          <strong>
            {forest?.forest_code ||
              "—"}
          </strong>

        </div>


        <div>

          <span>
            DISTRICT
          </span>

          <strong>
            {forest?.district_name ||
              "—"}

            {forest?.district_code
              ? ` (${forest.district_code})`
              : ""}
          </strong>

        </div>


        <div>

          <span>
            STATUS
          </span>

          <strong
            className={
              forest?.is_active
                ? "forest-active"
                : "forest-inactive"
            }
          >

            <span className="status-dot" />

            {forest?.is_active
              ? "Active Monitoring"
              : "Inactive"}

          </strong>

        </div>

      </div>


      {/* =================================================
          FOREST INFORMATION
          ================================================= */}

      <div className="forest-detail-grid">

        <div className="forest-detail-card">

          <span>
            Area
          </span>

          <strong>
            {formatArea(
              forest?.area_hectares
            )}
          </strong>

        </div>


        <div className="forest-detail-card">

          <span>
            Protection
          </span>

          <strong>
            {formatEnum(
              forest?.protected_status
            )}
          </strong>

        </div>


        <div className="forest-detail-card">

          <span>
            Monitoring
          </span>

          <strong>
            {formatEnum(
              forest?.monitoring_frequency
            )}
          </strong>

        </div>


        <div className="forest-detail-card">

          <span>
            Priority
          </span>

          <strong
            className={
              `detail-priority priority-${String(
                forest?.priority_level ||
                  "LOW"
              ).toLowerCase()}`
            }
          >
            {formatEnum(
              forest?.priority_level
            )}
          </strong>

        </div>

      </div>


      {/* =================================================
          SENTINEL-2 MAP
          ================================================= */}

      <div className="forest-map-card">

        <div className="forest-map-header">

          <div>

            <div className="eyebrow">
              SATELLITE MONITORING
            </div>

            <h2>
              Sentinel-2 Forest Map
            </h2>

            <p>
              Sentinel-2 satellite imagery
              with the registered forest
              boundary.
            </p>

          </div>


          <div className="map-coordinate-status">

            <span className="status-dot" />

            Sentinel-2

          </div>

        </div>


        {polygonPositions.length >
        0 ? (

          <div className="forest-map-wrapper">

            <MapContainer
              center={
                mapCenter
              }
              zoom={13}
              scrollWheelZoom={
                true
              }
              className="forest-leaflet-map"
            >

              <LayersControl
                position="topright"
              >

                {/* =========================================
                    SENTINEL-2 TRUE COLOR
                    ========================================= */}

                <LayersControl.BaseLayer
                  checked
                  name="🛰 Sentinel-2 True Color"
                >

                  <WMSTileLayer
                    url={
                      SENTINEL_WMS_URL
                    }

                    params={{
                      layers:
                        "1_TRUE_COLOR",

                      styles:
                        "",

                      format:
                        "image/png",

                      transparent:
                        false,

                      version:
                        "1.1.1",

                      maxcc:
                        50,

                      showlogo:
                        false,

                      time:
                        "2026-08-23",
                    }}

                    eventHandlers={{
                      load: () => {
                        setSatelliteError(
                          false
                        );
                      },

                      tileerror: () => {
                        setSatelliteError(
                          true
                        );
                      },
                    }}

                    attribution="Sentinel-2 © Copernicus Data Space Ecosystem"
                  />

                </LayersControl.BaseLayer>


                {/* =========================================
                    OPEN STREET MAP
                    ========================================= */}

                <LayersControl.BaseLayer
                  name="🗺 OpenStreetMap"
                >

                  <TileLayer
                    attribution="&copy; OpenStreetMap contributors"
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />

                </LayersControl.BaseLayer>


                {/* =========================================
                    SENTINEL-2 FALSE COLOR
                    ========================================= */}

                <LayersControl.BaseLayer
                  name="🌳 Sentinel-2 False Color"
                >

                  <WMSTileLayer
                    url={
                      SENTINEL_WMS_URL
                    }

                    params={{
                      layers:
                        "2_FALSE_COLOR",

                      styles:
                        "",

                      format:
                        "image/png",

                      transparent:
                        false,

                      version:
                        "1.1.1",

                      maxcc:
                        50,

                      showlogo:
                        false,

                      time:
                        "2026-08-23",
                    }}

                    attribution="Sentinel-2 © Copernicus Data Space Ecosystem"
                  />

                </LayersControl.BaseLayer>


                {/* =========================================
                    SENTINEL-2 NDVI
                    ========================================= */}

                <LayersControl.BaseLayer
                  name="🌿 Sentinel-2 NDVI"
                >

                  <WMSTileLayer
                    url={
                      SENTINEL_WMS_URL
                    }

                    params={{
                      layers:
                        "3_NDVI",

                      styles:
                        "",

                      format:
                        "image/png",

                      transparent:
                        false,

                      version:
                        "1.1.1",

                      maxcc:
                        50,

                      showlogo:
                        false,

                      time:
                        "2026-08-23",
                    }}

                    attribution="NDVI © Copernicus Data Space Ecosystem"
                  />

                </LayersControl.BaseLayer>

              </LayersControl>


              {/* =========================================
                  FOREST BOUNDARY
                  ========================================= */}

              <Polygon
                positions={
                  polygonPositions
                }

                pathOptions={{
                  fillOpacity: 0.20,
                  weight: 4,
                }}
              >

                <Tooltip
                  sticky
                >

                  <strong>
                    {forest?.name}
                  </strong>

                  <br />

                  Code:{" "}
                  {
                    forest?.forest_code
                  }

                  <br />

                  District:{" "}
                  {
                    forest?.district_name ||
                    "—"
                  }

                  <br />

                  Area:{" "}
                  {formatArea(
                    forest?.area_hectares
                  )}

                </Tooltip>

              </Polygon>


              {/* =========================================
                  AUTOMATIC ZOOM
                  ========================================= */}

              <MapViewport
                positions={
                  polygonPositions
                }
              />

            </MapContainer>


            {/* =========================================
                SENTINEL ERROR
                ========================================= */}

            {satelliteError && (
              <div className="satellite-map-warning">

                ⚠ Sentinel-2 imagery could not
                be loaded. Use the map layer
                selector to switch to OpenStreetMap.

              </div>
            )}

          </div>

        ) : (

          <div className="map-empty-state">

            <div>
              🗺️
            </div>

            <h3>
              Boundary Not Available
            </h3>

            <p>
              No valid polygon geometry
              was returned for this forest
              area.
            </p>

          </div>

        )}

      </div>


      {/* =================================================
          DESCRIPTION
          ================================================= */}

      <div className="forest-description-card">

        <div>

          <div className="eyebrow">
            AREA DESCRIPTION
          </div>

          <h2>
            About This Forest Area
          </h2>

        </div>

        <p>
          {forest?.description ||
            "No description has been provided for this forest area."}
        </p>

      </div>


      {/* =================================================
          ANALYSIS
          ================================================= */}

      <div className="forest-analysis-card">

        <div>

          <div className="eyebrow">
            DEFORESTATION MONITORING
          </div>

          <h2>
            Run Forest Analysis
          </h2>

          <p>
            Start an analysis job for this
            forest area to identify potential
            vegetation and land-cover changes
            using the configured Sentinel-2
            imagery workflow.
          </p>

        </div>


        <button
          type="button"
          className="register-button"
          onClick={
            handleRunAnalysis
          }
          disabled={
            analysisLoading
          }
        >

          {analysisLoading
            ? "Starting Analysis..."
            : "Run Deforestation Analysis"}

        </button>

      </div>


      {/* =================================================
          ANALYSIS SUCCESS
          ================================================= */}

      {analysisMessage && (
        <div className="message-card success-card">

          <div className="success-icon">
            ✓
          </div>

          <div>

            <h3>
              Analysis Started
            </h3>

            <p>
              {analysisMessage}
            </p>

          </div>

        </div>
      )}


      {/* =================================================
          ANALYSIS ERROR
          ================================================= */}

      {analysisError && (
        <div className="error-card">

          <div className="error-icon">
            !
          </div>

          <div>

            <h3>
              Analysis Could Not Start
            </h3>

            <p>
              {analysisError}
            </p>

          </div>

        </div>
      )}

    </div>
  );
}