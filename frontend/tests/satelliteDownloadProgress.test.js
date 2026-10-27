import assert from "node:assert/strict";
import test from "node:test";

import {
  getDownloadStatusErrorMessage,
  getSatelliteDownloadButtonState,
  isDownloadStatusErrorPermanent,
  isSatelliteDownloadActive,
  mergeSatelliteDownloadJobs,
  shouldRetryDownloadStatusError,
} from "../src/services/satelliteDownloadProgress.js";

test("explains a stale FastAPI route instead of displaying its validation object", () => {
  assert.equal(
    getDownloadStatusErrorMessage(422, {
      detail: [
        {
          loc: ["path", "image_id"],
          msg: "Input should be a valid integer",
        },
      ],
    }),
    "This FastAPI instance does not expose the satellite download-status route. " +
      "Restart the backend from the current ForestWatch project to enable download progress."
  );
});

test("keeps real download-status endpoint errors readable", () => {
  assert.equal(
    getDownloadStatusErrorMessage(404, {
      detail: "Forest area not found.",
    }),
    "Forest area not found."
  );
});

test("explains local ForestWatch authentication failures without blaming Copernicus", () => {
  assert.equal(
    getDownloadStatusErrorMessage(401, {
      detail: "Could not validate credentials.",
    }),
    "ForestWatch could not authenticate this request. Sign in again, then check the download status."
  );
});

test("does not retry permanent status failures but retries network and server errors", () => {
  assert.equal(shouldRetryDownloadStatusError({ status: 401 }), false);
  assert.equal(shouldRetryDownloadStatusError({ status: 403 }), false);
  assert.equal(shouldRetryDownloadStatusError({ status: 422 }), false);
  assert.equal(shouldRetryDownloadStatusError({ status: 429 }), true);
  assert.equal(shouldRetryDownloadStatusError({ status: 503 }), true);
  assert.equal(shouldRetryDownloadStatusError(new TypeError("Failed to fetch")), true);
  assert.equal(shouldRetryDownloadStatusError({ name: "AbortError" }), false);
});

test("button labels use measured backend percentages and allow unknown totals", () => {
  assert.equal(
    getSatelliteDownloadButtonState({
      status: "DOWNLOADING",
      progress_percentage: 25.8,
    }).label,
    "Downloading 25%"
  );
  assert.equal(
    getSatelliteDownloadButtonState({
      status: "DOWNLOADING",
      progress_percentage: null,
    }).label,
    "Downloading..."
  );
  assert.equal(
    getSatelliteDownloadButtonState({
      status: "DOWNLOADING",
      progress_percentage: 100,
    }).label,
    "Downloading 99%"
  );
});

test("active acquisition disables only that product and prevents repeated clicks", () => {
  const active = {
    product_id: "product-a",
    status: "DOWNLOADING",
    progress_percentage: 50,
  };
  const activeState = getSatelliteDownloadButtonState(active);
  const unrelatedState = getSatelliteDownloadButtonState(undefined);

  assert.equal(isSatelliteDownloadActive(active.status), true);
  assert.equal(activeState.disabled, true);
  assert.equal(activeState.label, "Downloading 50%");
  assert.equal(unrelatedState.disabled, false);
  assert.equal(unrelatedState.label, "Acquire");
});

test("blocks new acquisition while the backend cannot report download status", () => {
  const activeState = getSatelliteDownloadButtonState(
    { status: "PREPARING" },
    false,
    true
  );
  const untrackedState = getSatelliteDownloadButtonState(
    undefined,
    false,
    true
  );

  assert.equal(activeState.label, "Status unavailable");
  assert.equal(activeState.disabled, true);
  assert.equal(activeState.active, false);
  assert.equal(untrackedState.label, "Status unavailable");
  assert.equal(untrackedState.disabled, true);
});

test("progress from one product never appears on another product", () => {
  const jobs = mergeSatelliteDownloadJobs({}, [
    {
      product_id: "product-a",
      status: "DOWNLOADING",
      progress_percentage: 75,
    },
  ]);

  assert.equal(
    getSatelliteDownloadButtonState(jobs["product-a"]).label,
    "Downloading 75%"
  );
  assert.equal(
    getSatelliteDownloadButtonState(jobs["product-b"]).label,
    "Acquire"
  );
});

test("restored jobs reflect completed and failed status after refresh", () => {
  const restored = mergeSatelliteDownloadJobs({}, [
    { product_id: "product-done", status: "COMPLETED" },
    {
      product_id: "product-failed",
      status: "FAILED",
      error_message: "The product did not validate.",
    },
  ]);

  assert.equal(
    getSatelliteDownloadButtonState(restored["product-done"]).label,
    "Acquired"
  );
  const failed = getSatelliteDownloadButtonState(restored["product-failed"]);
  assert.equal(failed.label, "Retry Download");
  assert.equal(failed.error, "The product did not validate.");
  assert.equal(failed.disabled, false);
});

test("an unapplied download-job migration is permanent, an outage is not", () => {
  // Wording comes from _raise_if_download_job_table_missing in
  // app/api/satellite_images.py; test_satellite_download_progress.py
  // pins the backend half of this contract.
  const migrationDetail =
    "Satellite download tracking is unavailable because its database " +
    "migration has not been applied. Apply the pending Alembic migrations " +
    "from the backend directory.";

  assert.equal(
    isDownloadStatusErrorPermanent(503, { detail: migrationDetail }),
    true
  );
  assert.equal(
    isDownloadStatusErrorPermanent(503, {
      detail: "Service temporarily unavailable.",
    }),
    false
  );
  assert.equal(isDownloadStatusErrorPermanent(401, {}), true);
  assert.equal(isDownloadStatusErrorPermanent(403, {}), true);
  assert.equal(isDownloadStatusErrorPermanent(422, {}), true);
  assert.equal(isDownloadStatusErrorPermanent(500, {}), false);
  assert.equal(isDownloadStatusErrorPermanent(429, {}), false);

  // The migration message must survive to the officer unchanged: it is the
  // only thing on the page that says which command to run.
  assert.equal(
    getDownloadStatusErrorMessage(503, { detail: migrationDetail }),
    migrationDetail
  );
});

test("polling stops for a permanent failure the status code alone cannot classify", () => {
  const migrationError = Object.assign(new Error("migration not applied"), {
    status: 503,
    permanent: true,
  });
  const outage = Object.assign(new Error("gateway down"), {
    status: 503,
    permanent: false,
  });

  assert.equal(shouldRetryDownloadStatusError(migrationError), false);
  assert.equal(shouldRetryDownloadStatusError(outage), true);
});
