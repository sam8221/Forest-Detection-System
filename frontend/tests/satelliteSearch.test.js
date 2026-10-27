import assert from "node:assert/strict";
import test from "node:test";

import {
  initialSatelliteSearchState,
  satelliteSearchReducer,
} from "../src/services/satelliteSearch.js";

test("failed retries retain prior products and a successful retry clears the error", () => {
  const originalProducts = [
    { product_id: "product-1" },
    { product_id: "product-2" },
  ];
  const originalCriteria = {
    forestAreaId: "12",
    startDate: "2026-10-04",
    endDate: "2026-10-19",
    cloudCover: 30,
  };

  const afterFirstSuccess = satelliteSearchReducer(
    initialSatelliteSearchState,
    {
      type: "success",
      products: originalProducts,
      criteria: originalCriteria,
    }
  );
  const afterFailure = satelliteSearchReducer(afterFirstSuccess, {
    type: "failure",
    message: "Copernicus is temporarily unavailable.",
  });

  assert.equal(afterFailure.searching, false);
  assert.equal(afterFailure.error, "Copernicus is temporarily unavailable.");
  assert.deepEqual(afterFailure.products, originalProducts);
  assert.equal(afterFailure.lastSuccessfulSearch, originalCriteria);

  const retrying = satelliteSearchReducer(afterFailure, { type: "start" });
  assert.equal(retrying.error, "");
  assert.equal(retrying.searching, true);
  assert.deepEqual(retrying.products, originalProducts);

  const latestProducts = [{ product_id: "latest-product" }];
  const afterRetry = satelliteSearchReducer(retrying, {
    type: "success",
    products: latestProducts,
    criteria: { ...originalCriteria, startDate: "2026-10-10" },
  });

  assert.equal(afterRetry.error, "");
  assert.equal(afterRetry.searching, false);
  assert.deepEqual(afterRetry.products, latestProducts);
  assert.equal(afterRetry.lastSuccessfulSearch.startDate, "2026-10-10");
});

test("date validation failures are represented as user-facing search errors", () => {
  const invalid = satelliteSearchReducer(initialSatelliteSearchState, {
    type: "failure",
    message: "Start date cannot be later than end date.",
  });

  assert.equal(invalid.error, "Start date cannot be later than end date.");
  assert.equal(invalid.searching, false);
  assert.deepEqual(invalid.products, []);
});
