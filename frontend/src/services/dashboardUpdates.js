/**
 * Deciding when the dashboard has something new to draw.
 *
 * The dashboard refreshes itself so that work finishing in
 * the background -- a satellite product downloading, a queued
 * analysis completing, the detections it writes -- reaches the
 * officer without them pressing Refresh.
 *
 * Asking for the summary every minute is cheap. Redrawing the
 * map and reloading the Sentinel-2 scene is not, so those
 * happen only when the summary shows the underlying data has
 * actually moved. The two functions here are that decision,
 * kept out of the page so it can be tested without a browser,
 * a server or a map.
 */

/**
 * Describe the state of the data behind the dashboard.
 *
 * Only the figures that imply new imagery or new results are
 * included. Alert delivery counts are deliberately left out:
 * an alert being sent or read changes nothing that is drawn
 * on the map, so including it would reload the imagery for
 * no visible difference.
 *
 * Missing or partial responses are treated as zero rather
 * than throwing, so a short reply cannot break the refresh
 * loop that calls this.
 *
 * @param {object} data Dashboard response.
 * @returns {string} A value that changes when the data does.
 */
export function satelliteSignature(data) {
  const statistics = data?.statistics || {};
  const images = statistics.satellite_images || {};
  const detections = statistics.detections || {};

  return [
    images.total_images ?? 0,
    images.processed_images ?? 0,
    detections.total_detections ?? 0,
    detections.verified_detections ?? 0,
    detections.rejected_detections ?? 0,
  ].join(":");
}

/**
 * Whether the map and the Sentinel-2 scene should be reloaded.
 *
 * A null previous signature means this is the first reading of
 * the session. The page has already loaded the map and the
 * scene by then, so reloading on that first comparison would
 * repeat two expensive requests to draw exactly what is
 * already on screen.
 *
 * @param {string|null} previous Signature from the last pass.
 * @param {string} next Signature from the current pass.
 * @returns {boolean}
 */
export function shouldReloadImagery(previous, next) {
  if (previous === null || previous === undefined) {
    return false;
  }

  return previous !== next;
}
