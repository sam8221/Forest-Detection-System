import assert from "node:assert/strict";
import test from "node:test";

import {
  describeSmsStatus,
  describeTestOutcome,
} from "../src/services/smsSettings.js";

const settings = ({
  phone_number = "+260977123456",
  sms_notifications_enabled = true,
  preference_supported = true,
  automatic_sending_enabled = true,
  system_status = undefined,
  system_detail = undefined,
} = {}) => ({
  phone_number,
  sms_notifications_enabled,
  preference_supported,
  automatic_sending_enabled,
  system_status,
  system_detail,
});

test("a registered, enabled officer on a sending system is active", () => {
  const status = describeSmsStatus(settings());

  assert.equal(status.tone, "active");
  assert.equal(status.label, "Active");
});

test("no saved number reads as not registered", () => {
  const status = describeSmsStatus(settings({ phone_number: null }));

  assert.equal(status.tone, "unregistered");
  assert.match(status.detail, /Save a mobile number/);
});

test("an officer who switched notifications off is not shown as active", () => {
  const status = describeSmsStatus(
    settings({ sms_notifications_enabled: false })
  );

  assert.equal(status.tone, "paused");
  assert.equal(status.label, "Notifications off");
});

test("a registered officer is not shown as active while the server is not sending", () => {
  // The failure this exists to prevent: a number saved, the
  // officer believing alerts are flowing, and SMS_ENABLED
  // false so nothing is sent to anyone.
  const status = describeSmsStatus(
    settings({ automatic_sending_enabled: false })
  );

  assert.equal(status.tone, "pending");
  assert.match(status.detail, /switched off on the server/);
});

test("being switched off for the account outranks the server switch", () => {
  const status = describeSmsStatus(
    settings({
      sms_notifications_enabled: false,
      automatic_sending_enabled: false,
    })
  );

  assert.equal(status.tone, "paused");
});

test("a missing or empty response does not throw", () => {
  assert.equal(describeSmsStatus(undefined).tone, "unregistered");
  assert.equal(describeSmsStatus({}).tone, "unregistered");
});

// =========================================================
// THE SYSTEM STATES
//
// The failure these exist to prevent: a key sitting in the
// server configuration being taken for a working channel.
// An invalid key, a missing one and a provider that cannot
// be reached all mean no officer is alerted, and each is
// fixed by something different, so none of them may be
// reported as Active and none may be collapsed into the
// others.
// =========================================================

test("a verified, enabled officer on a sending system is active", () => {
  const status = describeSmsStatus(
    settings({ system_status: "ACTIVE" })
  );

  assert.equal(status.tone, "active");
  assert.equal(status.label, "Active");
});

test("sending switched off on the server reads as disabled", () => {
  const status = describeSmsStatus(
    settings({
      system_status: "DISABLED",
      automatic_sending_enabled: false,
    })
  );

  assert.equal(status.tone, "pending");
  assert.equal(status.label, "Disabled");
  assert.match(status.detail, /switched off on the server/);
});

test("credentials that were never configured are named as missing", () => {
  const status = describeSmsStatus(
    settings({
      system_status: "MISSING_CREDENTIALS",
      automatic_sending_enabled: false,
    })
  );

  assert.equal(status.tone, "fault");
  assert.equal(status.label, "Missing credentials");
});

test("credentials the provider rejected are named as invalid", () => {
  const status = describeSmsStatus(
    settings({
      system_status: "INVALID_CREDENTIALS",
      automatic_sending_enabled: false,
      system_detail:
        "The SMS provider rejected the configured " +
        "credentials: The supplied authentication is invalid",
    })
  );

  assert.equal(status.tone, "fault");
  assert.equal(status.label, "Invalid credentials");

  // The provider's own words reach the page, because that
  // sentence is what an administrator acts on.
  assert.match(status.detail, /authentication is invalid/);

  // The provider's phrase has no full stop of its own, so
  // one is added rather than running two sentences
  // together.
  assert.match(status.detail, /authentication is invalid\. This is/);
});

test("a provider that did not answer reads as a connection error", () => {
  const status = describeSmsStatus(
    settings({
      system_status: "PROVIDER_ERROR",
      automatic_sending_enabled: false,
    })
  );

  assert.equal(status.tone, "fault");
  assert.equal(status.label, "Connection error");
});

test("every system fault tells the officer it is not their number", () => {
  for (const state of [
    "MISSING_CREDENTIALS",
    "INVALID_CREDENTIALS",
    "PROVIDER_ERROR",
  ]) {
    const status = describeSmsStatus(
      settings({
        system_status: state,
        automatic_sending_enabled: false,
      })
    );

    assert.match(status.detail, /not a problem with your number/);
    assert.match(status.detail, /administrator/);
  }
});

test("a system state this page does not know is not reported as active", () => {
  // A newer backend reporting a state added after this page
  // was written. Guessing it is harmless would be the same
  // error as trusting a key.
  const status = describeSmsStatus(
    settings({
      system_status: "QUOTA_EXHAUSTED",
      automatic_sending_enabled: true,
    })
  );

  assert.equal(status.tone, "fault");
  assert.notEqual(status.label, "Active");
});

test("the officer's own state is reported before a server fault", () => {
  // Saving a number is the step that is theirs to take, and
  // a server fault stated first would bury it.
  const unregistered = describeSmsStatus(
    settings({
      phone_number: null,
      system_status: "INVALID_CREDENTIALS",
    })
  );

  assert.equal(unregistered.tone, "unregistered");

  const off = describeSmsStatus(
    settings({
      sms_notifications_enabled: false,
      system_status: "INVALID_CREDENTIALS",
    })
  );

  assert.equal(off.tone, "paused");
});

test("a response with no system_status falls back to the old flag", () => {
  // A page served while an older backend is still running
  // must not show every officer a fault.
  assert.equal(
    describeSmsStatus(settings({ automatic_sending_enabled: true })).tone,
    "active"
  );

  assert.equal(
    describeSmsStatus(settings({ automatic_sending_enabled: false })).label,
    "Disabled"
  );
});

test("an accepted test is never described as delivered", () => {
  const outcome = describeTestOutcome({
    submitted: true,
    status: "SUBMITTED",
    recipient_phone: "+260977123456",
    recorded: true,
  });

  assert.equal(outcome.ok, true);
  assert.match(outcome.message, /accepted the welcome message/);
  assert.match(outcome.message, /not proof of delivery/);
  assert.doesNotMatch(outcome.message, /delivered\b/i);
});

test("a failed test shows the reason it failed", () => {
  const outcome = describeTestOutcome({
    submitted: false,
    status: "FAILED",
    detail: "The provider refused the message: invalid sender (code 405).",
  });

  assert.equal(outcome.ok, false);
  assert.match(outcome.message, /refused the message/);
});

test("a failure with no detail still says something useful", () => {
  const outcome = describeTestOutcome({ submitted: false });

  assert.equal(outcome.ok, false);
  assert.match(outcome.message, /could not be sent/);
});

test("a send that could not be recorded says so", () => {
  const outcome = describeTestOutcome({
    submitted: true,
    recipient_phone: "+260977123456",
    recorded: false,
  });

  assert.equal(outcome.ok, true);
  assert.match(outcome.message, /could not be added to the message record/);
});
