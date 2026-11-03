/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Measurement Summary (presentation)
 *
 * Purpose:
 *   Turns an analysis job's measurement_summary into rows
 *   the Analysis page can show beneath its results.
 *
 * Why this exists:
 *
 *   A run reported "Vegetation Change 0.00%" and "Potential
 *   Affected Area: None detected". Both were correct: the
 *   steepest NDVI decline anywhere in the scene was 0.286
 *   against a 0.30 threshold. But nothing on the page said
 *   a measurement had been taken, so a correct negative
 *   result was read as a broken system.
 *
 *   These rows are the evidence: how much ground was
 *   compared, what the NDVI change was, what passed the
 *   threshold, and which rule produced the outcome.
 *
 * What this module will not do:
 *   It will not fill a gap with a zero. A job that ran
 *   before the summary was recorded has none, and that is
 *   reported as "not recorded for this run" rather than as
 *   a measurement of nothing, for the same reason the rest
 *   of this page distinguishes a missing reading from a
 *   zero one.
 * ===========================================================
 */

/** Shown when a job carries no summary at all. */
export const NOT_RECORDED =
  "Measurement detail was not recorded for this run.";

/**
 * Whether a summary carries figures worth showing.
 *
 * @param {object|null|undefined} summary
 * @returns {boolean}
 */
export function hasMeasurement(summary) {
  return Boolean(summary) && summary.measured === true;
}

/**
 * A count with thousands separators, or a dash.
 *
 * @param {unknown} value
 * @returns {string}
 */
function count(value) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toLocaleString()
    : "—";
}

/**
 * A fixed-precision number, or a dash.
 *
 * @param {unknown} value
 * @param {number} decimals
 * @returns {string}
 */
function fixed(value, decimals = 2) {
  return typeof value === "number" && Number.isFinite(value)
    ? value.toFixed(decimals)
    : "—";
}

/**
 * A signed number, so greening reads as greening.
 *
 * @param {unknown} value
 * @param {number} decimals
 * @returns {string}
 *
 * The sign matters more here than anywhere else on the
 * page. A mean NDVI change of +0.03 says the vegetation
 * grew over the interval, which is the clearest possible
 * answer to "why did this find no deforestation".
 */
function signed(value, decimals = 3) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }

  return `${value > 0 ? "+" : ""}${value.toFixed(decimals)}`;
}

/**
 * The rows to display for a measurement.
 *
 * @param {object|null|undefined} summary job.measurement_summary
 * @returns {{status: string, detail: string|null, rows: Array<{label: string, value: string, note?: string}>}}
 *
 * status is "measured", "unmeasured" or "absent", so the
 * caller can tell a run that measured nothing from one that
 * could not measure at all from one that kept no record.
 * All three look like "0.00%" if they are not separated.
 */
export function describeMeasurement(summary) {
  if (!summary) {
    return { status: "absent", detail: NOT_RECORDED, rows: [] };
  }

  if (summary.measured !== true) {
    return {
      status: "unmeasured",
      detail:
        summary.reason ||
        "No pixel could be compared on both dates, so no change was measured.",
      rows: [
        {
          label: "Pixels compared",
          value: "0",
          note: "Nothing was usable on both dates",
        },
      ],
    };
  }

  const rows = [
    {
      label: "Ground compared",
      value: `${count(summary.measured_pixels)} px`,
      // "of the monitored area", not "of the scene". The
      // statistics are masked to the forest boundary, and a
      // Sentinel-2 raster is a bounding box around an
      // irregular outline, so a large share of the scene is
      // padding the analysis was never commissioned for.
      // Calling this a percentage of the scene understated
      // how much of the forest was actually observed.
      note:
        `${fixed(summary.measured_percentage, 1)}% of the monitored area` +
        (typeof summary.measured_hectares === "number"
          ? ` · ${fixed(summary.measured_hectares)} ha`
          : ""),
    },
    {
      label: "NDVI change",
      value: signed(summary.ndvi_change_mean),
      note:
        `mean · range ${signed(summary.ndvi_change_min)} to ` +
        `${signed(summary.ndvi_change_max)}`,
    },
    {
      label: "Steepest decline",
      value: fixed(summary.largest_decline, 3),
      note: `threshold ${fixed(summary.ndvi_threshold, 2)} NDVI`,
    },
    {
      label: "Pixels past threshold",
      value: count(summary.candidate_pixels),
      note:
        typeof summary.candidate_hectares === "number"
          ? `${fixed(summary.candidate_hectares)} ha in total`
          : undefined,
    },
    {
      label: "Largest candidate patch",
      value: `${fixed(summary.largest_candidate_hectares)} ha`,
      note: `minimum ${fixed(summary.minimum_area_hectares)} ha`,
    },
  ];

  return {
    status: "measured",
    detail: summary.outcome || null,
    rows,
  };
}

/**
 * Why nothing was reported, in one line.
 *
 * @param {object|null|undefined} summary
 * @returns {string|null}
 *
 * Taken from the server rather than rebuilt here, so the
 * same sentence reaches the screen, the log and the
 * dissertation. Rewording it on the client would let two
 * accounts of one run disagree.
 */
export function measurementOutcome(summary) {
  if (!summary) {
    return NOT_RECORDED;
  }

  return summary.outcome || summary.reason || null;
}
