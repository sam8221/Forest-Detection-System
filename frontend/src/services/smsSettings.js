/**
 * What the SMS notification settings say to the officer.
 *
 * Several separate things decide whether an alert will
 * actually reach a handset: a number is saved, the officer
 * has notifications on, the column storing that preference
 * exists, the server's SMS sending is switched on, and the
 * provider accepts the credentials it was given. Any one of
 * them being false means no message arrives.
 *
 * Reporting only the first would let the page show a
 * registered number as though alerts were flowing while the
 * server was silent. Reporting a configured API key as a
 * working channel is the same mistake one level down: a key
 * that the provider rejects looks identical to a good one
 * from here, and the officer would be told alerts were on
 * their way while every message was refused.
 *
 * So the server verifies the credentials with the provider
 * and names the state in system_status, and this module
 * turns that into words. The status is derived here, where
 * it can be tested without a browser.
 */

/**
 * The system states the server can report.
 *
 * Kept apart from the officer's own states, which are
 * decided from the phone number and the preference.
 */
const SYSTEM_STATES = {
  ACTIVE: {
    tone: "active",
    label: "Active",
    detail:
      "You will receive an SMS when a new deforestation " +
      "alert is raised for your monitoring area.",
  },

  DISABLED: {
    tone: "pending",
    label: "Disabled",
    detail:
      "Your number is registered and notifications are " +
      "on, but SMS sending is switched off on the " +
      "server, so no alerts are being sent to anyone. " +
      "An administrator enables it with SMS_ENABLED.",
  },

  MISSING_CREDENTIALS: {
    tone: "fault",
    label: "Missing credentials",
    detail:
      "SMS is switched on, but the server has no " +
      "credentials for the SMS provider, so no alerts " +
      "can be sent to anyone.",
    administratorFixes: true,
  },

  INVALID_CREDENTIALS: {
    tone: "fault",
    label: "Invalid credentials",
    detail:
      "The SMS provider rejected the credentials the " +
      "server is using, so no alerts can be sent to " +
      "anyone.",
    administratorFixes: true,
  },

  PROVIDER_ERROR: {
    tone: "fault",
    label: "Connection error",
    detail:
      "The server could not confirm with the SMS " +
      "provider that alerts can be sent. This is either " +
      "a connection fault or a problem with the provider " +
      "account.",
    administratorFixes: true,
  },
};

/**
 * What an officer cannot fix themselves.
 *
 * Added to the detail of every system fault. Without it the
 * page describes a problem and leaves the officer to work
 * out that pressing Save Number again will not help.
 */
const ADMINISTRATOR_NOTE =
  " This is a server configuration problem, not a problem " +
  "with your number. Report it to an administrator.";

/**
 * Work out which system state applies.
 *
 * @param {object} settings The /users/profile/sms response.
 * @returns {string} A key of SYSTEM_STATES.
 *
 * Falls back to the older automatic_sending_enabled flag
 * when system_status is absent, so a page served by a
 * backend that predates the check still reads correctly
 * rather than showing every officer a fault.
 */
function systemStateKey(settings) {
  const reported = settings?.system_status;

  if (reported && reported in SYSTEM_STATES) {
    return reported;
  }

  if (reported) {
    // A state this page does not know about. Reported as a
    // fault rather than ignored: an unrecognised answer is
    // not evidence that messages are being sent.
    return "PROVIDER_ERROR";
  }

  return settings?.automatic_sending_enabled === true
    ? "ACTIVE"
    : "DISABLED";
}

/**
 * Describe the current notification status.
 *
 * @param {object} settings The /users/profile/sms response.
 * @returns {{tone: string, label: string, detail: string}}
 *   tone is one of "active", "paused", "pending", "fault"
 *   or "unregistered", for styling and for a reader who
 *   cannot distinguish the colours.
 *
 * The officer's own two states are reported first. Both are
 * things they can act on, and telling somebody about a
 * server fault before telling them they have saved no
 * number buries the step that is theirs to take.
 */
export function describeSmsStatus(settings) {
  const phone = settings?.phone_number || "";

  const enabled = settings?.sms_notifications_enabled !== false;

  if (!phone) {
    return {
      tone: "unregistered",
      label: "Not registered",
      detail:
        "Save a mobile number to receive automatic alerts " +
        "about suspected clearing in your area.",
    };
  }

  if (!enabled) {
    return {
      tone: "paused",
      label: "Notifications off",
      detail:
        "Your number is saved, but automatic alerts are " +
        "switched off for your account.",
    };
  }

  const state = SYSTEM_STATES[systemStateKey(settings)];

  // The server's own sentence is preferred where it gave
  // one: for a rejected credential or an unreachable
  // provider it carries what the provider actually said,
  // which is what an administrator needs to act on.
  const detail = settings?.system_detail || state.detail;

  return {
    tone: state.tone,
    label: state.label,
    detail: state.administratorFixes
      ? closeSentence(detail) + ADMINISTRATOR_NOTE
      : detail,
  };
}

/**
 * Make sure text can have another sentence added after it.
 *
 * @param {string} text Detail to append to.
 * @returns {string} The text, ending in punctuation.
 *
 * The provider's refusal arrives as a bare phrase with no
 * full stop, so appending to it ran two sentences together:
 * "...authentication is invalid This is a server
 * configuration problem".
 */
function closeSentence(text) {
  const trimmed = String(text || "").trim();

  if (!trimmed || /[.!?]$/.test(trimmed)) {
    return trimmed;
  }

  return `${trimmed}.`;
}

/**
 * Turn the welcome-message result into something to show.
 *
 * @param {object} result The /users/profile/sms/test response.
 * @returns {{ok: boolean, message: string}}
 *
 * The wording never says "delivered". The provider accepting
 * a message means it has the message, not that a handset
 * received it, and this system takes no delivery reports. An
 * officer told their number was reached when it was not
 * would stop watching for a problem that is still there.
 */
export function describeTestOutcome(result) {
  if (!result?.submitted) {
    return {
      ok: false,
      message:
        result?.detail ||
        "The welcome message could not be sent. Check the " +
          "number and the SMS provider configuration.",
    };
  }

  const recipient = result.recipient_phone
    ? ` to ${result.recipient_phone}`
    : "";

  const unrecorded = result.recorded === false
    ? " It could not be added to the message record; " +
      "the pending database migration is required for that."
    : "";

  return {
    ok: true,
    message:
      `The SMS provider accepted the welcome message${recipient}. ` +
      "Acceptance is not proof of delivery, so check the " +
      "handset." +
      unrecorded,
  };
}
