/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: District Breakdown
 *
 * Purpose:
 *   Compares deforestation activity across the districts an
 *   officer supervises.
 *
 * Responsibilities:
 *   - Show detections and affected area per district.
 *   - Show how many detections are still awaiting review.
 *   - Highlight the district needing attention first.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Note:
 *   Shown only to officers responsible for more than one
 *   district: a Provincial Forestry Officer, or an
 *   Administrator.
 *
 *   A District Forestry Officer is responsible for one
 *   district, so a comparison would either show them a
 *   single row telling them nothing new, or other districts,
 *   which requirement FR-04 forbids. The server refuses
 *   their request regardless of what this interface shows.
 * ===========================================================
 */

import { useCallback, useEffect, useState } from "react";

import api from "../services/api";

/**
 * Compare districts within an officer's jurisdiction.
 *
 * @param {object} props
 * @param {boolean} props.visible
 *   Whether the signed-in officer supervises more than one
 *   district.
 */
function DistrictBreakdown({ visible }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!visible) {
      return;
    }

    setLoading(true);
    setError("");

    try {
      const response = await api.get(
        "/dashboard/districts"
      );

      setData(response.data);
    } catch (requestError) {
      // 403 means this officer supervises a single district.
      // That is the expected answer for their role, not a
      // fault, so nothing is reported.
      if (requestError?.response?.status !== 403) {
        setError(
          "The district breakdown could not be loaded."
        );
      }
    } finally {
      setLoading(false);
    }
  }, [visible]);

  useEffect(() => {
    load();
  }, [load]);

  if (!visible) {
    return null;
  }

  const districts = data?.districts || [];

  // Districts with nothing recorded are kept out of the main
  // comparison: an officer scanning for where to act should
  // not have to read past rows of zeroes. The count is still
  // reported underneath, because "no detections" is a
  // finding rather than missing data.
  const active = districts.filter(
    (row) => row.total_detections > 0
  );

  const quiet = districts.length - active.length;

  const worst = active.reduce(
    (highest, row) =>
      !highest ||
      row.affected_area_hectares >
        highest.affected_area_hectares
        ? row
        : highest,
    null
  );

  const totalPending = active.reduce(
    (sum, row) => sum + row.pending_detections,
    0
  );

  return (
    <section className="district-breakdown">

      <div className="district-breakdown-head">
        <div>
          <h3>Districts you supervise</h3>
          <p>
            {data?.scope
              ? `${data.scope} — where deforestation has ` +
                "been detected, and what is still awaiting " +
                "review."
              : "Comparing activity across your jurisdiction."}
          </p>
        </div>

        {totalPending > 0 && (
          <span className="district-pending-pill">
            {totalPending} awaiting review
          </span>
        )}
      </div>

      {loading && (
        <p className="district-muted">
          Loading district activity...
        </p>
      )}

      {error && (
        <p className="district-error">{error}</p>
      )}

      {!loading && !error && active.length === 0 && (
        <p className="district-muted">
          No deforestation has been detected in any district
          you supervise.
        </p>
      )}

      {!loading && !error && active.length > 0 && (
        <>
          <table className="district-table">
            <thead>
              <tr>
                <th>District</th>
                <th>Detections</th>
                <th>Awaiting review</th>
                <th>Area affected</th>
                <th>Most recent</th>
              </tr>
            </thead>

            <tbody>
              {active.map((row) => (
                <tr
                  key={row.district_id}
                  className={
                    worst &&
                    row.district_id === worst.district_id
                      ? "district-row worst"
                      : "district-row"
                  }
                >
                  <td>
                    <strong>{row.district_name}</strong>

                    {worst &&
                      row.district_id ===
                        worst.district_id && (
                        <span className="district-flag">
                          most affected
                        </span>
                      )}
                  </td>

                  <td>{row.total_detections}</td>

                  <td>
                    {row.pending_detections > 0 ? (
                      <span className="district-pending">
                        {row.pending_detections}
                      </span>
                    ) : (
                      <span className="district-clear">
                        none
                      </span>
                    )}
                  </td>

                  <td>
                    {row.affected_area_hectares.toFixed(2)}
                    {" ha"}
                  </td>

                  <td>
                    {row.latest_detection || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {quiet > 0 && (
            <p className="district-muted">
              {quiet} other district
              {quiet === 1 ? "" : "s"} monitored with no
              detections recorded.
            </p>
          )}
        </>
      )}

    </section>
  );
}

export default DistrictBreakdown;
