import assert from "node:assert/strict";
import test from "node:test";

import {
  ZAMBIA_TIME_ZONE,
  formatZambiaDate,
  formatZambiaShortTime,
  formatZambiaTime,
  zambiaNow,
} from "../src/services/zambiaTime.js";

// 12:00:00 UTC. Zambia is UTC+2 with no daylight saving,
// so this is 14:00:00 in Lusaka on any date of the year.
const MIDDAY_UTC = new Date("2026-11-01T12:00:00Z");

test("the clock reads Zambian time, not UTC", () => {
  assert.equal(formatZambiaTime(MIDDAY_UTC), "14:00:00");
});

test("the clock is the same whatever the computer is set to", () => {
  // The failure this prevents: an officer reading a capture
  // time or an alert time shifted by their laptop's
  // timezone, with nothing on the page saying so.
  const sameInstant = new Date(MIDDAY_UTC.getTime());

  assert.equal(formatZambiaTime(sameInstant), "14:00:00");

  assert.equal(ZAMBIA_TIME_ZONE, "Africa/Lusaka");
});

test("the clock is 24-hour, so 07:00 and 19:00 are distinct", () => {
  const morning = new Date("2026-11-01T05:00:00Z");
  const evening = new Date("2026-11-01T17:00:00Z");

  assert.equal(formatZambiaTime(morning), "07:00:00");
  assert.equal(formatZambiaTime(evening), "19:00:00");
});

test("hours, minutes and seconds are always two digits", () => {
  const earlyHours = new Date("2026-11-01T01:02:03Z");

  // 03:02:03 in Lusaka. Padding keeps the digits from
  // shifting sideways as the clock ticks.
  assert.equal(formatZambiaTime(earlyHours), "03:02:03");
});

test("seconds advance", () => {
  const before = new Date("2026-11-01T12:00:00Z");
  const after = new Date("2026-11-01T12:00:01Z");

  assert.equal(formatZambiaTime(before), "14:00:00");
  assert.equal(formatZambiaTime(after), "14:00:01");
});

test("the date carries the weekday, day, month and year", () => {
  const written = formatZambiaDate(MIDDAY_UTC);

  assert.match(written, /Sunday/);
  assert.match(written, /\b1\b/);
  assert.match(written, /November/);
  assert.match(written, /2026/);
});

test("late evening UTC is already the next day in Zambia", () => {
  // 23:30 UTC on the 1st is 01:30 on the 2nd in Lusaka.
  // A date taken from UTC would show the wrong day here.
  const lateUtc = new Date("2026-11-01T23:30:00Z");

  assert.equal(formatZambiaTime(lateUtc), "01:30:00");
  assert.match(formatZambiaDate(lateUtc), /Monday/);
  assert.match(formatZambiaDate(lateUtc), /2 November/);
});

test("the offset does not move across the year", () => {
  // Central Africa Time has no daylight saving. Both of
  // these are UTC+2, where a European zone would differ.
  const january = new Date("2026-01-15T12:00:00Z");
  const july = new Date("2026-07-15T12:00:00Z");

  assert.equal(formatZambiaTime(january), "14:00:00");
  assert.equal(formatZambiaTime(july), "14:00:00");
});

test("zambiaNow returns both parts and a machine-readable instant", () => {
  const now = zambiaNow(MIDDAY_UTC);

  assert.equal(now.time, "14:00:00");
  assert.match(now.date, /Sunday/);

  // The absolute instant, not the Zambian wall-clock
  // reading: that is what a <time dateTime> carries.
  assert.equal(now.iso, "2026-11-01T12:00:00.000Z");
});

test("the output carries no invisible formatting characters", () => {
  // Some runtimes insert direction marks, which are
  // invisible but break a layout and a comparison.
  const written = formatZambiaTime(MIDDAY_UTC) + formatZambiaDate(MIDDAY_UTC);

  assert.doesNotMatch(written, /[‎‏‪-‮]/);
});

test("a stated time drops the seconds but keeps the timezone", () => {
  // "Updated 14:00" on the dashboard. Seconds are noise for
  // a reading stated once, but the zone still has to be
  // Zambia's: a panel reporting its refresh in the
  // browser's timezone, beside a header reporting Zambia's,
  // would show two different times for the same moment.
  assert.equal(formatZambiaShortTime(MIDDAY_UTC), "14:00");
});

test("a stated time is 24-hour and zero-padded", () => {
  assert.equal(
    formatZambiaShortTime(new Date("2026-11-01T01:02:00Z")),
    "03:02"
  );

  assert.equal(
    formatZambiaShortTime(new Date("2026-11-01T17:00:00Z")),
    "19:00"
  );
});

test("called with no argument it uses the present moment", () => {
  assert.match(formatZambiaTime(), /^\d{2}:\d{2}:\d{2}$/);

  assert.ok(formatZambiaDate().length > 0);
});
