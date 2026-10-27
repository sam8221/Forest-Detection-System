const NETWORK_ERROR_MESSAGE =
  "Unable to connect to the ForestWatch API. Check your connection and try again.";

function safeMessage(value) {
  if (typeof value !== "string") return "";

  const message = value.trim();
  if (!message || message === "[object Object]") return "";

  // Do not put stack traces, credentials, or server internals in the UI.
  if (
    /traceback|stack trace|file \".*\.py\"|authorization|bearer\s|api[_ -]?key|password|secret|token/i.test(
      message
    )
  ) {
    return "";
  }

  return message.length > 500 ? `${message.slice(0, 497)}...` : message;
}

function extractDetailMessage(detail) {
  const direct = safeMessage(detail);
  if (direct) return direct;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return safeMessage(item);
        return safeMessage(item?.msg) || safeMessage(item?.message);
      })
      .filter(Boolean);

    return messages.join(" ");
  }

  if (detail && typeof detail === "object") {
    for (const key of ["message", "msg", "detail", "error_description"]) {
      const message = extractDetailMessage(detail[key]);
      if (message) return message;
    }
  }

  return "";
}

/**
 * Return a useful, safe message for Axios errors, fetch response
 * envelopes, FastAPI validation errors, network errors, and exceptions.
 * Request configuration is intentionally never serialized because it
 * can contain authorization headers.
 */
export function getApiErrorMessage(error, fallback) {
  const response = error?.response;
  const responseData = response?.data ?? error?.data ?? error?.body;
  const detailMessage = extractDetailMessage(responseData?.detail);
  if (detailMessage) return detailMessage;

  const responseMessage = safeMessage(responseData?.message);
  if (responseMessage) return responseMessage;

  const errorMessage = safeMessage(error?.message);
  if (errorMessage && !/^request failed with status code \d+$/i.test(errorMessage)) {
    if (
      error?.name === "TypeError" ||
      /^(failed to fetch|network error|network request failed)$/i.test(errorMessage)
    ) {
      return NETWORK_ERROR_MESSAGE;
    }
    return errorMessage;
  }

  const status = response?.status ?? error?.status;
  if (status) {
    return `The server could not complete the request (HTTP ${status}).`;
  }

  return safeMessage(fallback) || "The request could not be completed. Please try again.";
}

/** Parse a fetch response and throw a safe Error for non-success statuses. */
export async function readApiResponse(response, fallback) {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(
        { response: { status: response.status, data } },
        fallback
      )
    );
  }
  return data;
}
