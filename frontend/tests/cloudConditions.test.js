import assert from "node:assert/strict";
import test from "node:test";

import {
  conditionPresentation,
  describeAge,
  describeSuitability,
  formatObservedAt,
  formatPercentage,
  gaugeGeometry,
  isReadingStale,
} from "../src/services/cloudConditions.js";

const NOW = new Date("2026-11-02T14:00:00Z");

// =========================================================
// THE GAUGE
//
// The failure these prevent: a gauge needs a number to
// draw, so a missing reading is under constant pressure to
// become a zero. A zero draws an empty arc beside the word
// "Clear", which is a confident statement nobody made.
// =========================================================

test("a reading draws a proportional arc", () => {
  const g = gaugeGeometry(50, 54);

  assert.equal(g.hasValue, true);
  assert.ok(Math.abs(g.dash - g.circumference / 2) < 0.001);
  assert.ok(Math.abs(g.gap - g.circumference / 2) < 0.001);
});

test("zero cloud is a real reading and draws no arc", () => {
  const g = gaugeGeometry(0);

  assert.equal(g.hasValue, true);
  assert.equal(g.dash, 0);
});

test("a missing reading is not a zero reading", () => {
  for (const absent of [null, undefined, NaN, "42"]) {
    const g = gaugeGeometry(absent);

    assert.equal(g.hasValue, false, String(absent));
    assert.equal(g.dash, 0);
  }
});

test("total overcast fills the circle", () => {
  const g = gaugeGeometry(100, 54);

  assert.ok(Math.abs(g.dash - g.circumference) < 0.001);
});

test("a figure outside the range is clamped for drawing only", () => {
  // Drawing cannot overflow the circle. The server has
  // already refused to classify such a figure, so this only
  // guards the geometry.
  assert.ok(gaugeGeometry(150).dash <= gaugeGeometry(100).circumference);
  assert.equal(gaugeGeometry(-10).dash, 0);
});

// =========================================================
// CONDITIONS
// =========================================================

test("each condition has a tone and an icon", () => {
  for (const condition of [
    "CLEAR",
    "PARTLY_CLOUDY",
    "CLOUDY",
    "VERY_CLOUDY",
    "UNKNOWN",
  ]) {
    const p = conditionPresentation(condition);

    assert.ok(p.tone, condition);
    assert.ok(p.icon, condition);
  }
});

test("a condition this page does not know is drawn as unknown", () => {
  // A newer server reporting a state added after this page
  // was written. Guessing it is harmless would be the same
  // error as defaulting a missing reading to zero.
  assert.equal(conditionPresentation("FOGGY").tone, "unknown");
  assert.equal(conditionPresentation(undefined).tone, "unknown");
});

// =========================================================
// PERCENTAGES
// =========================================================

test("a percentage is shown without false precision", () => {
  assert.equal(formatPercentage(42), "42%");
  assert.equal(formatPercentage(12.99), "13%");
  assert.equal(formatPercentage(12.5), "12.5%");
  assert.equal(formatPercentage(0), "0%");
});

test("a missing percentage shows a dash, never a zero", () => {
  assert.equal(formatPercentage(null), "—");
  assert.equal(formatPercentage(undefined), "—");
  assert.equal(formatPercentage(NaN), "—");
});

// =========================================================
// THE OBSERVATION TIMESTAMP
// =========================================================

test("the observation time is written out readably", () => {
  assert.equal(formatObservedAt("2026-11-02T14:00"), "14:00, 2 Nov 2026");
});

test("the observation time is not shifted by the viewer's timezone", () => {
  // The provider was asked for Africa/Lusaka and returns a
  // local wall-clock reading with no timezone suffix. Date
  // would read that as the viewer's own timezone and
  // relabel it on any machine not set to Zambia, so the
  // string is reformatted from its own parts instead.
  const original = process.env.TZ;

  try {
    for (const zone of ["America/New_York", "Asia/Tokyo", "UTC"]) {
      process.env.TZ = zone;

      assert.equal(
        formatObservedAt("2026-11-02T14:00"),
        "14:00, 2 Nov 2026",
        zone
      );
    }
  } finally {
    process.env.TZ = original;
  }
});

test("a missing or odd observation time does not break the card", () => {
  assert.equal(formatObservedAt(null), "—");
  assert.equal(formatObservedAt(""), "—");
  assert.equal(formatObservedAt("not a timestamp"), "not a timestamp");
});

// =========================================================
// AGE AND STALENESS
// =========================================================

test("age is reported in the largest sensible unit", () => {
  assert.equal(
    describeAge("2026-11-02T13:56:00Z", NOW),
    "4 minutes ago"
  );

  assert.equal(describeAge("2026-11-02T11:00:00Z", NOW), "3 hours ago");

  assert.equal(describeAge("2026-10-28T14:00:00Z", NOW), "5 days ago");
});

test("the singular is used for one", () => {
  assert.equal(describeAge("2026-11-02T13:59:00Z", NOW), "1 minute ago");
  assert.equal(describeAge("2026-11-02T13:00:00Z", NOW), "1 hour ago");
  assert.equal(describeAge("2026-11-01T14:00:00Z", NOW), "1 day ago");
});

test("under a minute reads as just now", () => {
  assert.equal(describeAge("2026-11-02T13:59:30Z", NOW), "just now");
});

test("a provider clock slightly ahead does not read as the future", () => {
  // Reporting "in 20 seconds" would look broken for what is
  // simply a small clock difference.
  assert.equal(describeAge("2026-11-02T14:00:20Z", NOW), "just now");
});

test("an absent or unreadable timestamp has no age", () => {
  assert.equal(describeAge(null, NOW), null);
  assert.equal(describeAge("", NOW), null);
  assert.equal(describeAge("not a date", NOW), null);
});

test("a reading past its interval is stale", () => {
  const fifteenMinutes = 15 * 60 * 1000;

  assert.equal(
    isReadingStale("2026-11-02T13:50:00Z", fifteenMinutes, NOW),
    false
  );

  assert.equal(
    isReadingStale("2026-11-02T13:30:00Z", fifteenMinutes, NOW),
    true
  );
});

test("nothing to date is not treated as stale", () => {
  assert.equal(isReadingStale(null, 1000, NOW), false);
  assert.equal(isReadingStale("rubbish", 1000, NOW), false);
});

// =========================================================
// SUITABILITY WORDING
//
// It must read as help in choosing an observation, never as
// a verdict about the forest. Cloud lowers NDVI and so does
// felling; the card separates those for a person and
// decides nothing itself.
// =========================================================

test("suitability is stated as a count against a threshold", () => {
  const line = describeSuitability({
    available: true,
    observation_count: 8,
    suitable_count: 6,
    suitability_threshold: 30,
  });

  assert.match(line, /6 of the last 8/);
  assert.match(line, /30%/);
  assert.match(line, /clear enough to analyse/);
});

test("no usable observation says so without implying a finding", () => {
  const line = describeSuitability({
    available: true,
    observation_count: 4,
    suitable_count: 0,
    suitability_threshold: 30,
  });

  assert.match(line, /None of the last 4/);
  assert.match(line, /measure NDVI from/);

  // Says nothing about deforestation either way.
  assert.doesNotMatch(line, /deforest|cleared|loss/i);
});

test("no imagery at all reports the server's reason", () => {
  const line = describeSuitability({
    available: false,
    unavailable_reason: "No Sentinel-2 imagery has been registered yet.",
  });

  assert.match(line, /No Sentinel-2 imagery/);
});

test("a missing satellite block does not throw", () => {
  assert.ok(describeSuitability(undefined).length > 0);
  assert.ok(describeSuitability({}).length > 0);
});
