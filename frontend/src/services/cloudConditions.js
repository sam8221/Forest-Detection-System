/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Cloud Conditions (presentation)
 *
 * Purpose:
 *   Turns the cloud monitoring response into the numbers and
 *   words the card draws.
 *
 * Responsibilities:
 *   - Geometry for the circular gauge.
 *   - Tone and icon for a condition.
 *   - How old a reading or an observation is, in words.
 *   - Whether a cached reading has gone stale.
 *
 * What this module will not do:
 *   It will not supply a percentage the server did not send.
 *   Every function accepts null and returns an absence, so a
 *   missing reading renders as "not available" rather than
 *   as a clear sky. The server is equally careful; this is
 *   the second half of the same rule, on the side where the
 *   temptation to default to zero is strongest because a
 *   gauge needs a number to draw.
 *
 * The classification itself is the server's. Repeating the
 * thresholds here would let the two drift and show an
 * officer a word that contradicts the figure beside it.
 * ===========================================================
 */

/**
 * Tone and icon for each condition the server can report.
 *
 * Tone drives colour. The label always accompanies it, so
 * the meaning never rests on hue alone: the card has to
 * stay readable in a monochrome dissertation figure and for
 * a reader who cannot distinguish the colours.
 */
const CONDITION_PRESENTATION = {
  CLEAR: { tone: "clear", icon: "sun" },
  PARTLY_CLOUDY: { tone: "partly", icon: "cloud-sun" },
  CLOUDY: { tone: "cloudy", icon: "cloud" },
  VERY_CLOUDY: { tone: "overcast", icon: "cloudy" },
  UNKNOWN: { tone: "unknown", icon: "cloud-off" },
};

/**
 * How a condition should be drawn.
 *
 * @param {string} condition The server's condition code.
 * @returns {{tone: string, icon: string}}
 *
 * An unrecognised code is drawn as unknown rather than
 * guessed at, for the same reason the server reports an
 * unrecognised state as a fault: a condition this page does
 * not understand is not evidence of a clear sky.
 */
export function conditionPresentation(condition) {
  return (
    CONDITION_PRESENTATION[condition] ||
    CONDITION_PRESENTATION.UNKNOWN
  );
}

/**
 * Geometry for the circular gauge.
 *
 * @param {number|null} percentage Cloud cover, 0 to 100.
 * @param {number} [radius] Circle radius in user units.
 * @returns {{circumference: number, dash: number, gap: number, hasValue: boolean}}
 *
 * Returns hasValue false and a zero-length arc when there
 * is no reading. The caller draws the track but no
 * progress, which is visibly different from a reading of
 * zero: that draws a full track with the needle at the
 * start and the words "Clear" beside it.
 */
export function gaugeGeometry(percentage, radius = 54) {
  const circumference = 2 * Math.PI * radius;

  const numeric =
    typeof percentage === "number" && Number.isFinite(percentage)
      ? Math.min(Math.max(percentage, 0), 100)
      : null;

  if (numeric === null) {
    return {
      circumference,
      dash: 0,
      gap: circumference,
      hasValue: false,
    };
  }

  const dash = (numeric / 100) * circumference;

  return {
    circumference,
    dash,
    gap: circumference - dash,
    hasValue: true,
  };
}

/**
 * A percentage as text.
 *
 * @param {number|null} percentage
 * @returns {string} e.g. "42%", or an em dash when absent.
 */
export function formatPercentage(percentage) {
  if (
    typeof percentage !== "number" ||
    !Number.isFinite(percentage)
  ) {
    return "—";
  }

  // Whole numbers for a weather reading, one decimal for a
  // catalogue figure that carries one. Cloud cover is not
  // measured finely enough to justify more.
  const rounded =
    Math.abs(percentage - Math.round(percentage)) < 0.05
      ? Math.round(percentage)
      : Math.round(percentage * 10) / 10;

  return `${rounded}%`;
}

const MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/**
 * The provider's observation timestamp, written out.
 *
 * @param {string|null} observedAt e.g. "2026-11-02T14:00".
 * @returns {string} e.g. "14:00, 2 Nov 2026", or an em dash.
 *
 * Reformatted from the string's own parts rather than
 * through a Date. The provider was asked for Africa/Lusaka
 * and returns a local wall-clock reading with no timezone
 * suffix, which Date would interpret as the *viewer's*
 * timezone and silently relabel on any machine not set to
 * Zambia. Splitting the string moves nothing.
 */
export function formatObservedAt(observedAt) {
  if (typeof observedAt !== "string" || !observedAt.includes("T")) {
    return observedAt || "—";
  }

  const [datePart, timePart] = observedAt.split("T");

  const [year, month, day] = datePart.split("-").map(Number);

  if (!year || !month || !day) {
    return observedAt;
  }

  const clock = (timePart || "").slice(0, 5);

  const monthName = MONTH_NAMES[month - 1] || month;

  return `${clock}, ${day} ${monthName} ${year}`;
}

/**
 * How long ago something was, in words.
 *
 * @param {string|null} isoString An ISO timestamp or date.
 * @param {Date} [now] The present moment, for testing.
 * @returns {string|null} e.g. "4 minutes ago", or null.
 *
 * Used for both the weather reading and an acquisition
 * date, because in both cases the age is what tells an
 * officer whether the figure still describes anything. A
 * cloud reading from this morning is history by afternoon.
 */
export function describeAge(isoString, now = new Date()) {
  if (!isoString) {
    return null;
  }

  const then = new Date(isoString);

  if (Number.isNaN(then.getTime())) {
    return null;
  }

  const seconds = Math.round((now.getTime() - then.getTime()) / 1000);

  // A provider's clock can be a little ahead of the
  // viewer's. Reporting "in 20 seconds" would look broken,
  // so anything within a minute either way reads as just now.
  if (seconds < 60) {
    return "just now";
  }

  const minutes = Math.round(seconds / 60);

  if (minutes < 60) {
    return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  }

  const hours = Math.round(minutes / 60);

  if (hours < 24) {
    return `${hours} hour${hours === 1 ? "" : "s"} ago`;
  }

  const days = Math.round(hours / 24);

  return `${days} day${days === 1 ? "" : "s"} ago`;
}

/**
 * Whether a reading has outlived its usefulness.
 *
 * @param {string|null} retrievedAt When it was fetched.
 * @param {number} maxAgeMs How long it stays current.
 * @param {Date} [now] The present moment, for testing.
 * @returns {boolean}
 *
 * A stale reading is still shown, labelled as stale. Hiding
 * it would leave an officer with nothing where they
 * previously had something, and "cloud cover as of an hour
 * ago" is worth more than a blank panel as long as the card
 * says that is what it is.
 */
export function isReadingStale(
  retrievedAt,
  maxAgeMs,
  now = new Date()
) {
  if (!retrievedAt) {
    return false;
  }

  const then = new Date(retrievedAt);

  if (Number.isNaN(then.getTime())) {
    return false;
  }

  return now.getTime() - then.getTime() > maxAgeMs;
}

/**
 * One line summarising how usable the recent imagery is.
 *
 * @param {object} satellite The satellite half of the response.
 * @returns {string}
 *
 * Phrased as a count against a threshold rather than as a
 * verdict. The card helps an officer choose an observation
 * to analyse; it does not decide for them, and it never
 * suggests that cloud cover says anything about whether an
 * area was cleared.
 */
export function describeSuitability(satellite) {
  if (!satellite?.available) {
    return (
      satellite?.unavailable_reason ||
      "No Sentinel-2 imagery has been registered for this district yet."
    );
  }

  const total = satellite.observation_count ?? 0;
  const suitable = satellite.suitable_count ?? 0;
  const threshold = satellite.suitability_threshold;

  if (total === 0) {
    return "No Sentinel-2 observations to compare.";
  }

  if (suitable === 0) {
    return (
      `None of the last ${total} observations are under ` +
      `${formatPercentage(threshold)} cloud, so none is clear ` +
      `enough to measure NDVI from yet.`
    );
  }

  return (
    `${suitable} of the last ${total} observations are under ` +
    `${formatPercentage(threshold)} cloud and clear enough to analyse.`
  );
}
