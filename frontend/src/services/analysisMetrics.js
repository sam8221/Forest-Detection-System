/**
 * Display rules for measurements from one analysis job.
 *
 * Raster change statistics come from measurement_summary, which is
 * computed from that job's previous/recent NDVI pair. Detection
 * records remain a separate result: they have passed the detection
 * pipeline and may still be awaiting officer verification.
 */

export const NOT_AVAILABLE = "Not available";
export const NOT_APPLICABLE = "Not applicable";

export function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(decimals) : null;
}

export function formatMeasurement(value, unit = "", decimals = 2) {
  const formatted = formatNumber(value, decimals);
  return formatted === null ? NOT_AVAILABLE : `${formatted}${unit}`;
}

function finite(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function detectionCountOf(job) {
  return finite(job?.detection_count);
}

function percentageText(value) {
  return formatMeasurement(value, "%");
}

function signed(value, decimals = 3) {
  const number = finite(value);
  if (number === null) return NOT_AVAILABLE;
  return `${number > 0 ? "+" : ""}${number.toFixed(decimals)}`;
}

function measuredSummary(job) {
  const summary = job?.measurement_summary;
  return summary?.measured === true ? summary : null;
}

function detectionStatus(
  job,
  summary,
  detectionCount,
  confirmedCount,
  pendingCount,
  rejectedCount
) {
  const status = String(job?.status || "").toUpperCase();
  if (status !== "COMPLETED") {
    if (status === "PENDING") return "Analysis pending";
    if (status === "RUNNING") return "Analysis running";
    if (status === "FAILED") return "Analysis failed";
    return "Not started";
  }

  if (confirmedCount !== null && confirmedCount > 0) {
    return "Completed · Confirmed detection";
  }
  if (pendingCount !== null && pendingCount > 0) {
    return "Completed · Potential deforestation detected · awaiting review";
  }
  if (rejectedCount !== null && rejectedCount > 0) {
    return "Completed · Candidate rejected by officer";
  }
  if (
    detectionCount !== null && detectionCount > 0 &&
    (confirmedCount === null || pendingCount === null || rejectedCount === null)
  ) {
    return "Completed · Detection status unavailable";
  }
  if (!summary) {
    return job?.measurement_summary
      ? "Completed · No valid data"
      : "Completed · Measurements not recorded";
  }
  if (
    detectionCount === null || confirmedCount === null ||
    pendingCount === null || rejectedCount === null
  ) {
    return "Completed · Detection status unavailable";
  }

  const candidatePixels = finite(summary.candidate_pixels) ?? 0;
  const largestPatch = finite(summary.largest_candidate_hectares);
  const minimumArea = finite(summary.minimum_area_hectares);
  if (candidatePixels > 0) {
    if (
      largestPatch !== null && minimumArea !== null &&
      largestPatch >= minimumArea
    ) {
      return "Completed · Potential deforestation detected · not confirmed by persistence";
    }
    return "Completed · Vegetation decline observed · below minimum area";
  }

  if (
    (finite(summary.decline_pixels) ?? 0) > 0 ||
    (finite(summary.ndvi_change_min) ?? 0) < 0
  ) {
    return "Completed · Vegetation decline observed · below NDVI threshold";
  }
  if (
    (finite(summary.increase_pixels) ?? 0) > 0 ||
    (finite(summary.ndvi_change_max) ?? 0) > 0
  ) {
    return "Completed · Vegetation increase observed";
  }
  return "Completed · No qualifying detection";
}

/**
 * Build the values and explanations displayed by the Analysis cards.
 *
 * Vegetation change is the percentage of comparable pixels whose
 * absolute NDVI difference meets the job's recorded threshold. The
 * directional shares use that same denominator and threshold. The
 * potential area is the area of pixels meeting the decline threshold,
 * before persistence and minimum-patch filtering.
 */
export function analysisMetricDisplays(job) {
  const summary = measuredSummary(job);
  const detectionCount = detectionCountOf(job);
  const noDetectionRecords = detectionCount === 0;
  const confirmedCount =
    finite(job?.confirmed_detection_count) ?? (noDetectionRecords ? 0 : null);
  const pendingCount =
    finite(job?.pending_detection_count) ?? (noDetectionRecords ? 0 : null);
  const rejectedCount =
    finite(job?.rejected_detection_count) ?? (noDetectionRecords ? 0 : null);

  const significantChange = summary
    ? finite(summary.significant_change_percentage)
    : null;
  const declineShare = summary
    ? finite(summary.significant_decline_percentage)
    : null;
  const increaseShare = summary
    ? finite(summary.significant_increase_percentage)
    : null;
  const littleChangeShare = summary
    ? finite(summary.little_change_percentage)
    : null;
  // The criterion for calling a pixel changed, which is NOT
  // the detection threshold. A 0.30 NDVI swing is most of a
  // canopy; measuring "did this change" against it reported
  // a scene as 0.00% declined and 99.99% unchanged while its
  // difference map showed red and green across the frame.
  //
  // Falls back to the detection threshold only for a job
  // recorded before the two were separated, so a historical
  // run still states the criterion it was actually measured
  // against rather than one it never used.
  const changeCriterion = summary
    ? finite(summary.significant_change_threshold) ??
      finite(summary.ndvi_threshold)
    : null;
  const detectionThreshold = summary ? finite(summary.ndvi_threshold) : null;
  const meanChange = summary ? finite(summary.ndvi_change_mean) : null;

  const changeBreakdown =
    declineShare !== null && increaseShare !== null && littleChangeShare !== null
      ? `Decline ${percentageText(declineShare)} · increase ${percentageText(increaseShare)} · little/no significant change ${percentageText(littleChangeShare)}`
      : "Directional percentage breakdown was not recorded for this job.";
  const meanChangeText = meanChange === null
    ? "Mean ΔNDVI was not recorded"
    : `Mean ΔNDVI ${signed(meanChange)}`;
  const vegetationChangeDetail = summary
    ? `${meanChangeText} · ${changeBreakdown}` +
      (changeCriterion === null
        ? ""
        : ` · significant means |ΔNDVI| ≥ ${changeCriterion.toFixed(2)}`)
    : "No valid paired-pixel measurement is available.";
  const vegetationChangeTitle = significantChange !== null
    ? "Share of comparable pixels whose recent-minus-previous NDVI moved by at least " +
      `${changeCriterion === null ? "the recorded" : changeCriterion.toFixed(2)}` +
      " in either direction. That criterion is the smallest change" +
      " distinguishable from sensor and atmospheric noise, and is" +
      " deliberately separate from the " +
      `${detectionThreshold === null ? "" : `${detectionThreshold.toFixed(2)} `}` +
      "NDVI decline a pixel must show to become a deforestation" +
      " candidate. This figure describes the imagery; it does not" +
      " detect, and includes greening as well as decline."
    : meanChange !== null
      ? "Mean recent-minus-previous NDVI change recorded for this job. Pixel-share percentages were not stored for this historical analysis."
      : "No valid paired-pixel measurement is available.";
  const vegetationChangeValue = significantChange !== null
    ? percentageText(significantChange)
    : meanChange !== null
      ? `${signed(meanChange)} NDVI`
      : NOT_AVAILABLE;

  // Area of decline large enough to be real, not of every
  // pixel that moved downward.
  //
  // Sign alone is the wrong criterion for an area: half of a
  // perfectly quiet scene drifts downward by a hundredth of
  // an NDVI unit, so "any measured decline" reported
  // hundreds of hectares of "potential affected area" for a
  // forest where nothing had happened. A figure that large
  // and that wrong is worse than none.
  //
  // Older jobs stored no significant-decline area. They fall
  // back to the all-decline figure and say which they are
  // showing, rather than silently presenting one as the
  // other.
  const significantDeclineArea = summary
    ? finite(summary.significant_decline_hectares)
    : null;
  const anyDeclineArea = summary ? finite(summary.decline_hectares) : null;

  const potentialArea =
    significantDeclineArea !== null
      ? formatMeasurement(significantDeclineArea, " ha")
      : anyDeclineArea !== null
        ? formatMeasurement(anyDeclineArea, " ha")
        : NOT_AVAILABLE;

  const thresholdArea = summary
    ? formatMeasurement(summary.candidate_hectares, " ha")
    : NOT_AVAILABLE;

  const potentialAreaDetail = !summary
    ? "No valid paired-pixel measurement is available."
    : significantDeclineArea !== null
      ? `Decline of at least ${
          changeCriterion === null ? "the recorded criterion" : changeCriterion.toFixed(2)
        } NDVI · past the ${
          detectionThreshold === null ? "detection" : detectionThreshold.toFixed(2)
        } detection threshold: ${thresholdArea}`
      : anyDeclineArea !== null
        ? `Any measured decline (ΔNDVI < 0), including noise · past the detection threshold: ${thresholdArea}`
        : `Area of measured decline was not recorded · past the detection threshold: ${thresholdArea}`;
  const confirmedAreaValue = finite(job?.confirmed_detected_area_hectares);
  const confirmedArea =
    confirmedCount === null
      ? NOT_AVAILABLE
      : confirmedCount === 0
        ? "0.00 ha"
        : formatMeasurement(confirmedAreaValue, " ha");

  const confidence = finite(job?.mean_confidence_score);
  const confidenceDisplay =
    detectionCount === 0
      ? NOT_APPLICABLE
      : confidence !== null && confidence >= 0 && confidence <= 100
        ? `${confidence.toFixed(2)}%`
        : NOT_AVAILABLE;

  return {
    detectionCount,
    vegetationChangeDisplay: vegetationChangeValue,
    vegetationChangeDetail,
    vegetationChangeTitle,
    potentialAreaDisplay: potentialArea,
    potentialAreaDetail,
    confirmedAreaDisplay: confirmedArea,
    detectionStatusDisplay: detectionStatus(
      job,
      summary,
      detectionCount,
      confirmedCount,
      pendingCount,
      rejectedCount
    ),
    confidenceDisplay,
  };
}
