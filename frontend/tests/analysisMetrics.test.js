import assert from "node:assert/strict";
import test from "node:test";

import {
  NOT_APPLICABLE,
  NOT_AVAILABLE,
  analysisMetricDisplays,
  formatMeasurement,
  formatNumber,
} from "../src/services/analysisMetrics.js";

function summary(overrides = {}) {
  return {
    measured: true,
    measured_pixels: 100,
    ndvi_change_mean: 0.031,
    ndvi_threshold: 0.3,
    decline_pixels: 20,
    increase_pixels: 30,
    decline_hectares: 0.2,
    candidate_pixels: 0,
    candidate_hectares: 0,
    largest_candidate_hectares: 0,
    minimum_area_hectares: 0.5,
    significant_change_percentage: 0,
    significant_decline_percentage: 0,
    significant_increase_percentage: 0,
    little_change_percentage: 100,
    ...overrides,
  };
}

test("missing values stay unavailable while a real zero remains measurable", () => {
  for (const value of [null, undefined, "", "not a number", NaN, Infinity]) {
    assert.equal(formatNumber(value), null);
  }
  assert.equal(formatNumber(0), "0.00");
  assert.equal(formatMeasurement(null, "%"), NOT_AVAILABLE);
  assert.equal(formatMeasurement(0, "%"), "0.00%");
});

test("sub-threshold vegetation decline is reported from raster pixels", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: summary({
      ndvi_change_mean: -0.021,
      decline_pixels: 12,
      candidate_pixels: 0,
      decline_hectares: 0.12,
      candidate_hectares: 0,
      significant_change_percentage: 0,
    }),
    detection_count: 0,
    confirmed_detection_count: 0,
  });

  assert.equal(result.vegetationChangeDisplay, "0.00%");
  assert.match(result.vegetationChangeDetail, /Mean ΔNDVI -0.021/);
  assert.match(result.vegetationChangeDetail, /little\/no significant change 100.00%/);
  assert.equal(result.potentialAreaDisplay, "0.12 ha");
  assert.match(
    result.potentialAreaDetail,
    /past the .*detection threshold: 0.00 ha/
  );
  assert.equal(result.detectionStatusDisplay, "Completed · Vegetation decline observed · below NDVI threshold");
  assert.equal(result.confidenceDisplay, NOT_APPLICABLE);
});

test("threshold-exceeding decline is potential area, not confirmed deforestation", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: summary({
      decline_pixels: 55,
      candidate_pixels: 55,
      candidate_hectares: 0.55,
      decline_hectares: 0.55,
      largest_candidate_hectares: 0.55,
      significant_decline_percentage: 55,
      significant_change_percentage: 55,
      little_change_percentage: 45,
    }),
    detection_count: 0,
    confirmed_detection_count: 0,
    confirmed_detected_area_hectares: null,
  });

  assert.equal(result.vegetationChangeDisplay, "55.00%");
  assert.equal(result.potentialAreaDisplay, "0.55 ha");
  assert.equal(result.confirmedAreaDisplay, "0.00 ha");
  assert.match(result.detectionStatusDisplay, /Potential deforestation detected/);
  assert.match(result.detectionStatusDisplay, /not confirmed by persistence/);
});

test("vegetation increase is kept positive and distinguished from decline", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: summary({
      ndvi_change_mean: 0.12,
      decline_pixels: 0,
      increase_pixels: 40,
      decline_hectares: 0,
      significant_increase_percentage: 40,
      significant_change_percentage: 40,
      little_change_percentage: 60,
    }),
    detection_count: 0,
    confirmed_detection_count: 0,
  });

  assert.equal(result.vegetationChangeDisplay, "40.00%");
  assert.match(result.vegetationChangeDetail, /Mean ΔNDVI \+0.120/);
  assert.match(result.vegetationChangeDetail, /increase 40.00%/);
  assert.equal(result.detectionStatusDisplay, "Completed · Vegetation increase observed");
});

test("little or no significant change is separated from absent measurements", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: summary({
      ndvi_change_mean: 0,
      decline_pixels: 0,
      increase_pixels: 0,
      decline_hectares: 0,
      little_change_percentage: 100,
    }),
    detection_count: 0,
    confirmed_detection_count: 0,
  });

  assert.equal(result.vegetationChangeDisplay, "0.00%");
  assert.equal(result.potentialAreaDisplay, "0.00 ha");
  assert.equal(result.detectionStatusDisplay, "Completed · No qualifying detection");
});

test("an analysis with no valid pixels keeps raster metrics unavailable and record totals separate", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: {
      measured: false,
      reason: "No common valid pixels.",
    },
    detection_count: 0,
    confirmed_detection_count: 0,
  });

  assert.equal(result.vegetationChangeDisplay, NOT_AVAILABLE);
  assert.equal(result.potentialAreaDisplay, NOT_AVAILABLE);
  assert.equal(result.confirmedAreaDisplay, "0.00 ha");
  assert.equal(result.detectionStatusDisplay, "Completed · No valid data");
  assert.equal(result.confidenceDisplay, NOT_APPLICABLE);
});

test("confidence is shown only for a valid detection confidence score", () => {
  const base = {
    status: "COMPLETED",
    measurement_summary: summary(),
    detection_count: 1,
    confirmed_detection_count: 0,
  };
  assert.equal(
    analysisMetricDisplays({ ...base, mean_confidence_score: 89.42 }).confidenceDisplay,
    "89.42%"
  );
  assert.equal(
    analysisMetricDisplays({ ...base, mean_confidence_score: 104 }).confidenceDisplay,
    NOT_AVAILABLE
  );
  assert.equal(
    analysisMetricDisplays({ ...base, mean_confidence_score: null }).confidenceDisplay,
    NOT_AVAILABLE
  );
  assert.equal(
    analysisMetricDisplays({
      ...base,
      detection_count: 0,
      mean_confidence_score: 89.42,
    }).confidenceDisplay,
    NOT_APPLICABLE
  );
});

test("a completed job without a raster summary never falls back to detection-only vegetation percent", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    vegetation_change_percentage: 86.96,
    detection_count: 1,
    detected_area_hectares: 0.98,
    mean_confidence_score: 94.78,
  });

  assert.equal(result.vegetationChangeDisplay, NOT_AVAILABLE);
  assert.equal(result.potentialAreaDisplay, NOT_AVAILABLE);
  assert.equal(result.confirmedAreaDisplay, NOT_AVAILABLE);
  assert.equal(result.confidenceDisplay, "94.78%");
});

test("older raster summaries retain their measured NDVI mean without inventing a percentage", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: {
      measured: true,
      measured_pixels: 227836,
      ndvi_change_min: -0.2863,
      ndvi_change_max: 0.3337,
      ndvi_change_mean: 0.031,
      largest_decline: 0.2863,
      candidate_pixels: 0,
      candidate_hectares: 0,
      largest_candidate_hectares: 0,
      ndvi_threshold: 0.3,
      minimum_area_hectares: 0.5,
    },
    detection_count: 0,
    confirmed_detection_count: 0,
  });

  assert.equal(result.vegetationChangeDisplay, "+0.031 NDVI");
  assert.match(result.vegetationChangeDetail, /percentage breakdown was not recorded/);
  assert.equal(result.potentialAreaDisplay, NOT_AVAILABLE);
  assert.match(
    result.potentialAreaDetail,
    /past the .*detection threshold: 0.00 ha/
  );
  assert.equal(result.detectionStatusDisplay, "Completed · Vegetation decline observed · below NDVI threshold");
});

test("missing detection totals do not become a no-detection conclusion", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: summary(),
  });

  assert.equal(result.confirmedAreaDisplay, NOT_AVAILABLE);
  assert.equal(result.detectionStatusDisplay, "Completed · Detection status unavailable");
});

test("detections awaiting review are not labelled as confirmed", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: summary(),
    detection_count: 2,
    confirmed_detection_count: 0,
    pending_detection_count: 2,
    rejected_detection_count: 0,
  });

  assert.match(result.detectionStatusDisplay, /Potential deforestation detected/);
  assert.match(result.detectionStatusDisplay, /awaiting review/);
});

test("officer-confirmed area and status come from verified records", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: summary(),
    detection_count: 1,
    confirmed_detection_count: 1,
    confirmed_detected_area_hectares: 0.75,
    pending_detection_count: 0,
    rejected_detection_count: 0,
    mean_confidence_score: 91.2,
  });

  assert.equal(result.confirmedAreaDisplay, "0.75 ha");
  assert.equal(result.detectionStatusDisplay, "Completed · Confirmed detection");
  assert.equal(result.confidenceDisplay, "91.20%");
});

test("confirmed records remain visible when an older job has no raster summary", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    detection_count: 1,
    confirmed_detection_count: 1,
    confirmed_detected_area_hectares: 0.75,
    pending_detection_count: 0,
    rejected_detection_count: 0,
  });

  assert.equal(result.detectionStatusDisplay, "Completed · Confirmed detection");
  assert.equal(result.confirmedAreaDisplay, "0.75 ha");
  assert.equal(result.potentialAreaDisplay, NOT_AVAILABLE);
});

test("officer-rejected candidates are not left in the awaiting-review state", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: summary(),
    detection_count: 1,
    confirmed_detection_count: 0,
    pending_detection_count: 0,
    rejected_detection_count: 1,
  });

  assert.equal(result.detectionStatusDisplay, "Completed · Candidate rejected by officer");
});

// =========================================================
// THE FIVE SCENARIOS
//
// The cards used to measure "did this change" against the
// detection threshold, a 0.30 NDVI swing that means most of
// a canopy has gone. Almost nothing in a real scene reaches
// it, so a forest whose difference map showed red and green
// across the frame reported 0.00% changed and 99.99%
// unchanged. These five cases pin each outcome to what the
// imagery actually contained.
// =========================================================

/** A summary measured against the 0.05 change criterion. */
function measured(overrides = {}) {
  return summary({
    significant_change_threshold: 0.05,
    significant_decline_hectares: 0,
    ...overrides,
  });
}

test("scenario 1: decline below the detection threshold is still reported", () => {
  // The real Kitwe run. 1.99% of the area declined by at
  // least 0.05 NDVI; nothing reached 0.30, so there is no
  // detection. The card must show the decline, not 0.00%.
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: measured({
      ndvi_change_mean: 0.031,
      significant_decline_percentage: 1.99,
      significant_increase_percentage: 25.59,
      little_change_percentage: 72.42,
      significant_change_percentage: 27.58,
      significant_decline_hectares: 45.29,
      decline_hectares: 800.0,
      candidate_pixels: 0,
      candidate_hectares: 0,
    }),
    detection_count: 0,
    confirmed_detection_count: 0,
  });

  assert.equal(result.vegetationChangeDisplay, "27.58%");
  assert.match(result.vegetationChangeDetail, /Decline 1.99%/);
  assert.match(result.vegetationChangeDetail, /increase 25.59%/);

  // The affected area is the significant decline, not the
  // 800 ha of any-downward-movement including noise.
  assert.equal(result.potentialAreaDisplay, "45.29 ha");
  assert.match(result.potentialAreaDetail, /at least 0.05 NDVI/);

  assert.equal(result.confidenceDisplay, NOT_APPLICABLE);
});

test("scenario 2: decline exceeding the threshold reaches detection", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: measured({
      ndvi_change_mean: -0.18,
      significant_decline_percentage: 31.0,
      significant_increase_percentage: 1.0,
      little_change_percentage: 68.0,
      significant_change_percentage: 32.0,
      significant_decline_hectares: 62.0,
      candidate_pixels: 820,
      candidate_hectares: 8.2,
      largest_candidate_hectares: 3.4,
    }),
    detection_count: 2,
    confirmed_detection_count: 2,
    confirmed_detected_area_hectares: 3.9,
    mean_confidence_score: 88.4,
  });

  assert.equal(result.vegetationChangeDisplay, "32.00%");
  assert.equal(result.potentialAreaDisplay, "62.00 ha");

  // Confirmed detections are reported separately and never
  // conflated with the potential decline area.
  assert.equal(result.confirmedAreaDisplay, "3.90 ha");
  assert.equal(result.confidenceDisplay, "88.40%");
});

test("scenario 3: vegetation increase is not reported as decline", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: measured({
      ndvi_change_mean: 0.12,
      significant_decline_percentage: 0.4,
      significant_increase_percentage: 61.2,
      little_change_percentage: 38.4,
      significant_change_percentage: 61.6,
      significant_decline_hectares: 2.1,
      candidate_pixels: 0,
      candidate_hectares: 0,
    }),
    detection_count: 0,
    confirmed_detection_count: 0,
  });

  assert.match(result.vegetationChangeDetail, /Mean ΔNDVI \+0.12/);
  assert.match(result.vegetationChangeDetail, /increase 61.20%/);

  // A greener forest reports a small decline area, not a
  // large one, and no detection.
  assert.equal(result.potentialAreaDisplay, "2.10 ha");
  assert.equal(result.confidenceDisplay, NOT_APPLICABLE);
});

test("scenario 4: little change reports little change", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: measured({
      ndvi_change_mean: 0.004,
      significant_decline_percentage: 0.1,
      significant_increase_percentage: 0.2,
      little_change_percentage: 99.7,
      significant_change_percentage: 0.3,
      significant_decline_hectares: 0.5,
      candidate_pixels: 0,
      candidate_hectares: 0,
    }),
    detection_count: 0,
    confirmed_detection_count: 0,
  });

  assert.equal(result.vegetationChangeDisplay, "0.30%");
  assert.match(result.vegetationChangeDetail, /little\/no significant change 99.70%/);
  assert.equal(result.potentialAreaDisplay, "0.50 ha");
});

test("scenario 5: no valid data reports no measurement, not zero", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: {
      measured: false,
      reason:
        "No pixel carried a usable NDVI value on both dates, so no change could be measured.",
      measured_pixels: 0,
      ndvi_threshold: 0.3,
      significant_change_threshold: 0.05,
      significant_change_percentage: null,
      significant_decline_percentage: null,
      significant_increase_percentage: null,
      little_change_percentage: null,
      decline_hectares: null,
      significant_decline_hectares: null,
    },
    detection_count: 0,
    confirmed_detection_count: 0,
  });

  // Nothing was measured, so nothing is asserted as a
  // measurement. A zero here would read as a quiet forest.
  assert.equal(result.vegetationChangeDisplay, NOT_AVAILABLE);
  assert.equal(result.potentialAreaDisplay, NOT_AVAILABLE);
  assert.equal(result.confidenceDisplay, NOT_APPLICABLE);
});

test("the tooltip names both thresholds and separates them", () => {
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: measured({ significant_change_percentage: 27.58 }),
    detection_count: 0,
  });

  assert.match(result.vegetationChangeTitle, /0.05/);
  assert.match(result.vegetationChangeTitle, /0.30/);
  assert.match(result.vegetationChangeTitle, /separate/);

  // Says plainly that the figure describes rather than
  // detects, and that it includes greening.
  assert.match(result.vegetationChangeTitle, /does not\s+detect/);
  assert.match(result.vegetationChangeTitle, /greening/);
});

test("a job recorded before the criteria were separated still states its own", () => {
  // No significant_change_threshold stored. It falls back to
  // the detection threshold, which is what that job was
  // actually measured against, rather than claiming a
  // criterion it never used.
  const result = analysisMetricDisplays({
    status: "COMPLETED",
    measurement_summary: summary({ significant_change_percentage: 0 }),
    detection_count: 0,
  });

  assert.match(result.vegetationChangeDetail, /\|ΔNDVI\| ≥ 0.30/);
});
