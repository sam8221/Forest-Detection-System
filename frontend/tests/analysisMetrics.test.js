import assert from "node:assert/strict";
import test from "node:test";

import {
  NONE_DETECTED,
  NOT_APPLICABLE,
  NOT_AVAILABLE,
  analysisMetricDisplays,
  detectionCountOf,
  formatMeasurement,
  formatNumber,
} from "../src/services/analysisMetrics.js";

// ---------------------------------------------------------
// The rule these tests exist for
//
// A metric the backend did not report must never be shown as
// a measurement of zero. formatNumber used to return "0.00"
// for a missing value, and the Analysis page read the
// affected area and the confidence from response fields the
// analysis API has never sent, so every completed analysis
// displayed 0.00 ha at 0.00% confidence however much
// clearing it had found.
// ---------------------------------------------------------

test("a missing number is not formatted as zero", () => {
  for (const missing of [null, undefined, "", "not a number", NaN, Infinity]) {
    assert.equal(
      formatNumber(missing),
      null,
      `${String(missing)} should have no formatted value`
    );
  }
});

test("a real number is formatted, including a genuine zero", () => {
  assert.equal(formatNumber(0), "0.00");
  assert.equal(formatNumber(0.98), "0.98");
  assert.equal(formatNumber(86.955, 1), "87.0");
  assert.equal(formatNumber("4.540487"), "4.54");
});

test("a unit is attached only to a reading that exists", () => {
  assert.equal(formatMeasurement(0.98, " ha"), "0.98 ha");
  assert.equal(formatMeasurement(4.54, "%"), "4.54%");

  // Never "Not available%".
  assert.equal(formatMeasurement(null, "%"), NOT_AVAILABLE);
  assert.equal(formatMeasurement(undefined, " ha"), NOT_AVAILABLE);
});

test("a reported count of zero is distinct from no count at all", () => {
  assert.equal(detectionCountOf({ detection_count: 0 }), 0);
  assert.equal(detectionCountOf({ detection_count: 16 }), 16);
  assert.equal(detectionCountOf({}), null);
  assert.equal(detectionCountOf({ detection_count: null }), null);
  assert.equal(detectionCountOf(null), null);
});

// ---------------------------------------------------------
// The three states a completed analysis can be in
// ---------------------------------------------------------

test("an analysis that found clearing reports its measured figures", () => {
  const displays = analysisMetricDisplays({
    status: "COMPLETED",
    vegetation_change_percentage: 86.96,
    detection_count: 1,
    detected_area_hectares: 0.98,
    mean_confidence_score: 94.78,
  });

  assert.equal(displays.detectionCount, 1);
  assert.equal(displays.vegetationChangeDisplay, "86.96%");
  assert.equal(displays.affectedAreaDisplay, "0.98 ha");
  assert.equal(displays.confidenceDisplay, "94.78%");
});

test("an analysis that found nothing says so rather than showing an unknown", () => {
  // The real shape of a zero-detection job: the backend sends
  // a count of zero and no area, because there is no area to
  // report.
  const displays = analysisMetricDisplays({
    status: "COMPLETED",
    vegetation_change_percentage: 0.0,
    detection_count: 0,
    detected_area_hectares: null,
    mean_confidence_score: null,
  });

  assert.equal(displays.detectionCount, 0);

  // A measured vegetation change of zero is a real reading.
  assert.equal(displays.vegetationChangeDisplay, "0.00%");

  // Not "0.00 ha", which would read as a measured area, and
  // not "Not available", which would suggest a fault.
  assert.equal(displays.affectedAreaDisplay, NONE_DETECTED);

  // With no detections there is nothing to be confident
  // about, which is not a confidence of zero.
  assert.equal(displays.confidenceDisplay, NOT_APPLICABLE);
});

test("metrics the response omits are reported as unavailable, never as zero", () => {
  const displays = analysisMetricDisplays({ status: "COMPLETED" });

  assert.equal(displays.detectionCount, null);
  assert.equal(displays.vegetationChangeDisplay, NOT_AVAILABLE);
  assert.equal(displays.affectedAreaDisplay, NOT_AVAILABLE);
  assert.equal(displays.confidenceDisplay, NOT_AVAILABLE);

  // The regression in one line: none of these is a zero.
  for (const shown of Object.values(displays)) {
    assert.ok(
      !String(shown).startsWith("0.00"),
      `an omitted metric must not display as ${shown}`
    );
  }
});

test("a job that has not run yet shows no metrics", () => {
  for (const job of [null, undefined, { status: "PENDING" }]) {
    const displays = analysisMetricDisplays(job);

    assert.equal(displays.vegetationChangeDisplay, NOT_AVAILABLE);
    assert.equal(displays.affectedAreaDisplay, NOT_AVAILABLE);
    assert.equal(displays.confidenceDisplay, NOT_AVAILABLE);
  }
});

test("the stale response fields that caused the defect are not read", () => {
  // If any of these were still consulted, the displays below
  // would carry their values instead of reporting that the
  // real fields are absent.
  const displays = analysisMetricDisplays({
    status: "COMPLETED",
    loss_area_hectares: 12.5,
    deforestation_area_hectares: 12.5,
    deforested_area_hectares: 12.5,
    confidence_percentage: 77,
    confidence: 77,
  });

  assert.equal(displays.affectedAreaDisplay, NOT_AVAILABLE);
  assert.equal(displays.confidenceDisplay, NOT_AVAILABLE);
});

// ---------------------------------------------------------
// Call sites that moved onto formatMeasurement
//
// Extracting these helpers out of Analysis.jsx left one call
// site still naming the removed local formatNumber, which is
// a ReferenceError the bundler does not report and no test
// covered - it crashed the job detail panel at render. These
// pin the formatting those call sites now rely on.
// ---------------------------------------------------------

test("a job duration formats to one decimal with its unit", () => {
  assert.equal(formatMeasurement(6.764595, " seconds", 1), "6.8 seconds");
  assert.equal(formatMeasurement(15.519683, " seconds", 1), "15.5 seconds");
});

test("cloud cover and NDVI threshold format without inventing zeros", () => {
  assert.equal(formatMeasurement(4.540487, "%"), "4.54%");
  assert.equal(formatMeasurement(0.3), "0.30");

  // A catalogue row with no cloud figure, and a job with no
  // threshold recorded, must not read as 0.
  assert.equal(formatMeasurement(null, "%", 1), NOT_AVAILABLE);
  assert.equal(formatMeasurement(undefined), NOT_AVAILABLE);
});
