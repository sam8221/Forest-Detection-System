import assert from "node:assert/strict";
import test from "node:test";

import {
  getApiErrorMessage,
  readApiResponse,
} from "../src/services/apiError.js";

test("uses FastAPI's server detail instead of the generic save error", () => {
  const error = {
    message: "Request failed with status code 422",
    response: {
      status: 422,
      data: {
        detail: "The running API does not return phone_number.",
      },
    },
  };

  assert.equal(
    getApiErrorMessage(error, "The account could not be saved."),
    "The running API does not return phone_number."
  );
});

test("preserves a POST /users account-creation error", () => {
  const error = {
    message: "Request failed with status code 400",
    response: {
      status: 400,
      data: { detail: "Email already exists." },
    },
  };

  assert.equal(
    getApiErrorMessage(error, "The account could not be saved."),
    "Email already exists."
  );
});

test("preserves a PUT /users/{id} account-update error", () => {
  const error = {
    message: "Request failed with status code 404",
    response: {
      status: 404,
      data: { detail: "User not found." },
    },
  };

  assert.equal(
    getApiErrorMessage(error, "The account could not be saved."),
    "User not found."
  );
});

test("shows the stale-backend response check instead of the generic save error", () => {
  const error = new Error(
    "The API did not confirm the saved phone number. " +
      "Check that the running FastAPI backend includes phone-number support."
  );

  assert.equal(
    getApiErrorMessage(error, "The account could not be saved."),
    error.message
  );
});

test("shows validation messages returned as a FastAPI error list", () => {
  const error = {
    response: {
      status: 422,
      data: {
        detail: [
          { loc: ["body", "district_id"], msg: "Field required" },
          { loc: ["body", "role"], msg: "Invalid role" },
        ],
      },
    },
  };

  assert.equal(
    getApiErrorMessage(error, "The account could not be saved."),
    "Field required Invalid role"
  );
});

test("shows the request error for network failures without a response", () => {
  assert.equal(
    getApiErrorMessage(
      {
        message: "Network Error",
        config: { headers: { Authorization: "not-for-display" } },
      },
      "The account could not be saved."
    ),
    "Unable to connect to the ForestWatch API. Check your connection and try again."
  );
});

test("formats FastAPI validation arrays instead of rendering object text", () => {
  assert.equal(
    getApiErrorMessage(
      {
        response: {
          status: 422,
          data: {
            detail: [
              {
                loc: ["path", "image_id"],
                msg: "Input should be a valid integer",
              },
            ],
          },
        },
      },
      "Unable to retrieve download status."
    ),
    "Input should be a valid integer"
  );
});

test("extracts a safe message from an object-shaped FastAPI detail", () => {
  assert.equal(
    getApiErrorMessage(
      {
        response: {
          status: 400,
          data: { detail: { message: "Invalid search parameters." } },
        },
      },
      "Unable to search imagery."
    ),
    "Invalid search parameters."
  );
});

test("uses a safe fallback for opaque objects and sensitive server errors", () => {
  assert.equal(
    getApiErrorMessage(
      {
        response: {
          status: 500,
          data: {
            detail: { exception: "opaque" },
          },
        },
      },
      "Unable to search imagery."
    ),
    "The server could not complete the request (HTTP 500)."
  );
  assert.equal(
    getApiErrorMessage(
      {
        response: {
          status: 500,
          data: { detail: "Traceback (most recent call last)" },
        },
      },
      "Unable to search imagery."
    ),
    "The server could not complete the request (HTTP 500)."
  );
});

test("maps a fetch network failure to a useful connection message", () => {
  assert.equal(
    getApiErrorMessage(
      new TypeError("Failed to fetch"),
      "Unable to search imagery."
    ),
    "Unable to connect to the ForestWatch API. Check your connection and try again."
  );
});

test("reads a successful catalogue response containing real products", async () => {
  const products = Array.from({ length: 7 }, (_, index) => ({
    product_id: `sentinel-${index + 1}`,
  }));
  const response = {
    ok: true,
    status: 200,
    json: async () => ({ products, count: products.length }),
  };

  assert.deepEqual(
    await readApiResponse(response, "Unable to search imagery."),
    { products, count: 7 }
  );
});

test("reads invalid-date and Copernicus errors as safe API messages", async () => {
  await assert.rejects(
    readApiResponse(
      {
        ok: false,
        status: 400,
        json: async () => ({
          detail: "start_date cannot be later than end_date.",
        }),
      },
      "Unable to search imagery."
    ),
    { message: "start_date cannot be later than end_date." }
  );

  await assert.rejects(
    readApiResponse(
      {
        ok: false,
        status: 502,
        json: async () => ({
          detail: "Unable to retrieve Sentinel-2 imagery from Copernicus.",
        }),
      },
      "Unable to search imagery."
    ),
    { message: "Unable to retrieve Sentinel-2 imagery from Copernicus." }
  );
});

test("a successful repeat search can recover after a prior request error", async () => {
  const failedResponse = {
    ok: false,
    status: 422,
    json: async () => ({ detail: [{ msg: "Invalid date range." }] }),
  };
  const successfulResponse = {
    ok: true,
    status: 200,
    json: async () => ({ products: [{ product_id: "real-product" }] }),
  };

  await assert.rejects(
    readApiResponse(failedResponse, "Unable to search imagery."),
    { message: "Invalid date range." }
  );
  assert.deepEqual(
    await readApiResponse(successfulResponse, "Unable to search imagery."),
    { products: [{ product_id: "real-product" }] }
  );
});
