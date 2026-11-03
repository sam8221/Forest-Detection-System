/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Forest Analytics
 *
 * Purpose:
 *   Presents forest-loss analytics, NDVI change statistics
 *   and advisory recommendations over stored results.
 *
 * Responsibilities:
 *   - Show headline figures for the officer's jurisdiction.
 *   - Chart potential loss over observed days.
 *   - Compare potential loss across districts.
 *   - Report NDVI change for a chosen analysis.
 *   - List advisory recommendations.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Note:
 *   Every number drawn here comes from the analytics
 *   endpoints, which derive them from stored analysis
 *   results. Nothing is computed in the browser and nothing
 *   is placeholder data.
 *
 *   Two distinctions are carried through from the API
 *   because collapsing either would mislead an officer:
 *
 *     A day missing from the trend was NOT OBSERVED. It is
 *     not a day with zero loss, and the chart leaves a gap
 *     rather than joining through it.
 *
 *     A district with observed false has had no analysis at
 *     all. Its empty bar means "not examined", not "nothing
 *     found", and it is labelled as such.
 * ===========================================================
 */

import { useCallback, useEffect, useState } from "react";

import {
  AlertCircle,
  AlertTriangle,
  BarChart3,
  CalendarRange,
  Download,
  Info,
  Leaf,
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

import { API_V1 } from "../config";

// =========================================================
// PRIORITY ORDER
//
// Matches PriorityLevel on the server so the badge colour
// and the sort agree with the advice they describe.
// =========================================================

// Sections a report may contain. The keys match what the
// backend accepts, so an unknown one is rejected there
// rather than silently dropped.
const REPORT_SECTIONS = [
  { key: "summary", label: "Executive summary" },
  { key: "forest_loss", label: "Forest-loss trend" },
  { key: "ndvi", label: "NDVI change analysis" },
  { key: "detections", label: "Detection details" },
  { key: "districts", label: "District comparison" },
  { key: "alerts", label: "Alert statistics" },
  { key: "recommendations", label: "Recommendations" },
  { key: "history", label: "Analysis history" },
];

const REPORT_FORMATS = [
  { key: "pdf", label: "PDF", hint: "for printing and review" },
  { key: "xlsx", label: "Excel", hint: "one sheet per section" },
  { key: "csv", label: "CSV", hint: "for further analysis" },
];

const PRIORITY_CLASS = {
  CRITICAL: "priority-critical",
  HIGH: "priority-high",
  MEDIUM: "priority-medium",
  LOW: "priority-low",
};

export default function Analytics() {
  const [summary, setSummary] = useState(null);
  const [trend, setTrend] = useState([]);
  const [districts, setDistricts] = useState([]);
  const [advice, setAdvice] = useState(null);

  const [forestAreas, setForestAreas] = useState([]);

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [districtId, setDistrictId] = useState("");
  const [forestAreaId, setForestAreaId] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // ---------------------------------------------------
  // Report download
  //
  // The report is generated and returned by one request, so
  // there is no job to poll. The button stays in its
  // generating state until the bytes have actually arrived.
  // Announcing a download before the file exists would be a
  // success message for something that may still fail.
  // ---------------------------------------------------

  const [reportOpen, setReportOpen] = useState(false);
  const [reportFormat, setReportFormat] = useState("pdf");
  const [reportSections, setReportSections] = useState(
    REPORT_SECTIONS.map((one) => one.key)
  );
  const [generating, setGenerating] = useState(false);
  const [reportError, setReportError] = useState("");
  const [reportNotice, setReportNotice] = useState("");

  // Both read the stored token when called, not when
  // defined, so neither depends on a render. Holding one
  // identity for the life of the page lets the effects below
  // declare them honestly instead of carrying a dependency
  // that changed on every render.
  const token = useCallback(
    () =>
      localStorage.getItem("access_token") ||
      localStorage.getItem("token"),
    []
  );

  const headers = useCallback(
    () => ({
      "Content-Type": "application/json",
      ...(token() ? { Authorization: `Bearer ${token()}` } : {}),
    }),
    [token]
  );

  // =======================================================
  // QUERY STRING
  //
  // Only filters the officer actually set are sent. An empty
  // value is omitted rather than sent as a blank, which the
  // server would reject as an invalid date or identifier.
  // =======================================================

  const queryString = useCallback(
    (include = {}) => {
      const parameters = new URLSearchParams();

      if (startDate) parameters.set("start_date", startDate);
      if (endDate) parameters.set("end_date", endDate);

      if (include.district && districtId) {
        parameters.set("district_id", districtId);
      }

      if (include.forestArea && forestAreaId) {
        parameters.set("forest_area_id", forestAreaId);
      }

      const query = parameters.toString();

      return query ? `?${query}` : "";
    },
    [startDate, endDate, districtId, forestAreaId]
  );

  // =======================================================
  // LOAD
  // =======================================================

  const load = useCallback(async () => {
    setLoading(true);
    setError("");

    const scoped = queryString({
      district: true,
      forestArea: true,
    });

    try {
      const responses = await Promise.all([
        fetch(`${API_V1}/analytics/summary${scoped}`, {
          headers: headers(),
        }),
        fetch(`${API_V1}/analytics/trend${scoped}`, {
          headers: headers(),
        }),
        fetch(
          `${API_V1}/analytics/districts${queryString()}`,
          { headers: headers() }
        ),
        fetch(
          `${API_V1}/analytics/recommendations${queryString({
            district: true,
            forestArea: true,
          })}`,
          { headers: headers() }
        ),
      ]);

      const failed = responses.find((one) => !one.ok);

      if (failed) {
        const body = await failed.json().catch(() => null);

        throw new Error(
          body?.detail ||
            `The analytics could not be loaded. Server returned ${failed.status}.`
        );
      }

      const [
        summaryBody,
        trendBody,
        districtBody,
        adviceBody,
      ] = await Promise.all(
        responses.map((one) => one.json())
      );

      setSummary(summaryBody);
      setTrend(trendBody);
      setDistricts(districtBody);
      setAdvice(adviceBody);
    } catch (requestError) {
      console.error("Analytics error:", requestError);

      setError(
        requestError?.message ||
          "The analytics could not be loaded."
      );
    } finally {
      setLoading(false);
    }
  }, [queryString, headers]);

  useEffect(() => {
    load();
  }, [load]);

  // Forest areas populate the filter. Already scoped to the
  // officer's jurisdiction by the endpoint, so the list can
  // never offer an area they may not see.
  useEffect(() => {
    fetch(`${API_V1}/forest-areas`, { headers: headers() })
      .then((response) =>
        response.ok ? response.json() : []
      )
      .then((body) =>
        setForestAreas(Array.isArray(body) ? body : [])
      )
      .catch(() => setForestAreas([]));
  }, [headers]);

  // =======================================================
  // GENERATE AND DOWNLOAD
  // =======================================================

  const toggleSection = (key) => {
    setReportSections((current) =>
      current.includes(key)
        ? current.filter((one) => one !== key)
        : [...current, key]
    );
  };

  const generateReport = async () => {
    setReportError("");
    setReportNotice("");

    if (reportSections.length === 0) {
      setReportError(
        "Select at least one section to include."
      );
      return;
    }

    setGenerating(true);

    try {
      const response = await fetch(
        `${API_V1}/reports/analytics`,
        {
          method: "POST",
          headers: {
            ...headers(),
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            format: reportFormat,
            sections: reportSections,
            // The dashboard filters are the report filters,
            // so the document matches what is on screen.
            start_date: startDate || null,
            end_date: endDate || null,
            district_id: districtId ? Number(districtId) : null,
            forest_area_id: forestAreaId
              ? Number(forestAreaId)
              : null,
          }),
        }
      );

      if (!response.ok) {
        // The error body is JSON even though a success is a
        // file, so it is read as text and parsed leniently.
        const raw = await response.text();

        let detail = "";

        try {
          const parsed = JSON.parse(raw);
          detail = Array.isArray(parsed?.detail)
            ? parsed.detail
                .map((one) => one.msg || one)
                .join("; ")
            : parsed?.detail || "";
        } catch {
          detail = "";
        }

        throw new Error(
          detail ||
            `The report could not be generated (${response.status}).`
        );
      }

      const blob = await response.blob();

      // Prefer the filename the server chose: it carries the
      // real generation date and the scope.
      const disposition =
        response.headers.get("Content-Disposition") || "";

      const match = disposition.match(
        /filename="?([^"]+)"?/
      );

      const filename =
        match?.[1] ||
        `Forest_Analytics_${new Date()
          .toISOString()
          .slice(0, 10)}.${reportFormat}`;

      const url = URL.createObjectURL(blob);

      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();

      URL.revokeObjectURL(url);

      // Only now, with the bytes in hand.
      setReportNotice(`${filename} downloaded.`);
    } catch (requestError) {
      console.error("Report error:", requestError);

      setReportError(
        requestError?.message ||
          "The report could not be generated."
      );
    } finally {
      setGenerating(false);
    }
  };

  const clearFilters = () => {
    setStartDate("");
    setEndDate("");
    setDistrictId("");
    setForestAreaId("");
  };

  // =======================================================
  // RENDER
  // =======================================================

  if (loading && summary === null) {
    return (
      <div className="analytics-page">
        <div className="analytics-loading">
          <RefreshCw size={20} className="refresh-spinning" />
          <span>Loading analytics…</span>
        </div>
      </div>
    );
  }

  const observedDistricts = districts.filter(
    (one) => one.observed
  );

  const unobservedDistricts = districts.filter(
    (one) => !one.observed
  );

  return (
    <div className="analytics-page">
      {/* ================= HEADER ================= */}

      <div className="analytics-header">
        <div>
          <h1>
            <BarChart3 size={26} />
            Forest Analytics
          </h1>

          <p>
            Potential vegetation loss across the monitored
            areas you are responsible for.
          </p>
        </div>

        <div className="analytics-header-actions">
          <button
            type="button"
            className="analytics-clear"
            onClick={() => setReportOpen((open) => !open)}
            aria-expanded={reportOpen}
          >
            <Download size={15} />
            Download report
          </button>

          <button
            type="button"
            className="acquire-button"
            onClick={load}
            disabled={loading}
          >
            <RefreshCw
              size={15}
              className={loading ? "refresh-spinning" : ""}
            />
            Refresh
          </button>
        </div>
      </div>

      {/* ================= REPORT PANEL ================= */}

      {reportOpen && (
        <div className="analytics-panel report-panel">
          <div className="analytics-panel-header">
            <h2>Generate a report</h2>
            <span className="analytics-unit">
              uses the filters above
            </span>
          </div>

          <div className="report-formats">
            {REPORT_FORMATS.map((one) => (
              <button
                key={one.key}
                type="button"
                className={
                  "report-format" +
                  (reportFormat === one.key
                    ? " report-format-active"
                    : "")
                }
                onClick={() => setReportFormat(one.key)}
              >
                <strong>{one.label}</strong>
                <span>{one.hint}</span>
              </button>
            ))}
          </div>

          <fieldset className="report-sections">
            <legend>Sections to include</legend>

            {REPORT_SECTIONS.map((one) => (
              <label key={one.key}>
                <input
                  type="checkbox"
                  checked={reportSections.includes(one.key)}
                  onChange={() => toggleSection(one.key)}
                />
                {one.label}
              </label>
            ))}
          </fieldset>

          <div className="report-actions">
            <button
              type="button"
              className="acquire-button"
              onClick={generateReport}
              disabled={generating}
            >
              {generating ? (
                <>
                  <RefreshCw
                    size={15}
                    className="refresh-spinning"
                  />
                  Generating…
                </>
              ) : (
                <>
                  <Download size={15} />
                  Generate {reportFormat.toUpperCase()}
                </>
              )}
            </button>

            <button
              type="button"
              className="analytics-clear"
              onClick={() =>
                setReportSections(
                  REPORT_SECTIONS.map((one) => one.key)
                )
              }
            >
              Select all
            </button>
          </div>

          {reportError && (
            <div className="sentinel-search-error">
              <AlertCircle size={17} />
              <span>{reportError}</span>
            </div>
          )}

          {reportNotice && (
            <div className="sentinel-acquire-notice">
              <Download size={17} />
              <span>{reportNotice}</span>
            </div>
          )}

          <p className="analytics-footnote">
            <Info size={14} />
            The report contains only the forest areas you are
            authorised to see, and states where a figure
            could not be measured rather than writing a zero.
          </p>
        </div>
      )}

      {error && (
        <div className="sentinel-search-error">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* ================= FILTERS ================= */}

      <div className="analytics-filters">
        <div className="analytics-filter">
          <label htmlFor="analytics-start">From</label>
          <input
            id="analytics-start"
            type="date"
            value={startDate}
            onChange={(event) =>
              setStartDate(event.target.value)
            }
          />
        </div>

        <div className="analytics-filter">
          <label htmlFor="analytics-end">To</label>
          <input
            id="analytics-end"
            type="date"
            value={endDate}
            onChange={(event) =>
              setEndDate(event.target.value)
            }
          />
        </div>

        <div className="analytics-filter">
          <label htmlFor="analytics-district">District</label>
          <select
            id="analytics-district"
            value={districtId}
            onChange={(event) =>
              setDistrictId(event.target.value)
            }
          >
            <option value="">All districts</option>
            {districts.map((one) => (
              <option
                key={one.district_id}
                value={one.district_id}
              >
                {one.district}
              </option>
            ))}
          </select>
        </div>

        <div className="analytics-filter">
          <label htmlFor="analytics-forest">Forest area</label>
          <select
            id="analytics-forest"
            value={forestAreaId}
            onChange={(event) =>
              setForestAreaId(event.target.value)
            }
          >
            <option value="">All forest areas</option>
            {forestAreas.map((one) => (
              <option key={one.id} value={one.id}>
                {one.name}
              </option>
            ))}
          </select>
        </div>

        <button
          type="button"
          className="analytics-clear"
          onClick={clearFilters}
        >
          Clear
        </button>
      </div>

      {/* ================= EMPTY STATE ================= */}

      {/*
        Three states, not two. summary is null when the
        request failed, and rendering the cards from it would
        throw on the first figure. The error is already shown
        above, so this branch simply stops.
      */}
      {summary === null ? null : !summary.has_results ? (
        <div className="analytics-empty">
          <TreePine size={34} />

          <h2>No analysis results yet</h2>

          <p>
            Nothing has been detected in the areas you are
            responsible for, for the filters selected. This
            is not a report of zero deforestation: it means
            no analysis has produced a result here yet.
          </p>

          <p>
            Acquire a Sentinel-2 product for a monitored area
            and run an analysis to populate these figures.
          </p>
        </div>
      ) : (
        <>
          {/* ================= KPI CARDS ================= */}

          <div className="analytics-kpis">
            <Kpi
              icon={<TreePine size={18} />}
              label="Monitored forest area"
              value={`${summary.monitored_hectares.toLocaleString()} ha`}
              note={`${summary.monitored_forest_areas} areas`}
            />

            <Kpi
              icon={<Leaf size={18} />}
              label="Potential loss, cumulative"
              value={`${summary.cumulative_loss_hectares.toLocaleString()} ha`}
              note="Sum of all detections"
            />

            <Kpi
              icon={<Leaf size={18} />}
              label="Potential loss, unique ground"
              value={
                summary.unique_loss_hectares === null
                  ? "Not available"
                  : `${summary.unique_loss_hectares.toLocaleString()} ha`
              }
              note={
                summary.unique_loss_hectares === null
                  ? "No detection in scope has an outline"
                  : `Overlaps dissolved, from ${summary.detections_with_outline} outlines`
              }
            />

            <Kpi
              icon={<AlertTriangle size={18} />}
              label="Detections"
              value={summary.total_detections}
              note={`Across ${summary.forest_areas_with_detections} areas`}
            />

            <Kpi
              icon={<BarChart3 size={18} />}
              label="Forest areas analysed"
              value={summary.forest_areas_analysed}
              note="With a completed analysis"
            />

            <Kpi
              icon={<CalendarRange size={18} />}
              label="Latest analysis"
              value={
                summary.latest_analysis_at
                  ? new Date(
                      summary.latest_analysis_at
                    ).toLocaleDateString()
                  : "None"
              }
              note={
                summary.latest_analysis_at
                  ? "Most recent completed run"
                  : "No analysis has completed"
              }
            />
          </div>

          {/* ================= TREND ================= */}

          <div className="analytics-panel">
            <div className="analytics-panel-header">
              <h2>Potential forest loss over time</h2>

              <span className="analytics-unit">
                hectares per observed day
              </span>
            </div>

            {trend.length === 0 ? (
              <EmptyPanel message="No analysis has completed in this period, so there is nothing to plot. An empty chart here means no observation, not no loss." />
            ) : (
              <>
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={trend}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#e4ebe6"
                    />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 12 }}
                    />
                    <YAxis
                      tick={{ fontSize: 12 }}
                      label={{
                        value: "hectares",
                        angle: -90,
                        position: "insideLeft",
                        style: { fontSize: 12 },
                      }}
                    />
                    <Tooltip
                      formatter={(value, name) =>
                        name === "loss_hectares"
                          ? [`${value} ha`, "Potential loss"]
                          : [value, name]
                      }
                      labelFormatter={(label) =>
                        `Observed ${label}`
                      }
                    />
                    <Line
                      type="monotone"
                      dataKey="loss_hectares"
                      stroke="#166534"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      name="loss_hectares"
                    />
                  </LineChart>
                </ResponsiveContainer>

                <p className="analytics-footnote">
                  <Info size={14} />
                  Each point is a day an analysis completed. A
                  point at zero means an analysis ran and found
                  no clearing large enough to report. Days
                  between points were not observed.
                </p>
              </>
            )}
          </div>

          {/* ================= DISTRICTS ================= */}

          <div className="analytics-panel">
            <div className="analytics-panel-header">
              <h2>Potential loss by district</h2>

              <span className="analytics-unit">hectares</span>
            </div>

            {observedDistricts.length === 0 ? (
              <EmptyPanel message="No district in your jurisdiction has a completed analysis yet." />
            ) : (
              <>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={observedDistricts}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="#e4ebe6"
                    />
                    <XAxis
                      dataKey="district"
                      tick={{ fontSize: 12 }}
                    />
                    <YAxis
                      tick={{ fontSize: 12 }}
                      label={{
                        value: "hectares",
                        angle: -90,
                        position: "insideLeft",
                        style: { fontSize: 12 },
                      }}
                    />
                    <Tooltip
                      formatter={(value) => [
                        `${value} ha`,
                        "Potential loss",
                      ]}
                    />
                    <Bar
                      dataKey="loss_hectares"
                      fill="#166534"
                      radius={[5, 5, 0, 0]}
                      name="Potential loss"
                    />
                  </BarChart>
                </ResponsiveContainer>

                {unobservedDistricts.length > 0 && (
                  <p className="analytics-footnote">
                    <Info size={14} />
                    Not charted because no analysis has
                    completed there:{" "}
                    {unobservedDistricts
                      .map((one) => one.district)
                      .join(", ")}
                    . Their absence reflects a lack of
                    observation, not an absence of clearing.
                  </p>
                )}
              </>
            )}
          </div>

          {/* ================= RECOMMENDATIONS ================= */}

          <div className="analytics-panel">
            <div className="analytics-panel-header">
              <h2>Advisory recommendations</h2>

              <span className="analytics-unit">
                {advice?.recommendations?.length ?? 0} items
              </span>
            </div>

            <p className="analytics-caution">
              <AlertTriangle size={15} />
              Advice, not findings. A fall in vegetation index
              can follow harvest, fire, drought or cultivation
              as well as felling, and this system does not
              distinguish them. Nothing here establishes that
              clearing was unlawful.
            </p>

            {(advice?.recommendations?.length ?? 0) === 0 ? (
              <EmptyPanel message="No rule has been triggered by the records in scope." />
            ) : (
              <ul className="analytics-advice">
                {advice.recommendations.map((item, index) => (
                  <li
                    key={`${item.rule}-${index}`}
                    className="analytics-advice-item"
                  >
                    <div className="analytics-advice-head">
                      <span
                        className={`priority-badge ${
                          PRIORITY_CLASS[item.priority] || ""
                        }`}
                      >
                        {item.priority}
                      </span>

                      <strong>
                        {item.rule.replaceAll("_", " ")}
                      </strong>

                      {item.forest_area && (
                        <span className="analytics-advice-place">
                          <MapPin size={13} />
                          {item.forest_area}
                          {item.district
                            ? ` · ${item.district}`
                            : ""}
                        </span>
                      )}
                    </div>

                    <p className="analytics-advice-finding">
                      {item.finding}
                    </p>

                    <p className="analytics-advice-action">
                      <strong>Suggested action: </strong>
                      {item.action}
                    </p>
                  </li>
                ))}
              </ul>
            )}

            {advice?.rules && (
              <details className="analytics-rules">
                <summary>
                  Thresholds these recommendations use
                </summary>

                <ul>
                  {Object.entries(advice.rules).map(
                    ([name, value]) => (
                      <li key={name}>
                        <code>{name}</code>: {String(value)}
                      </li>
                    )
                  )}
                </ul>
              </details>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// =========================================================
// SMALL PRESENTATION PIECES
// =========================================================

function Kpi({ icon, label, value, note }) {
  return (
    <div className="analytics-kpi">
      <div className="analytics-kpi-icon">{icon}</div>

      <div>
        <span className="analytics-kpi-label">{label}</span>
        <strong className="analytics-kpi-value">{value}</strong>
        {note && (
          <span className="analytics-kpi-note">{note}</span>
        )}
      </div>
    </div>
  );
}

function EmptyPanel({ message }) {
  return (
    <div className="analytics-panel-empty">
      <Info size={18} />
      <span>{message}</span>
    </div>
  );
}
