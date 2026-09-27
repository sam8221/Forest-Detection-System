/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Current User Hook
 *
 * Purpose:
 *   Loads and holds the signed-in officer's profile.
 *
 * Responsibilities:
 *   - Retrieve the profile once a session exists.
 *   - Expose the officer's role and jurisdiction.
 *   - Clear the profile when the session ends.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import { useCallback, useEffect, useState } from "react";

import { fetchCurrentUser } from "../services/auth";

/**
 * Load the signed-in officer's profile.
 *
 * @param {boolean} isAuthenticated
 *   Whether a session currently exists. The profile is
 *   requested only when it does, so an unauthenticated
 *   interface makes no call that is certain to fail.
 *
 * @returns {{
 *   currentUser: object|null,
 *   loading: boolean,
 *   error: string|null,
 *   reload: Function
 * }}
 */
export default function useCurrentUser(isAuthenticated) {
  const [currentUser, setCurrentUser] = useState(null);

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    if (!isAuthenticated) {
      setCurrentUser(null);
      setError(null);

      return;
    }

    setLoading(true);
    setError(null);

    try {
      const user = await fetchCurrentUser();

      setCurrentUser(user);
    } catch (requestError) {
      // Three different situations reach this point, and each
      // needs different wording, because the officer's next
      // step differs for each.
      //
      // No response at all means the request never reached
      // the server: the backend is not running, or the
      // address the interface was built with is wrong. Saying
      // "your profile could not be loaded" here sends the
      // officer looking for a problem with their account when
      // the real problem is that nothing is answering.
      //
      // A 401 means the session has already ended, and the API
      // client has signalled that separately, so nothing is
      // shown here.
      //
      // Anything else is a genuine failure on the server, and
      // is reported so the interface does not silently show
      // an account with no identity.
      if (!requestError?.response) {
        setError(
          "The ForestWatch server could not be reached, so " +
            "your profile and records cannot be loaded. " +
            "Check that the backend is running, then refresh " +
            "the page."
        );
      } else if (requestError.response.status !== 401) {
        setError(
          "Your profile could not be loaded. Some parts of " +
            "the interface may be incomplete."
        );
      }

      setCurrentUser(null);
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    load();
  }, [load]);

  return {
    currentUser,
    loading,
    error,
    reload: load,
  };
}
