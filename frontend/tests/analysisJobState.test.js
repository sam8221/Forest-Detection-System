import assert from "node:assert/strict";
import test from "node:test";

import {
  canDisplayAnalysisResults,
  comparisonFigureUrls,
  isConfirmedActiveAnalysisJob,
  isTerminalAnalysisJob,
  restoreSelectedPair,
  selectRestorableAnalysisJob,
} from "../src/services/analysisJobState.js";

const observation = (id, acquisition_date) => ({
  id,
  forest_area_id: 9,
  acquisition_date,
  is_active: true,
  is_downloaded: true,
  is_ready_for_analysis: true,
  processing_level: "L2A",
  tile_id: "35KPV",
});

test("initial load with no jobs has no restored or running analysis", () => {
  assert.equal(selectRestorableAnalysisJob([], 9), null);
  assert.equal(isConfirmedActiveAnalysisJob(null), false);
});

test("refresh restores a queued or running job only when the backend confirms its worker", () => {
  const queued = { id: 12, forest_area_id: 9, status: "PENDING", worker_available: true };
  const running = { ...queued, id: 13, status: "RUNNING" };
  assert.equal(isConfirmedActiveAnalysisJob(queued), true);
  assert.equal(isConfirmedActiveAnalysisJob(running), true);
  assert.equal(selectRestorableAnalysisJob([queued], 9).id, 12);
});

test("a stale pending job without an available worker is not restored as active", () => {
  const stale = { id: 14, forest_area_id: 9, status: "PENDING", worker_available: false };
  assert.equal(isConfirmedActiveAnalysisJob(stale), false);
  assert.equal(selectRestorableAnalysisJob([stale], 9), null);
});

test("completed results require both execution timestamps and backend output verification", () => {
  const complete = {
    status: "COMPLETED",
    started_at: "2026-10-22T10:00:00Z",
    completed_at: "2026-10-22T10:02:00Z",
    results_verified: true,
  };
  assert.equal(canDisplayAnalysisResults(complete), true);
  assert.equal(canDisplayAnalysisResults({ ...complete, results_verified: false }), false);
  assert.equal(canDisplayAnalysisResults({ ...complete, started_at: null }), false);
});

test("failed jobs are terminal and do not keep polling or disable retry", () => {
  const failed = { id: 15, status: "FAILED", worker_available: true };
  assert.equal(isTerminalAnalysisJob(failed), true);
  assert.equal(isConfirmedActiveAnalysisJob(failed), false);
});

test("the newest confirmed active job wins over older completed history", () => {
  const completed = {
    id: 10,
    forest_area_id: 9,
    status: "COMPLETED",
    created_at: "2026-10-20T10:00:00Z",
  };
  const active = {
    id: 11,
    forest_area_id: 9,
    status: "RUNNING",
    worker_available: true,
    created_at: "2026-10-22T10:00:00Z",
  };
  assert.equal(selectRestorableAnalysisJob([completed, active], 9).id, 11);
});

test("selected observation IDs restore from the exact job only when still eligible", () => {
  const observations = [
    observation(47, "2025-06-10T00:00:00Z"),
    observation(46, "2026-06-10T00:00:00Z"),
  ];
  const restored = restoreSelectedPair(
    { previous_satellite_image_id: 47, satellite_image_id: 46 },
    observations,
    9
  );
  assert.deepEqual(restored, { previousImageId: "47", recentImageId: "46" });
  assert.equal(
    restoreSelectedPair(
      { previous_satellite_image_id: 47, satellite_image_id: 999 },
      observations,
      9
    ),
    null
  );
});

test("the comparison figure and panels are scoped to the completed job ID", () => {
  const urls = comparisonFigureUrls("/api/v1", 9, 78);
  assert.equal(urls.figure, "/api/v1/monitoring/9/comparison/78/figure.png");
  assert.equal(urls.panels.previous_rgb, "/api/v1/monitoring/9/comparison/78/panel/previous_rgb.png");
  assert.equal(urls.panels.ndvi_difference, "/api/v1/monitoring/9/comparison/78/panel/ndvi_difference.png");
});
