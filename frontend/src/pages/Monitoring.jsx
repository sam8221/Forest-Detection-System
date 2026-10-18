/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Forest Monitoring
 *
 * Purpose:
 *   Opens a detailed monitoring view for one forest area:
 *   satellite imagery, NDVI layers, the vegetation change
 *   found there, and the distribution behind it.
 *
 * Responsibilities:
 *   - Choose a forest area and zoom the map to it.
 *   - Switch between the NDVI layers that exist for it.
 *   - Report the readings under a clicked point.
 *   - Chart NDVI over observation dates and its histogram.
 *   - Summarise the vegetation change.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Note:
 *   Every layer, figure and chart point comes from the
 *   monitoring and analytics endpoints, which read rasters
 *   and records the pipeline produced. A layer that was
 *   never produced is offered as unavailable rather than
 *   drawn empty, because an empty overlay reads as measured
 *   ground with no vegetation.
 *
 *   Detected areas are labelled POTENTIAL vegetation loss
 *   throughout. A fall in NDVI follows harvest, fire,
 *   drought and cultivation as well as felling, and nothing
 *   here distinguishes them.
 * ===========================================================
 */

import { useCallback, useEffect, useState } from "react";

import {
  AlertCircle,
  AlertTriangle,
  CalendarRange,
  Info,
  Layers,
  MapPin,
  RefreshCw,
  TreePine,
} from "lucide-react";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import ForestMonitoringMap from "../components/ForestMonitoringMap";
import { API_V1 } from "../config";

// The colour ramp the backend paints NDVI with, repeated
// here only as a legend. The authority is the server.
const NDVI_LEGEND = [
  { colour: "#a52a20", label: "≤ 0.05  bare, built, water" },
  { colour: "#e8963c", label: "0.20  sparse" },
  { colour: "#f3d658", label: "0.35  moderate" },
  { colour: "#a6cf5e", label: "0.50  vegetated" },
  { colour: "#155226", label: "≥ 0.70  dense canopy" },
];

const DIFFERENCE_LEGEND = [
  { colour: "#156e3c", label: "NDVI rose (growth)" },
  { colour: "#f2f4f0", label: "little change" },
  { colour: "#f0aa5a", label: "modest decline" },
  { colour: "#961818", label: "severe decline" },
];

export default function Monitoring() {
  const [forestAreas, setForestAreas] = useState([]);
  const [forestAreaId, setForestAreaId] = useState("");

  const [detail, setDetail] = useState(null);
  const [activeLayer, setActiveLayer] = useState(
    "ndvi_difference"
  );
  const [opacity, setOpacity] = useState(0.85);

  const [histogram, setHistogram] = useState(null);
  const [trend, setTrend] = useState(null);
  const [change, setChange] = useState(null);

  const [sample, setSample] = useState(null);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const token = () =>
    localStorage.getItem("access_token") ||
    localStorage.getItem("token");

  const headers = () => ({
    Authorization: `Bearer ${token()}`,
  });

  // =======================================================
  // FOREST AREAS
  //
  // Already scoped to the officer's jurisdiction by the
  // endpoint, so the picker cannot offer an area they are
  // not permitted to open.
  // =======================================================

  useEffect(() => {
    fetch(`${API_V1}/forest-areas`, { headers: headers() })
      .then((response) =>
        response.ok ? response.json() : []
      )
      .then((body) => {
        const list = Array.isArray(body) ? body : [];
        setForestAreas(list);

        if (list.length > 0) {
          setForestAreaId(String(list[0].id));
        }
      })
      .catch(() => setForestAreas([]));
  }, []);

  // =======================================================
  // LOAD THE SELECTED AREA
  // =======================================================

  const load = useCallback(async () => {
    if (!forestAreaId) return;

    setLoading(true);
    setError("");
    setSample(null);

    try {
      const layersResponse = await fetch(
        `${API_V1}/monitoring/${forestAreaId}/layers`,
        { headers: headers() }
      );

      if (!layersResponse.ok) {
        const body = await layersResponse
          .json()
          .catch(() => null);

        throw new Error(
          body?.detail ||
            `The monitoring map could not be opened (${layersResponse.status}).`
        );
      }

      const layerBody = await layersResponse.json();

      setDetail(layerBody);

      // Prefer the change layer when it exists: it is the
      // one that answers what an officer came to ask.
      const firstAvailable =
        layerBody.layers.find(
          (one) =>
            one.key === "ndvi_difference" && one.available
        ) || layerBody.layers.find((one) => one.available);

      setActiveLayer(firstAvailable?.key || "");

      // The remaining panels are independent, so a failure
      // in one leaves the others drawn.
      const [histogramBody, trendBody, changeBody] =
        await Promise.all([
          fetch(
            `${API_V1}/monitoring/${forestAreaId}/histogram` +
              `?layer=ndvi_current&bins=40`,
            { headers: headers() }
          )
            .then((one) => (one.ok ? one.json() : null))
            .catch(() => null),

          fetch(
            `${API_V1}/monitoring/${forestAreaId}/ndvi-trend`,
            { headers: headers() }
          )
            .then((one) => (one.ok ? one.json() : null))
            .catch(() => null),

          layerBody.latest_analysis
            ? fetch(
                `${API_V1}/analytics/ndvi/${layerBody.latest_analysis.id}`,
                { headers: headers() }
              )
                .then((one) => (one.ok ? one.json() : null))
                .catch(() => null)
            : Promise.resolve(null),
        ]);

      setHistogram(histogramBody);
      setTrend(trendBody);
      setChange(changeBody);
    } catch (requestError) {
      console.error("Monitoring error:", requestError);
      setError(
        requestError?.message ||
          "The monitoring map could not be opened."
      );
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }, [forestAreaId]);

  useEffect(() => {
    load();
  }, [load]);

  const selected = detail?.forest_area;
  const analysis = detail?.latest_analysis;

  const legend =
    activeLayer === "ndvi_difference"
      ? DIFFERENCE_LEGEND
      : NDVI_LEGEND;

  return (
    <div className="monitoring-page">
      {/* ================= HEADER ================= */}

      <div className="analytics-header">
        <div>
          <h1>
            <Layers size={26} />
            Forest Monitoring Map
          </h1>

          <p>
            Satellite imagery, vegetation index and potential
            loss for one monitored area.
          </p>
        </div>

        <div className="monitoring-picker">
          <label htmlFor="monitoring-area">Forest area</label>

          <select
            id="monitoring-area"
            value={forestAreaId}
            onChange={(event) =>
              setForestAreaId(event.target.value)
            }
          >
            {forestAreas.length === 0 && (
              <option value="">
                No forest areas available
              </option>
            )}

            {forestAreas.map((one) => (
              <option key={one.id} value={one.id}>
                {one.name}
              </option>
            ))}
          </select>

          <button
            type="button"
            className="acquire-button"
            onClick={load}
            disabled={loading || !forestAreaId}
          >
            <RefreshCw
              size={15}
              className={loading ? "refresh-spinning" : ""}
            />
            Reload
          </button>
        </div>
      </div>

      {error && (
        <div className="sentinel-search-error">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {detail === null && !loading && !error && (
        <div className="analytics-empty">
          <TreePine size={34} />
          <h2>Select a forest area</h2>
          <p>
            Choose a monitored area to open its imagery and
            vegetation layers.
          </p>
        </div>
      )}

      {/*
        Why there are no layers, when there are none.
        "Never analysed", "still running", "failed" and
        "completed but produced nothing" call for different
        responses from the officer, so the server names
        which one applies and the reason is shown rather
        than leaving an empty map to be interpreted.
      */}
      {detail &&
        detail.analysis_state !== "COMPLETED" && (
          <div className="analytics-panel-empty">
            <Info size={17} />
            <span>
              <strong>
                {detail.analysis_state.replaceAll("_", " ")}
              </strong>
              {detail.analysis_detail
                ? ` — ${detail.analysis_detail}`
                : ""}
            </span>
          </div>
        )}

      {/*
        Outputs used to be stored per forest area, so each
        analysis overwrote the one before it. A job from
        that era shows rasters that may belong to a LATER
        analysis of the same area, while the dates beside
        them belong to this job. Saying so is the only
        honest option short of re-running the analysis.
      */}
      {analysis?.is_legacy_storage && (
        <div className="analytics-caution">
          <AlertTriangle size={15} />
          These layers were produced before results were
          stored per analysis, when each run overwrote the
          last. They are the most recent rasters for this
          area and may not be the ones this job produced,
          although the observation dates shown are its own.
          Run a new analysis for results tied to their job.
        </div>
      )}

      {detail && (
        <div className="monitoring-layout">
          {/* ============ MAP COLUMN ============ */}

          <div className="monitoring-main">
            <ForestMonitoringMap
              forestAreaId={forestAreaId}
              layers={detail.layers}
              activeLayer={activeLayer}
              boundary={selected?.boundary}
              imageryBounds={detail.imagery_bounds}
              opacity={opacity}
              onSample={setSample}
            />

            {/* --------- LAYER CONTROL --------- */}

            <div className="monitoring-controls">
              <div className="monitoring-layer-list">
                {detail.layers.map((one) => (
                  <button
                    key={one.key}
                    type="button"
                    disabled={!one.available}
                    title={
                      one.available
                        ? one.description
                        : "Not produced for this area yet"
                    }
                    className={
                      "monitoring-layer" +
                      (activeLayer === one.key
                        ? " monitoring-layer-active"
                        : "") +
                      (one.available
                        ? ""
                        : " monitoring-layer-missing")
                    }
                    onClick={() => setActiveLayer(one.key)}
                  >
                    {one.label}
                    {!one.available && " (none)"}
                  </button>
                ))}
              </div>

              <div className="monitoring-opacity">
                <label htmlFor="monitoring-opacity">
                  Overlay opacity
                </label>

                <input
                  id="monitoring-opacity"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={opacity}
                  onChange={(event) =>
                    setOpacity(Number(event.target.value))
                  }
                />
              </div>
            </div>

            {/* --------- LEGEND --------- */}

            <div className="monitoring-legend">
              <strong>
                {
                  detail.layers.find(
                    (one) => one.key === activeLayer
                  )?.label
                }
              </strong>

              <p className="monitoring-legend-note">
                {
                  detail.layers.find(
                    (one) => one.key === activeLayer
                  )?.description
                }
              </p>

              <div className="monitoring-legend-swatches">
                {legend.map((entry) => (
                  <span key={entry.label}>
                    <i
                      style={{ background: entry.colour }}
                    />
                    {entry.label}
                  </span>
                ))}
              </div>

              <p className="monitoring-legend-note">
                <Info size={13} /> The background imagery is
                an Esri basemap for orientation. It is not the
                Sentinel-2 imagery the analysis was run on.
              </p>
            </div>
          </div>

          {/* ============ SIDE COLUMN ============ */}

          <div className="monitoring-side">
            {/* --------- AREA --------- */}

            <div className="analytics-panel">
              <div className="analytics-panel-header">
                <h2>{selected?.name}</h2>
                <span className="analytics-unit">
                  {selected?.forest_code}
                </span>
              </div>

              <dl className="monitoring-facts">
                <dt>Registered area</dt>
                <dd>{selected?.area_hectares ?? "—"} ha</dd>

                <dt>Observation windows</dt>
                <dd>
                  {analysis?.baseline_start &&
                  analysis?.comparison_end ? (
                    <>
                      {analysis.baseline_start} →{" "}
                      {analysis.baseline_end}
                      <br />
                      {analysis.comparison_start} →{" "}
                      {analysis.comparison_end}
                    </>
                  ) : (
                    "Not recorded"
                  )}
                </dd>

                <dt>NDVI threshold</dt>
                <dd>{analysis?.ndvi_threshold ?? "—"}</dd>

                <dt>Cloud cover</dt>
                <dd>
                  {analysis?.cloud_cover_percentage != null
                    ? `${Number(
                        analysis.cloud_cover_percentage
                      ).toFixed(1)}%`
                    : "—"}
                </dd>
              </dl>
            </div>

            {/* --------- CLICKED POINT --------- */}

            <div className="analytics-panel">
              <div className="analytics-panel-header">
                <h2>Point reading</h2>
                <span className="analytics-unit">
                  click the map
                </span>
              </div>

              {sample === null ? (
                <div className="analytics-panel-empty">
                  <MapPin size={17} />
                  <span>
                    Click anywhere on the map to read the
                    vegetation index at that point.
                  </span>
                </div>
              ) : (
                <dl className="monitoring-facts">
                  <dt>Coordinates</dt>
                  <dd>
                    {sample.latitude?.toFixed(5)},{" "}
                    {sample.longitude?.toFixed(5)}
                  </dd>

                  {sample.error ? (
                    <>
                      <dt>Status</dt>
                      <dd>{sample.error}</dd>
                    </>
                  ) : (
                    Object.entries(
                      sample.readings || {}
                    ).map(([key, value]) => (
                      <RowReading
                        key={key}
                        name={key}
                        value={value}
                      />
                    ))
                  )}
                </dl>
              )}
            </div>

            {/* --------- CHANGE SUMMARY --------- */}

            <div className="analytics-panel">
              <div className="analytics-panel-header">
                <h2>Vegetation change</h2>
                <span className="analytics-unit">
                  latest analysis
                </span>
              </div>

              {!change || !change.rasters_available ? (
                <div className="analytics-panel-empty">
                  <Info size={17} />
                  <span>
                    No completed analysis with imagery for
                    this area yet.
                  </span>
                </div>
              ) : (
                <>
                  <dl className="monitoring-facts">
                    <dt>Mean NDVI, earlier</dt>
                    <dd>{change.mean_ndvi_before ?? "—"}</dd>

                    <dt>Mean NDVI, later</dt>
                    <dd>{change.mean_ndvi_after ?? "—"}</dd>

                    <dt>Difference</dt>
                    <dd>
                      {change.mean_ndvi_difference ?? "—"}
                    </dd>

                    <dt>Pixels that declined</dt>
                    <dd>
                      {change.declined_pixel_percentage != null
                        ? `${change.declined_pixel_percentage}%`
                        : "—"}
                    </dd>

                    <dt>Area past threshold</dt>
                    <dd>
                      {change.declined_hectares != null
                        ? `${change.declined_hectares} ha`
                        : "—"}
                    </dd>
                  </dl>

                  <p className="analytics-caution">
                    <AlertTriangle size={15} />
                    Potential vegetation loss. A fall in NDVI
                    can follow harvest, fire, drought or
                    cultivation as well as felling. These
                    locations are candidates for verification,
                    not confirmed clearing.
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ================= CHARTS ================= */}

      {detail && (
        <div className="monitoring-charts">
          <div className="analytics-panel">
            <div className="analytics-panel-header">
              <h2>NDVI by observation date</h2>
              <span className="analytics-unit">
                mean at detected locations
              </span>
            </div>

            {!trend || trend.points.length === 0 ? (
              <div className="analytics-panel-empty">
                <CalendarRange size={17} />
                <span>
                  No analysis with recorded observation
                  windows for this area yet.
                </span>
              </div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={240}>
                  <LineChart data={trend.points}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#e4ebe6"
                    />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 11 }}
                    />
                    <YAxis
                      domain={[-1, 1]}
                      tick={{ fontSize: 11 }}
                      label={{
                        value: "NDVI",
                        angle: -90,
                        position: "insideLeft",
                        style: { fontSize: 11 },
                      }}
                    />
                    <Tooltip
                      formatter={(value) => [value, "Mean NDVI"]}
                    />
                    <Line
                      type="monotone"
                      dataKey="mean_ndvi"
                      stroke="#166534"
                      strokeWidth={2}
                      dot={{ r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>

                <p className="analytics-footnote">
                  <Info size={14} />
                  {trend.basis} Detected patches are, by
                  selection, ground that lost vegetation, so
                  this is not the area's overall greenness.
                </p>
              </>
            )}
          </div>

          <div className="analytics-panel">
            <div className="analytics-panel-header">
              <h2>Histogram of NDVI</h2>
              <span className="analytics-unit">
                {histogram?.valid_pixels
                  ? `${histogram.valid_pixels.toLocaleString()} valid pixels`
                  : "later observation"}
              </span>
            </div>

            {!histogram || histogram.valid_pixels === 0 ? (
              <div className="analytics-panel-empty">
                <Info size={17} />
                <span>
                  No NDVI raster has been produced for this
                  area yet.
                </span>
              </div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={histogram.bins}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#e4ebe6"
                    />
                    <XAxis
                      dataKey="value"
                      tick={{ fontSize: 10 }}
                      label={{
                        value: "NDVI",
                        position: "insideBottom",
                        offset: -2,
                        style: { fontSize: 11 },
                      }}
                    />
                    <YAxis
                      tick={{ fontSize: 10 }}
                      label={{
                        value: "pixels",
                        angle: -90,
                        position: "insideLeft",
                        style: { fontSize: 11 },
                      }}
                    />
                    <Tooltip
                      formatter={(value) => [
                        Number(value).toLocaleString(),
                        "Pixels",
                      ]}
                      labelFormatter={(label) =>
                        `NDVI ${label}`
                      }
                    />
                    <Bar dataKey="count" fill="#2f7d4f" />
                  </BarChart>
                </ResponsiveContainer>

                <p className="analytics-footnote">
                  <Info size={14} />
                  Valid pixels only. Cloud, shadow and
                  no-data are excluded, so the distribution
                  describes ground that was actually
                  measured. Mean {histogram.mean}, range{" "}
                  {histogram.minimum} to {histogram.maximum}.
                </p>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// =========================================================
// READING ROW
// =========================================================

const READING_LABELS = {
  ndvi_current: "NDVI, later",
  ndvi_previous: "NDVI, earlier",
  ndvi_difference: "NDVI change",
  confirmed_loss: "Past threshold",
};

function RowReading({ name, value }) {
  return (
    <>
      <dt>{READING_LABELS[name] || name}</dt>
      <dd>
        {value === null ? (
          <span className="monitoring-no-reading">
            no reading
          </span>
        ) : name === "confirmed_loss" ? (
          "yes"
        ) : (
          value
        )}
      </dd>
    </>
  );
}
