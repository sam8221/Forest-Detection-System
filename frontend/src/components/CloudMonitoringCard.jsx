/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Cloud Monitoring Card
 *
 * Purpose:
 *   Shows cloud conditions over a Copperbelt district, so an
 *   officer can tell whether imagery is worth analysing and
 *   whether a field visit is worth planning.
 *
 * Responsibilities:
 *   - Let the officer pick a district they are permitted.
 *   - Show current cloud cover from the weather provider.
 *   - Show cloud cover recorded for recent Sentinel-2 passes.
 *   - Refresh on a timer and on demand.
 *   - Say when a figure is missing, and why.
 *
 * The two figures are kept visibly apart. The current
 * reading carries the provider's name and its own
 * observation time; each satellite figure carries its
 * acquisition date. They are different measurements of
 * different moments, and the card never lets the newer
 * satellite figure stand in for the sky now.
 *
 * On what this does not claim:
 *   Cloud cover helps an officer choose an observation to
 *   analyse. It is never evidence about the forest. Cloud
 *   lowers NDVI and so does felling; separating those is
 *   the officer's judgement, and nothing here or in the
 *   detection path treats a cloud figure as a finding.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  Cloud,
  CloudOff,
  CloudSun,
  Cloudy,
  MapPin,
  RefreshCw,
  Satellite,
  Sun,
} from "lucide-react";

import {
  conditionPresentation,
  describeAge,
  describeSuitability,
  formatObservedAt,
  formatPercentage,
  gaugeGeometry,
  isReadingStale,
} from "../services/cloudConditions";

import { API_URL } from "../config";
import { TOKEN_KEY } from "../services/auth";

/**
 * How often the current reading is refreshed.
 *
 * Matched to the provider's own update interval, which
 * Open-Meteo reports as 900 seconds. Asking more often
 * returns the same numbers and spends a rate limit to do
 * it. The server caches for the same period, so a shorter
 * interval here would not even reach the provider.
 */
const REFRESH_INTERVAL_MS = 15 * 60 * 1000;

/** Past this age a reading is labelled stale rather than hidden. */
const STALE_AFTER_MS = 20 * 60 * 1000;

const ICONS = {
  sun: Sun,
  "cloud-sun": CloudSun,
  cloud: Cloud,
  cloudy: Cloudy,
  "cloud-off": CloudOff,
};

/**
 * The circular cloud-cover gauge.
 *
 * @param {object} props
 * @param {number|null} props.percentage Cloud cover.
 * @param {string} props.condition Server condition code.
 * @param {string} props.label Words for the condition.
 */
function CloudGauge({ percentage, condition, label }) {
  const radius = 54;

  const { circumference, dash, gap, hasValue } = gaugeGeometry(
    percentage,
    radius
  );

  const { tone, icon } = conditionPresentation(condition);

  const Icon = ICONS[icon] || CloudOff;

  return (
    <div
      className={`cloud-gauge cloud-tone-${tone}`}
      role="img"
      aria-label={
        hasValue
          ? `${formatPercentage(percentage)} cloud cover, ${label}`
          : `Cloud cover not available, ${label}`
      }
    >
      <svg viewBox="0 0 128 128" aria-hidden="true">
        <circle
          className="cloud-gauge-track"
          cx="64"
          cy="64"
          r={radius}
          fill="none"
          strokeWidth="9"
        />

        {/* Drawn only when there is a reading. An arc of
            zero length and no arc at all look the same, but
            a reading of 0% also puts "Clear" in the middle,
            which no-reading never does. */}
        {hasValue && (
          <circle
            className="cloud-gauge-value"
            cx="64"
            cy="64"
            r={radius}
            fill="none"
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={`${dash} ${gap}`}
            strokeDashoffset={circumference / 4}
            transform="rotate(-90 64 64)"
          />
        )}
      </svg>

      <div className="cloud-gauge-centre">
        <Icon size={19} aria-hidden="true" />

        <strong>{formatPercentage(percentage)}</strong>

        <span>{label}</span>
      </div>
    </div>
  );
}

/**
 * The dashboard's cloud monitoring card.
 *
 * @param {object} props
 * @param {string|number} [props.refreshSignal]
 *   Changes when the dashboard notices new satellite
 *   imagery, which is when the recorded cloud cover for this
 *   district can have changed. The card refetches rather
 *   than waiting out its timer.
 */
export default function CloudMonitoringCard({ refreshSignal }) {
  const [districts, setDistricts] = useState([]);
  const [districtId, setDistrictId] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Read once per render rather than stored, so a theme or
  // token change cannot leave a stale header behind.
  const headers = useCallback(
    () => ({
      Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY)}`,
    }),
    []
  );

  // ---------------------------------------------------------
  // Which districts this officer may monitor
  //
  // The server decides. A district officer is given one
  // option, which is their own, so the selector cannot offer
  // a choice the server would refuse.
  // ---------------------------------------------------------

  useEffect(() => {
    let cancelled = false;

    const loadDistricts = async () => {
      try {
        const response = await fetch(
          `${API_URL}/api/v1/cloud-monitoring/districts`,
          { headers: headers() }
        );

        if (!response.ok) {
          throw new Error(
            "The list of monitoring districts could not be loaded."
          );
        }

        const payload = await response.json();

        if (cancelled) return;

        setDistricts(payload.districts || []);

        setDistrictId(
          payload.default_district_id ??
            payload.districts?.[0]?.id ??
            null
        );
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
          setLoading(false);
        }
      }
    };

    loadDistricts();

    return () => {
      cancelled = true;
    };
  }, [headers]);

  // ---------------------------------------------------------
  // The report itself
  // ---------------------------------------------------------

  const loadReport = useCallback(
    async ({ manual = false } = {}) => {
      if (districtId == null) return;

      if (manual) {
        setRefreshing(true);
      }

      try {
        const response = await fetch(
          `${API_URL}/api/v1/cloud-monitoring` +
            `?district_id=${districtId}` +
            `&refresh=${manual ? "true" : "false"}`,
          { headers: headers() }
        );

        if (response.status === 403) {
          throw new Error(
            "You may only monitor conditions in your own jurisdiction."
          );
        }

        if (!response.ok) {
          throw new Error(
            "Cloud conditions could not be loaded for this district."
          );
        }

        setReport(await response.json());

        setError("");
      } catch (err) {
        // The previous report is deliberately kept. Stale
        // figures labelled as stale are worth more than a
        // blank panel, and the card says which it is
        // showing.
        setError(err.message);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [districtId, headers]
  );

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  // New imagery means the recorded cloud cover can have
  // changed, so the card does not wait out its timer.
  useEffect(() => {
    if (refreshSignal == null) return;

    loadReport();
  }, [refreshSignal, loadReport]);

  // ---------------------------------------------------------
  // Automatic refresh
  //
  // Paused while the tab is hidden: a card nobody is looking
  // at should not keep a provider busy, and the first thing
  // that happens on return is a fresh read.
  // ---------------------------------------------------------

  const loadReportRef = useRef(loadReport);

  useEffect(() => {
    loadReportRef.current = loadReport;
  }, [loadReport]);

  useEffect(() => {
    const tick = setInterval(() => {
      if (document.hidden) return;

      loadReportRef.current();
    }, REFRESH_INTERVAL_MS);

    const onVisible = () => {
      if (!document.hidden) {
        loadReportRef.current();
      }
    };

    document.addEventListener("visibilitychange", onVisible);

    return () => {
      clearInterval(tick);

      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  // ---------------------------------------------------------
  // Render
  // ---------------------------------------------------------

  const current = report?.current;
  const satellite = report?.satellite;
  const point = report?.observation_point;

  const stale = isReadingStale(
    current?.retrieved_at,
    STALE_AFTER_MS
  );

  return (
    <section className="status-panel cloud-card">
      <div className="cloud-card-header">
        <div>
          <span className="eyebrow">
            CLOUD CONDITIONS
          </span>

          <h3>Satellite Cloud Monitoring</h3>
        </div>

        <div className="cloud-card-actions">
          {districts.length > 1 && (
            <label className="cloud-district-select">
              <span className="cloud-visually-hidden">
                Monitoring district
              </span>

              <select
                value={districtId ?? ""}
                onChange={(event) =>
                  setDistrictId(Number(event.target.value))
                }
              >
                {districts.map((district) => (
                  <option key={district.id} value={district.id}>
                    {district.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          <button
            type="button"
            className="icon-button cloud-refresh"
            onClick={() => loadReport({ manual: true })}
            disabled={refreshing || districtId == null}
            aria-label="Refresh cloud conditions"
            title="Ask the weather provider again now"
          >
            <RefreshCw
              size={16}
              className={refreshing ? "is-spinning" : undefined}
            />
          </button>
        </div>
      </div>

      {loading && !report ? (
        <p className="cloud-card-loading">
          Loading cloud conditions…
        </p>
      ) : (
        <>
          {error && (
            <div className="cloud-card-error">{error}</div>
          )}

          {report && (
            <>
              <div className="cloud-card-body">
                <CloudGauge
                  percentage={current?.percentage ?? null}
                  condition={current?.condition || "UNKNOWN"}
                  label={current?.condition_label || "Not available"}
                />

                <dl className="cloud-facts">
                  <div>
                    <dt>
                      <MapPin size={13} aria-hidden="true" />
                      Location
                    </dt>

                    <dd>
                      {report.district_name}
                      {point && (
                        <small>
                          {point.latitude}, {point.longitude}
                          {point.source === "monitored_areas"
                            ? ` · centre of ${point.monitored_area_count} monitored area${
                                point.monitored_area_count === 1 ? "" : "s"
                              }`
                            : " · district town, no monitored area yet"}
                        </small>
                      )}
                    </dd>
                  </div>

                  <div>
                    <dt>Source</dt>

                    <dd>
                      {current?.available
                        ? current.provider
                        : "Not available"}

                      <small>
                        {current?.available
                          ? "Current weather observation"
                          : current?.unavailable_reason}
                      </small>
                    </dd>
                  </div>

                  <div>
                    <dt>Observed</dt>

                    <dd>
                      {formatObservedAt(current?.observed_at)}

                      {current?.retrieved_at && (
                        <small>
                          Retrieved{" "}
                          {describeAge(current.retrieved_at) ||
                            "just now"}
                          {stale && " · may be out of date"}
                        </small>
                      )}
                    </dd>
                  </div>
                </dl>
              </div>

              <div className="cloud-satellite">
                <div className="cloud-satellite-head">
                  <Satellite size={14} aria-hidden="true" />

                  <strong>Sentinel-2 observations</strong>

                  <span>{describeSuitability(satellite)}</span>
                </div>

                {satellite?.available && (
                  <ul className="cloud-observations">
                    {satellite.observations.map((observation) => {
                      const { tone } = conditionPresentation(
                        observation.condition
                      );

                      return (
                        <li
                          key={observation.image_id}
                          className={`cloud-observation cloud-tone-${tone}`}
                        >
                          <span className="cloud-observation-date">
                            {observation.acquisition_date}
                          </span>

                          <span className="cloud-observation-bar">
                            <span
                              style={{
                                width: `${Math.min(
                                  Math.max(observation.percentage, 0),
                                  100
                                )}%`,
                              }}
                            />
                          </span>

                          <span className="cloud-observation-value">
                            {formatPercentage(observation.percentage)}
                          </span>

                          <span
                            className={
                              "cloud-observation-flag" +
                              (observation.suitable_for_analysis
                                ? " is-suitable"
                                : "")
                            }
                          >
                            {observation.suitable_for_analysis === null
                              ? "unknown"
                              : observation.suitable_for_analysis
                                ? "analysable"
                                : "too cloudy"}
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <p className="cloud-card-footnote">
                Cloud cover helps choose which observation to
                analyse. It is not evidence of vegetation
                loss: cloud lowers NDVI and so does clearing.
                {report.generated_at && (
                  <>
                    {" "}
                    Last updated{" "}
                    {describeAge(report.generated_at) || "just now"}.
                  </>
                )}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
