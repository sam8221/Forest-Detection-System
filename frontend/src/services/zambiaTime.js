/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Zambian Local Time
 *
 * Purpose:
 *   Formats an instant as the date and time in Zambia,
 *   whatever the viewing computer is set to.
 *
 * Why the timezone is fixed rather than taken from the
 * browser:
 *
 *   An officer reads a time on this screen and acts on it:
 *   when a scene was captured, when an alert was raised,
 *   when a field visit was planned for. Those are all
 *   events in the Copperbelt. A laptop whose clock was left
 *   on another timezone, or a browser reached from outside
 *   Zambia, would render every one of them shifted, and
 *   nothing on the page would say so.
 *
 *   So the zone is named, not inferred.
 *
 * Note on Africa/Lusaka:
 *   Central Africa Time, UTC+2, with no daylight saving.
 *   The offset is therefore constant, but the zone is still
 *   named rather than hard-coded as +02:00, because a fixed
 *   offset would be a claim this module has no business
 *   making on behalf of the tz database.
 * ===========================================================
 */

/** The one timezone this system reports times in. */
export const ZAMBIA_TIME_ZONE = "Africa/Lusaka";

/**
 * The locale used for the clock and date.
 *
 * Fixed rather than taken from the browser so that every
 * officer reads the same wording, and so a screenshot in
 * the dissertation shows what the system displays rather
 * than what one machine happened to be configured for.
 */
const LOCALE = "en-GB";

/**
 * Formatter for the digital clock: hours, minutes, seconds.
 *
 * hourCycle is stated explicitly. Without it the locale
 * decides, and a locale that chooses a 12-hour clock would
 * drop the distinction between 07:00 and 19:00 unless the
 * meridiem were shown as well.
 *
 * Built once. Constructing an Intl.DateTimeFormat is not
 * free and this is read once a second for as long as the
 * page is open.
 */
const timeFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: ZAMBIA_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

/** Formatter for the full date: weekday, day, month, year. */
const dateFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: ZAMBIA_TIME_ZONE,
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

/**
 * Formatter for a time without seconds.
 *
 * For readings that are not a ticking clock: when a panel
 * last refreshed, when a job finished. Seconds there are
 * noise.
 */
const shortTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  timeZone: ZAMBIA_TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/**
 * The time in Zambia, as HH:MM:SS.
 *
 * @param {Date} [instant] The moment to render. Defaults to now.
 * @returns {string} e.g. "14:07:52"
 *
 * Some runtimes insert a narrow no-break space or a
 * left-to-right mark into formatted output. Those are
 * invisible, but they break a string comparison in a test
 * and can upset a monospaced layout, so the separators are
 * normalised to plain colons.
 */
export function formatZambiaTime(instant = new Date()) {
  return timeFormatter
    .format(instant)
    .replace(/[‎‏‪-‮]/g, "")
    .trim();
}

/**
 * The date in Zambia, written out in full.
 *
 * @param {Date} [instant] The moment to render. Defaults to now.
 * @returns {string} e.g. "Saturday 1 November 2026"
 */
export function formatZambiaDate(instant = new Date()) {
  return dateFormatter
    .format(instant)
    .replace(/[‎‏‪-‮]/g, "")
    .trim();
}

/**
 * The time in Zambia without seconds, as HH:MM.
 *
 * @param {Date} [instant] The moment to render. Defaults to now.
 * @returns {string} e.g. "14:07"
 *
 * Used where a time is stated once rather than counted:
 * "Updated 14:07". Those readings go through here for the
 * same reason the clock does. A panel that reported its
 * refresh in the browser's timezone, next to a header
 * reporting Zambia's, would show two different times for
 * the same moment on one screen.
 */
export function formatZambiaShortTime(instant = new Date()) {
  return shortTimeFormatter
    .format(instant)
    .replace(/[‎‏‪-‮]/g, "")
    .trim();
}

/**
 * Both parts, plus a machine-readable timestamp.
 *
 * @param {Date} [instant] The moment to render. Defaults to now.
 * @returns {{time: string, date: string, iso: string}}
 *
 * iso is the instant itself, for the <time> element's
 * dateTime attribute. It is an absolute point in time, not
 * a Zambian wall-clock reading, which is what that
 * attribute is supposed to carry.
 */
export function zambiaNow(instant = new Date()) {
  return {
    time: formatZambiaTime(instant),
    date: formatZambiaDate(instant),
    iso: instant.toISOString(),
  };
}
