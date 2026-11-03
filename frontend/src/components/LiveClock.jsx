/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Live Clock
 *
 * Purpose:
 *   Shows the current date and time in Zambia in the
 *   application header, advancing every second.
 *
 * Responsibilities:
 *   - Read the clock once a second.
 *   - Render the time as HH:MM:SS and the date in full.
 *   - Stop the timer when the header is removed.
 *
 * What this will not do:
 *   It will not ask the server what time it is. The time
 *   shown is the viewer's own clock rendered in the Zambian
 *   timezone, so it costs no request and keeps running if
 *   the backend is unreachable. The formatting, and the
 *   reason the timezone is named rather than inferred, live
 *   in services/zambiaTime.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import { useEffect, useState } from "react";

import { zambiaNow } from "../services/zambiaTime";

/**
 * The header clock.
 *
 * @returns {JSX.Element}
 */
export default function LiveClock() {
  // Seeded with the present moment rather than null, so the
  // first paint shows the time instead of an empty box that
  // fills in a second later and shifts the header.
  const [now, setNow] = useState(() => zambiaNow());

  useEffect(() => {
    const tick = setInterval(
      () => setNow(zambiaNow()),
      1000
    );

    // Without this the timer outlives the component: every
    // remount would add another one, each setting state on
    // something no longer mounted, and they would
    // accumulate for as long as the session lasted.
    return () => clearInterval(tick);
  }, []);

  return (
    <div className="live-clock">
      {/* One <time> element carrying the instant, so the
          date and the clock are announced as one reading
          rather than two unrelated strings. */}
      <time
        className="live-clock-time"
        dateTime={now.iso}
      >
        {now.time}
      </time>

      <span className="live-clock-date">
        {now.date}
      </span>
    </div>
  );
}
