/**
 * Validate the written forms accepted by the backend's
 * Zambian mobile-number normalizer.
 *
 * The server remains authoritative and stores the E.164 form.
 */
export function normalizeZambianPhoneNumber(value) {
  const raw = String(value ?? "").trim();

  if (!raw) {
    return null;
  }

  const compact = raw.replace(/[\s().-]/g, "");
  const match = compact.match(
    /^(?:\+260|00260|260|0)?([79]\d{8})$/
  );

  return match ? `+260${match[1]}` : null;
}

export function validateZambianPhoneNumber(value) {
  if (!String(value ?? "").trim()) {
    return null;
  }

  return normalizeZambianPhoneNumber(value)
    ? null
    : "Enter a valid Zambian mobile number, such as +260971234567.";
}
