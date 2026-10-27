import assert from "node:assert/strict";
import test from "node:test";

import {
  applySynchronizedViewState,
  clampSwipePercent,
  COMPARISON_MODES,
  comparisonLayoutClass,
  formatComparisonMeanNdvi,
  findEligibleObservation,
  getEligibleObservations,
  getSelectedObservationCards,
  nextSwipePercent,
  SELECTED_COMPARISON_LAYERS,
  swipeClipPath,
  swipePercentFromPointer,
  validateObservationPair,
} from "../src/services/satelliteComparison.js";

function observation(id, date, overrides = {}) {
  return {
    id,
    forest_area_id: 5,
    acquisition_date: date,
    tile_id: "35KPV",
    processing_level: "L2A",
    is_downloaded: true,
    is_active: true,
    is_ready_for_analysis: true,
    ...overrides,
  };
}

test("selection uses the exact earlier and recent observations for this forest", () => {
  const images = [
    observation(10, "2024-05-10"),
    observation(20, "2025-05-12"),
  ];
  const pair = validateObservationPair(images, 5, "10", "20");
  assert.equal(pair.valid, true);
  assert.equal(pair.previous.acquisition_date, "2024-05-10");
  assert.equal(pair.recent.acquisition_date, "2025-05-12");
});

test("selection rejects incomplete, foreign-area, cross-tile, and non-L2A pairs", () => {
  const previous = observation(10, "2024-05-10");
  const recent = observation(20, "2025-05-12");
  assert.equal(validateObservationPair([previous], 5, 10, 20).valid, false);
  assert.equal(
    validateObservationPair(
      [previous, observation(20, "2025-05-12", { forest_area_id: 6 })],
      5,
      10,
      20
    ).valid,
    false
  );
  assert.equal(
    validateObservationPair(
      [previous, observation(20, "2025-05-12", { tile_id: "35KQV" })],
      5,
      10,
      20
    ).valid,
    false
  );
  assert.equal(
    validateObservationPair(
      [previous, observation(20, "2025-05-12", { processing_level: "L1C" })],
      5,
      10,
      20
    ).valid,
    false
  );
  assert.equal(validateObservationPair([previous, recent], 5, 10, 10).valid, false);
});

test("eligible observations are active downloaded L2A products for the selected forest", () => {
  const images = [
    observation(10, "2024-05-10"),
    observation(20, "2025-05-12", { is_downloaded: false }),
    observation(30, "2023-05-12", { forest_area_id: 6 }),
    observation(40, "2022-05-12", { is_active: false }),
    observation(50, "2021-05-12", { processing_level: "L1C" }),
  ];

  assert.deepEqual(
    getEligibleObservations(images, 5).map((image) => image.id),
    [10]
  );
  assert.equal(findEligibleObservation(images, 5, "10")?.id, 10);
  assert.equal(findEligibleObservation(images, 5, 20), null);
});

test("observation cards bind each role and metadata to the selected product ID", () => {
  const september = observation(47, "2026-09-17", {
    tile_id: "T35LPF",
    product_id: "S2A_SEPTEMBER",
    cloud_cover_percentage: 3.2,
  });
  const october = observation(46, "2026-10-18", {
    tile_id: "T35LPF",
    product_id: "S2C_OCTOBER",
    cloud_cover_percentage: 8.4,
  });
  const august = observation(45, "2026-08-17", {
    tile_id: "T35LPF",
    product_id: "S2A_AUGUST",
    cloud_cover_percentage: 1.7,
  });
  const november = observation(48, "2026-11-18", {
    tile_id: "T35LPF",
    product_id: "S2C_NOVEMBER",
    cloud_cover_percentage: 5.6,
  });

  const selected = getSelectedObservationCards(
    [october, september, august],
    5,
    47,
    46
  );
  assert.deepEqual(
    selected.map(({ role, label, image }) => ({
      role,
      label,
      id: image.id,
      date: image.acquisition_date,
      product: image.product_id,
      tile: image.tile_id,
      cloud: image.cloud_cover_percentage,
      downloaded: image.is_downloaded,
    })),
    [
      {
        role: "previous",
        label: "Previous observation",
        id: 47,
        date: "2026-09-17",
        product: "S2A_SEPTEMBER",
        tile: "T35LPF",
        cloud: 3.2,
        downloaded: true,
      },
      {
        role: "recent",
        label: "Recent observation",
        id: 46,
        date: "2026-10-18",
        product: "S2C_OCTOBER",
        tile: "T35LPF",
        cloud: 8.4,
        downloaded: true,
      },
    ]
  );

  const changedSelections = getSelectedObservationCards(
    [october, september, august],
    5,
    45,
    46
  );
  assert.equal(changedSelections[0].label, "Previous observation");
  assert.equal(changedSelections[0].image.product_id, "S2A_AUGUST");
  assert.equal(changedSelections[1].label, "Recent observation");
  assert.equal(changedSelections[1].image.product_id, "S2C_OCTOBER");

  const changedRecentSelection = getSelectedObservationCards(
    [november, october, september, august],
    5,
    45,
    48
  );
  assert.equal(changedRecentSelection[0].label, "Previous observation");
  assert.equal(changedRecentSelection[0].image.product_id, "S2A_AUGUST");
  assert.equal(changedRecentSelection[1].label, "Recent observation");
  assert.equal(changedRecentSelection[1].image.product_id, "S2C_NOVEMBER");
});

test("observation selections reject reversed acquisition dates", () => {
  const september = observation(47, "2026-09-17", { tile_id: "T35LPF" });
  const october = observation(46, "2026-10-18", { tile_id: "T35LPF" });

  const pair = validateObservationPair([september, october], 5, 46, 47);
  assert.equal(pair.valid, false);
  assert.match(pair.error, /previous observation must be earlier/);
});

test("swipe mode clamps the draggable reveal to the image extent", () => {
  assert.deepEqual(COMPARISON_MODES, {
    SWIPE: "swipe",
    SIDE_BY_SIDE: "side-by-side",
  });
  assert.equal(clampSwipePercent(-5), 0);
  assert.equal(clampSwipePercent(45), 45);
  assert.equal(clampSwipePercent(108), 100);
  assert.equal(clampSwipePercent("not-a-number"), 50);
  assert.equal(swipeClipPath(35), "inset(0 65% 0 0)");
  assert.equal(comparisonLayoutClass(COMPARISON_MODES.SWIPE), "satellite-comparison-swipe");
  assert.equal(comparisonLayoutClass("unknown"), "satellite-comparison-swipe");
});

test("side-by-side mode selects the two-panel synchronized map layout", () => {
  assert.equal(
    comparisonLayoutClass(COMPARISON_MODES.SIDE_BY_SIDE),
    "satellite-comparison-side-by-side"
  );
});

test("side-by-side view synchronization copies pan, zoom, and rotation", () => {
  const source = {
    center: [2750000, -1600000],
    resolution: 9.5,
    rotation: 0.25,
  };
  const target = { center: null, resolution: null, rotation: null };
  target.setCenter = (value) => { target.center = value; };
  target.setResolution = (value) => { target.resolution = value; };
  target.setRotation = (value) => { target.rotation = value; };

  applySynchronizedViewState(source, target);
  assert.deepEqual(target.center, source.center);
  assert.equal(target.resolution, source.resolution);
  assert.equal(target.rotation, source.rotation);
  assert.notEqual(target.center, source.center);
});

test("completed comparison defaults to its explicit selected-pair NDVI change layer", () => {
  assert.equal(SELECTED_COMPARISON_LAYERS.NDVI_DIFFERENCE, "selected_ndvi_difference");
  assert.equal(SELECTED_COMPARISON_LAYERS.PERSISTENCE_CANDIDATES, "confirmed_loss");
});

test("comparison mean metrics display real values and leave missing values unavailable", () => {
  assert.equal(formatComparisonMeanNdvi(-0.1256), "-0.126");
  assert.equal(formatComparisonMeanNdvi(0.4), "0.400");
  assert.equal(formatComparisonMeanNdvi(null), "Unavailable");
  assert.equal(formatComparisonMeanNdvi("not-a-number"), "Unavailable");
});

// ---------------------------------------------------------
// Swipe divider
//
// The divider used to be a transparent range input lying
// across the vertical middle of the map, with its track
// inset by 3rem while the clip path and the visible line were
// positioned against the full width. The line and the pointer
// therefore drifted apart towards either edge, and the seam
// could not be grabbed anywhere except at mid-height.
//
// The position is now computed from the pointer against the
// same box the clip path measures. These pin that, so the
// line cannot come apart from the clip edge again.
// ---------------------------------------------------------

test("the reveal position follows the pointer across the clipped box", () => {
  const rect = { left: 100, width: 400 };

  assert.equal(swipePercentFromPointer(100, rect), 0);
  assert.equal(swipePercentFromPointer(200, rect), 25);
  assert.equal(swipePercentFromPointer(300, rect), 50);
  assert.equal(swipePercentFromPointer(500, rect), 100);
});

test("the divider and the clip edge stay on the same position", () => {
  // Whatever the pointer reports, the percentage driving the
  // divider's "left" is the same number the clip path uses,
  // so the two cannot separate.
  const rect = { left: 64, width: 913 };

  for (const clientX of [64, 200, 517, 800, 977]) {
    const percent = swipePercentFromPointer(clientX, rect);

    assert.equal(swipeClipPath(percent), `inset(0 ${100 - percent}% 0 0)`);
  }
});

test("a pointer beyond either edge is held at the edge", () => {
  const rect = { left: 100, width: 400 };

  assert.equal(swipePercentFromPointer(-500, rect), 0);
  assert.equal(swipePercentFromPointer(99, rect), 0);
  assert.equal(swipePercentFromPointer(5000, rect), 100);
});

test("an unmeasured swipe area moves nothing rather than jumping", () => {
  // Before layout, or while the panel is hidden, the
  // rectangle has no width. Dividing by it would give NaN,
  // which clamps to 50 and would snap the divider to the
  // centre mid-drag.
  for (const rect of [null, undefined, {}, { left: 0, width: 0 }]) {
    assert.equal(swipePercentFromPointer(300, rect), null);
  }

  assert.equal(swipePercentFromPointer(NaN, { left: 0, width: 400 }), null);
});

test("arrow keys step the divider and Home and End reach the edges", () => {
  assert.equal(nextSwipePercent(50, "ArrowRight"), 52);
  assert.equal(nextSwipePercent(50, "ArrowLeft"), 48);
  assert.equal(nextSwipePercent(50, "ArrowRight", true), 60);
  assert.equal(nextSwipePercent(50, "ArrowLeft", true), 40);
  assert.equal(nextSwipePercent(50, "PageUp"), 60);
  assert.equal(nextSwipePercent(50, "PageDown"), 40);
  assert.equal(nextSwipePercent(50, "Home"), 0);
  assert.equal(nextSwipePercent(50, "End"), 100);
});

test("keyboard stepping stops at the edges instead of wrapping", () => {
  assert.equal(nextSwipePercent(1, "ArrowLeft"), 0);
  assert.equal(nextSwipePercent(0, "ArrowLeft"), 0);
  assert.equal(nextSwipePercent(99, "ArrowRight"), 100);
  assert.equal(nextSwipePercent(100, "ArrowRight"), 100);
});

test("keys the divider does not act on are left to the browser", () => {
  // Returning null is what stops the handler calling
  // preventDefault, so Tab still moves focus off the divider.
  for (const key of ["Tab", "Enter", " ", "a", "Escape", "F5"]) {
    assert.equal(nextSwipePercent(50, key), null);
  }
});
