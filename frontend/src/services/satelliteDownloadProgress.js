import { getApiErrorMessage } from "./apiError.js";

const ACTIVE_STATUSES = new Set([
  "PREPARING",
  "DOWNLOADING",
  "VALIDATING",
]);

/**
 * Explain the legacy-route validation response produced when an older
 * FastAPI process treats `/downloads` as the integer `{image_id}` route.
 */
export function getDownloadStatusErrorMessage(status, data) {
  if (status === 401) {
    return "ForestWatch could not authenticate this request. Sign in again, then check the download status.";
  }

  if (status === 403) {
    return "Your account is not authorised to view this download status.";
  }

  const validationErrors = data?.detail;
  const matchedLegacyImageRoute =
    status === 422 &&
    Array.isArray(validationErrors) &&
    validationErrors.some(
      (item) =>
        Array.isArray(item?.loc) && item.loc.includes("image_id")
    );

  if (matchedLegacyImageRoute) {
    return (
      "This FastAPI instance does not expose the satellite download-status " +
      "route. Restart the backend from the current ForestWatch project to " +
      "enable download progress."
    );
  }

  return getApiErrorMessage(
    { response: { status, data } },
    "Unable to retrieve download status. The download may still be running."
  );
}

/**
 * Decide whether a download-status failure can ever clear by itself.
 *
 * Most 5xx responses are transient, but the backend answers 503 when the
 * satellite_download_jobs migration has not been applied. That condition
 * needs an operator to run Alembic, so polling it forever only hides the
 * one message that says what to do.
 */
export function isDownloadStatusErrorPermanent(status, data) {
  const code = Number(status);

  if (code === 400 || code === 401 || code === 403 || code === 422) {
    return true;
  }

  if (code === 503) {
    const detail = typeof data?.detail === "string" ? data.detail : "";
    return /migration/i.test(detail);
  }

  return false;
}

/** Retry transient status transport/service errors, not auth or route errors. */
export function shouldRetryDownloadStatusError(error) {
  if (error?.name === "AbortError") return false;

  // Set by the caller from the response body when the status code alone
  // cannot say whether retrying could succeed.
  if (error?.permanent === true) return false;

  const status = Number(error?.status);
  if (Number.isFinite(status) && status > 0) {
    return status === 408 || status === 429 || status >= 500;
  }

  // A fetch rejection without an HTTP response is a network-level failure.
  return true;
}

export function isSatelliteDownloadActive(status) {
  return ACTIVE_STATUSES.has(String(status || "").toUpperCase());
}

export function mergeSatelliteDownloadJobs(current, jobs) {
  const next = { ...current };
  for (const job of Array.isArray(jobs) ? jobs : []) {
    if (job?.product_id) {
      next[job.product_id] = job;
    }
  }
  return next;
}

export function getSatelliteDownloadButtonState(
  job,
  isAcquired = false,
  statusUnavailable = false
) {
  const status = String(job?.status || "").toUpperCase();
  const progress = job?.progress_percentage != null && Number.isFinite(Number(job.progress_percentage))
    ? Math.max(0, Math.min(100, Number(job.progress_percentage)))
    : null;

  if (isAcquired || status === "COMPLETED") {
    return {
      label: "Acquired",
      disabled: true,
      active: false,
      progress: null,
      error: null,
    };
  }

  if (statusUnavailable) {
    return {
      label: "Status unavailable",
      disabled: true,
      active: false,
      progress: null,
      error: null,
    };
  }

  if (status === "FAILED") {
    return {
      label: "Retry Download",
      disabled: false,
      active: false,
      progress: null,
      error: job?.error_message || "The download failed. Retry the acquisition.",
    };
  }

  if (status === "PREPARING") {
    return {
      label: "Preparing...",
      disabled: true,
      active: true,
      progress: null,
      error: null,
    };
  }

  if (status === "DOWNLOADING") {
    const displayPercentage = progress === null ? null : Math.min(99, Math.floor(progress));
    return {
      label:
        displayPercentage === null
          ? "Downloading..."
          : `Downloading ${displayPercentage}%`,
      disabled: true,
      active: true,
      progress,
      error: null,
    };
  }

  if (status === "VALIDATING") {
    return {
      label: "Validating...",
      disabled: true,
      active: true,
      progress,
      error: null,
    };
  }

  return {
    label: "Acquire",
    disabled: false,
    active: false,
    progress: null,
    error: null,
  };
}
