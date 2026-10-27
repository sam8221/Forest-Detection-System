/**
 * Display rules for the metrics an analysis job reports.
 *
 * These live apart from Analysis.jsx so the rule they exist
 * to enforce can be tested without rendering a component:
 * a quantity the backend did not report is never displayed
 * as a measurement of zero.
 *
 * Why that distinction matters here. An affected area of
 * 0.00 ha is a finding - the analysis ran over the forest
 * area and found no clearing that met the half-hectare
 * minimum. "No figure was reported" is not a finding; it
 * means the result is incomplete or the job has not
 * finished. An officer reading the first should wait for the
 * next acquisition; one reading the second should look for a
 * fault. Collapsing them into the same "0.00" removes the
 * difference the officer needs.
 */

/** Shown where the backend reported no value. */
export const NOT_AVAILABLE = "Not available";

/**
 * Shown where a metric cannot apply rather than merely being
 * absent, such as a confidence score for an analysis that
 * produced no detections to be confident about.
 */
export const NOT_APPLICABLE = "Not applicable";

/** Shown for a completed analysis that found no clearing. */
export const NONE_DETECTED = "None detected";

/**
 * Format a number for display, or null when there is none.
 *
 * Returns null - never "0.00" - for null, undefined, an empty
 * string, NaN and Infinity, so a caller cannot accidentally
 * present a missing reading as a zero one.
 *
 * @param {unknown} value
 * @param {number} decimals
 * @returns {string|null}
 */
export function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  const number = Number(value);

  if (!Number.isFinite(number)) {
    return null;
  }

  return number.toFixed(decimals);
}

/**
 * Format a measured quantity with its unit.
 *
 * The unit is attached only to a real reading, so nothing
 * ever renders as "Not available%".
 *
 * @param {unknown} value
 * @param {string} unit
 * @param {number} decimals
 * @returns {string}
 */
export function formatMeasurement(value, unit = "", decimals = 2) {
  const formatted = formatNumber(value, decimals);

  return formatted === null ? NOT_AVAILABLE : `${formatted}${unit}`;
}

/**
 * Read an analysis job's detection count.
 *
 * Returns null when the field is absent, which keeps a job
 * whose count was not reported distinct from one that
 * reported a count of zero.
 *
 * @param {object|null|undefined} job
 * @returns {number|null}
 */
export function detectionCountOf(job) {
  const count = Number(job?.detection_count);

  return Number.isFinite(count) && job?.detection_count !== null &&
    job?.detection_count !== undefined
    ? count
    : null;
}

/**
 * Build the display strings for a job's metric tiles.
 *
 * Reads the fields the analysis API actually serves:
 * vegetation_change_percentage, detected_area_hectares,
 * mean_confidence_score and detection_count.
 *
 * @param {object|null|undefined} job
 */
export function analysisMetricDisplays(job) {
  const detectionCount = detectionCountOf(job);

  return {
    detectionCount,

    vegetationChangeDisplay: formatMeasurement(
      job?.vegetation_change_percentage,
      "%"
    ),

    // Zero detections is reported as the outcome it is,
    // rather than as an area that could not be measured.
    affectedAreaDisplay:
      detectionCount === 0
        ? NONE_DETECTED
        : formatMeasurement(job?.detected_area_hectares, " ha"),

    // The mean of the confidence indicators across this
    // job's detections. With no detections there is nothing
    // to average, which is not a confidence of zero.
    confidenceDisplay:
      detectionCount === 0
        ? NOT_APPLICABLE
        : formatMeasurement(job?.mean_confidence_score, "%"),
  };
}
