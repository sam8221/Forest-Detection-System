import assert from "node:assert/strict";
import test from "node:test";

import {
  NOT_RECORDED,
  describeMeasurement,
  hasMeasurement,
  measurementOutcome,
} from "../src/services/measurementSummary.js";

// The real run that was reported as a fault: 227,836 pixels
// compared, steepest decline 0.286, threshold 0.30.
const QUIET_RUN = {
  measured: true,
  reason: null,
  total_pixels: 308856,
  measured_pixels: 227836,
  measured_percentage: 73.77,
  measured_hectares: 2278.36,
  ndvi_change_min: -0.2863,
  ndvi_change_max: 0.3337,
  ndvi_change_mean: 0.031,
  largest_decline: 0.2863,
  candidate_pixels: 0,
  candidate_hectares: 0,
  largest_candidate_hectares: 0,
  ndvi_threshold: 0.3,
  minimum_area_hectares: 0.5,
  outcome:
    "No pixel declined by the 0.30 NDVI required. The steepest decline measured anywhere in the monitored area was 0.286.",
};

// The run that found 42 candidate pixels and suppressed them.
const SUPPRESSED_RUN = {
  ...QUIET_RUN,
  candidate_pixels: 42,
  candidate_hectares: 0.42,
  largest_candidate_hectares: 0.25,
  largest_decline: 0.3767,
  ndvi_change_mean: 0.0682,
  outcome:
    "42 pixels declined past the 0.30 NDVI threshold, but the largest connected group covers 0.25 ha, below the 0.50 ha minimum, so none was reported as a clearing.",
};

// =========================================================
// THE THREE STATES
//
// A run that measured and found nothing, a run that could
// not measure, and a run with no record all render as
// "0.00%" if they are not kept apart. That confusion is
// what made a correct result look broken.
// =========================================================

test("a run that measured and found nothing is marked measured", () => {
  const described = describeMeasurement(QUIET_RUN);

  assert.equal(described.status, "measured");
  assert.ok(described.rows.length >= 5);
});

test("a run with no comparable pixel is unmeasured, not zero", () => {
  const described = describeMeasurement({
    measured: false,
    reason:
      "No pixel carried a usable NDVI value on both dates, so no change could be measured.",
  });

  assert.equal(described.status, "unmeasured");
  assert.match(described.detail, /no change could be measured/);
});

test("a run with no record says so rather than showing zeros", () => {
  for (const absent of [null, undefined]) {
    const described = describeMeasurement(absent);

    assert.equal(described.status, "absent");
    assert.equal(described.detail, NOT_RECORDED);
    assert.deepEqual(described.rows, []);
  }
});

test("hasMeasurement is true only for a real measurement", () => {
  assert.equal(hasMeasurement(QUIET_RUN), true);
  assert.equal(hasMeasurement({ measured: false }), false);
  assert.equal(hasMeasurement(null), false);
});

// =========================================================
// THE EVIDENCE
// =========================================================

test("the quiet run shows how much ground it compared", () => {
  const rows = describeMeasurement(QUIET_RUN).rows;

  const ground = rows.find((r) => r.label === "Ground compared");

  assert.match(ground.value, /227,836 px/);
  // "of the monitored area", not "of the scene": the
  // statistics are masked to the forest boundary, and a
  // Sentinel-2 raster is a bounding box around an irregular
  // outline, so much of the scene is padding outside it.
  assert.match(ground.note, /73\.8% of the monitored area/);
  assert.match(ground.note, /2278\.36 ha/);
});

test("the steepest decline is shown against the threshold", () => {
  // The single most useful figure for a run that found
  // nothing: 0.286 against 0.30 is a near miss, 0.01 is a
  // quiet forest, and the officer acts differently on each.
  const rows = describeMeasurement(QUIET_RUN).rows;

  const decline = rows.find((r) => r.label === "Steepest decline");

  assert.equal(decline.value, "0.286");
  assert.match(decline.note, /threshold 0\.30/);
});

test("greening is shown with its sign", () => {
  // +0.031 says the vegetation grew over the interval,
  // which answers "why did this find no deforestation"
  // more directly than any other figure on the page.
  const rows = describeMeasurement(QUIET_RUN).rows;

  const change = rows.find((r) => r.label === "NDVI change");

  assert.equal(change.value, "+0.031");
  assert.match(change.note, /-0\.286 to \+0\.334/);
});

test("a suppressed candidate is shown against the minimum area", () => {
  const rows = describeMeasurement(SUPPRESSED_RUN).rows;

  const candidates = rows.find(
    (r) => r.label === "Pixels past threshold"
  );

  assert.equal(candidates.value, "42");

  const patch = rows.find(
    (r) => r.label === "Largest candidate patch"
  );

  assert.equal(patch.value, "0.25 ha");
  assert.match(patch.note, /minimum 0\.50 ha/);
});

test("the server's own outcome sentence is shown, not a rebuilt one", () => {
  // One account of one run. Rewording it here would let the
  // screen, the log and the dissertation disagree.
  assert.equal(
    describeMeasurement(SUPPRESSED_RUN).detail,
    SUPPRESSED_RUN.outcome
  );

  assert.equal(measurementOutcome(QUIET_RUN), QUIET_RUN.outcome);
});

test("an outcome falls back to the unmeasured reason", () => {
  assert.match(
    measurementOutcome({ measured: false, reason: "cloud-covered" }),
    /cloud-covered/
  );

  assert.equal(measurementOutcome(null), NOT_RECORDED);
});

test("missing figures render as a dash, never as a zero", () => {
  const rows = describeMeasurement({ measured: true }).rows;

  for (const row of rows) {
    assert.doesNotMatch(
      row.value,
      /^0(\.0+)?( px| ha)?$/,
      `${row.label} rendered a bare zero for a missing figure`
    );
  }
});
