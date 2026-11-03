import assert from "node:assert/strict";
import test from "node:test";

import {
  satelliteSignature,
  shouldReloadImagery,
} from "../src/services/dashboardUpdates.js";

const dashboard = ({
  total_images = 23,
  processed_images = 12,
  total_detections = 25,
  verified_detections = 9,
  rejected_detections = 0,
  sent_alerts = 4,
} = {}) => ({
  statistics: {
    satellite_images: {
      total_images,
      processed_images,
      unprocessed_images:
        total_images - processed_images,
    },
    detections: {
      total_detections,
      verified_detections,
      rejected_detections,
      pending_detections:
        total_detections -
        verified_detections -
        rejected_detections,
    },
    alerts: { sent_alerts },
    forests: { total_forests: 18 },
  },
});

test("an unchanged dashboard produces an unchanged signature", () => {
  assert.equal(
    satelliteSignature(dashboard()),
    satelliteSignature(dashboard())
  );
});

test("a newly downloaded satellite product changes the signature", () => {
  assert.notEqual(
    satelliteSignature(dashboard({ total_images: 23 })),
    satelliteSignature(dashboard({ total_images: 24 }))
  );
});

test("a product finishing processing changes the signature", () => {
  assert.notEqual(
    satelliteSignature(dashboard({ processed_images: 12 })),
    satelliteSignature(dashboard({ processed_images: 13 }))
  );
});

test("detections written by a completed analysis change the signature", () => {
  assert.notEqual(
    satelliteSignature(dashboard({ total_detections: 25 })),
    satelliteSignature(dashboard({ total_detections: 31 }))
  );
});

test("verifying or rejecting a detection changes the signature", () => {
  const before = satelliteSignature(dashboard());

  assert.notEqual(
    before,
    satelliteSignature(dashboard({ verified_detections: 10 }))
  );

  assert.notEqual(
    before,
    satelliteSignature(dashboard({ rejected_detections: 1 }))
  );
});

test("alert delivery alone does not reload the imagery", () => {
  // An alert being sent or read changes nothing drawn on the
  // map, so it must not trigger the expensive reload.
  assert.equal(
    satelliteSignature(dashboard({ sent_alerts: 4 })),
    satelliteSignature(dashboard({ sent_alerts: 9 }))
  );
});

test("a partial or empty response is read as zeroes rather than throwing", () => {
  // The refresh loop calls this on whatever the server
  // returned; a short reply must not break the loop.
  const empty = "0:0:0:0:0";

  assert.equal(satelliteSignature(undefined), empty);
  assert.equal(satelliteSignature(null), empty);
  assert.equal(satelliteSignature({}), empty);
  assert.equal(satelliteSignature({ statistics: {} }), empty);
  assert.equal(
    satelliteSignature({
      statistics: { satellite_images: {} },
    }),
    empty
  );
});

test("the first reading of a session does not reload the imagery", () => {
  // The page has already drawn the map and the scene by the
  // time the first comparison happens.
  const first = satelliteSignature(dashboard());

  assert.equal(shouldReloadImagery(null, first), false);
  assert.equal(shouldReloadImagery(undefined, first), false);
});

test("the imagery reloads only once the data has actually moved", () => {
  const before = satelliteSignature(dashboard());
  const after = satelliteSignature(
    dashboard({ total_images: 24 })
  );

  assert.equal(shouldReloadImagery(before, before), false);
  assert.equal(shouldReloadImagery(before, after), true);
});
