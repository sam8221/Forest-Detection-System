export function validateObservationPair(
  images,
  forestAreaId,
  previousId,
  recentId
) {
  const previous = images.find(
    (image) => String(image.id) === String(previousId)
  );
  const recent = images.find(
    (image) => String(image.id) === String(recentId)
  );

  if (!previous || !recent) {
    return { valid: false, error: "Choose two available observations." };
  }
  if (String(previous.id) === String(recent.id)) {
    return { valid: false, error: "Choose two different observation dates." };
  }
  if (
    String(previous.forest_area_id) !== String(forestAreaId) ||
    String(recent.forest_area_id) !== String(forestAreaId)
  ) {
    return { valid: false, error: "Both observations must belong to this forest area." };
  }
  if (
    previous.is_downloaded !== true ||
    recent.is_downloaded !== true ||
    previous.is_ready_for_analysis !== true ||
    recent.is_ready_for_analysis !== true ||
    previous.is_active !== true ||
    recent.is_active !== true
  ) {
    return { valid: false, error: "Both observations must be active, downloaded, and locally ready for analysis." };
  }
  if (!previous.tile_id || !recent.tile_id || previous.tile_id !== recent.tile_id) {
    return { valid: false, error: "Choose observations from the same Sentinel-2 tile." };
  }
  if (
    previous.processing_level !== "L2A" ||
    recent.processing_level !== "L2A"
  ) {
    return { valid: false, error: "Both observations must use Level-2A processing." };
  }
  if (
    !previous.acquisition_date ||
    !recent.acquisition_date ||
    !Number.isFinite(new Date(previous.acquisition_date).getTime()) ||
    !Number.isFinite(new Date(recent.acquisition_date).getTime()) ||
    new Date(previous.acquisition_date).getTime() >=
      new Date(recent.acquisition_date).getTime()
  ) {
    return { valid: false, error: "The previous observation must be earlier than the recent one." };
  }

  return { valid: true, previous, recent };
}

export function getEligibleObservations(images, forestAreaId) {
  return (Array.isArray(images) ? images : [])
    .filter((image) => {
      const acquisitionTime = new Date(image.acquisition_date).getTime();
      return (
        String(image.forest_area_id) === String(forestAreaId) &&
        image.is_active === true &&
        image.is_downloaded === true &&
        image.is_ready_for_analysis === true &&
        image.processing_level === "L2A" &&
        Boolean(image.acquisition_date) &&
        Number.isFinite(acquisitionTime)
      );
    })
    .sort((first, second) =>
      String(first.acquisition_date).localeCompare(
        String(second.acquisition_date)
      )
    );
}

export function findEligibleObservation(images, forestAreaId, imageId) {
  return (
    getEligibleObservations(images, forestAreaId).find(
      (image) => String(image.id) === String(imageId)
    ) || null
  );
}

export function getSelectedObservationCards(
  images,
  forestAreaId,
  previousId,
  recentId
) {
  const eligible = getEligibleObservations(images, forestAreaId);
  const findById = (imageId) =>
    eligible.find((image) => String(image.id) === String(imageId)) || null;

  return [
    {
      role: "previous",
      label: "Previous observation",
      image: findById(previousId),
    },
    {
      role: "recent",
      label: "Recent observation",
      image: findById(recentId),
    },
  ].filter((card) => card.image);
}

export function clampSwipePercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 50;
  return Math.min(100, Math.max(0, number));
}

export function comparisonLayoutClass(mode) {
  const selectedMode = Object.values(COMPARISON_MODES).includes(mode)
    ? mode
    : COMPARISON_MODES.SWIPE;
  return `satellite-comparison-${selectedMode}`;
}

export function swipeClipPath(value) {
  return `inset(0 ${100 - clampSwipePercent(value)}% 0 0)`;
}

export function synchronizeViewState(view) {
  return {
    center: view.center ? [...view.center] : undefined,
    resolution: view.resolution,
    rotation: view.rotation || 0,
  };
}

export const COMPARISON_MODES = Object.freeze({
  SWIPE: "swipe",
  SIDE_BY_SIDE: "side-by-side",
});

export const SELECTED_COMPARISON_LAYERS = Object.freeze({
  NDVI_DIFFERENCE: "selected_ndvi_difference",
  PERSISTENCE_CANDIDATES: "confirmed_loss",
});

export function formatComparisonMeanNdvi(value) {
  if (value === null || value === undefined || value === "") {
    return "Unavailable";
  }
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(3) : "Unavailable";
}

export function applySynchronizedViewState(sourceView, targetView) {
  const state = synchronizeViewState(sourceView);
  if (state.center) targetView.setCenter(state.center);
  if (Number.isFinite(state.resolution)) {
    targetView.setResolution(state.resolution);
  }
  targetView.setRotation(state.rotation);
  return state;
}

/* ----------------------------------------------------------
   Swipe divider interaction

   The swipe comparison used to be driven by a transparent
   range input laid across the middle of the map. That had
   three problems, all of which made the divider feel like it
   was fighting the pointer:

   - the input was only about twenty pixels tall at the
     vertical centre, so the divider could not be grabbed
     anywhere else along its length;
   - the input was invisible, so the thing the officer could
     see (a three pixel white line) was not the thing that
     responded to the pointer;
   - the input track was inset by 3rem while the clip path and
     the divider line were positioned against the full width,
     so the line and the pointer drifted further apart the
     closer the divider came to either edge.

   The divider is now a slider element spanning the full
   height of the map, dragged with pointer events. The
   position is computed here, against the same box the clip
   path uses, so the line stays exactly under the pointer.
   ---------------------------------------------------------- */

/** Percentage moved by an arrow key. */
export const SWIPE_STEP = 2;

/** Percentage moved by Page Up, Page Down, or a shifted arrow. */
export const SWIPE_COARSE_STEP = 10;

/**
 * Convert a pointer position into a reveal percentage.
 *
 * Measured against the rectangle of the element the panels
 * are clipped within, which is why the divider cannot drift
 * away from the clip edge.
 *
 * @param {number} clientX pointer X in client coordinates.
 * @param {{left: number, width: number}|null|undefined} rect
 *   the swipe area's bounding rectangle.
 * @returns {number|null} the percentage, or null when the
 *   area has no width yet and the pointer cannot be placed.
 */
export function swipePercentFromPointer(clientX, rect) {
  const width = Number(rect?.width);
  const left = Number(rect?.left);

  if (!Number.isFinite(width) || width <= 0) return null;
  if (!Number.isFinite(left) || !Number.isFinite(Number(clientX))) return null;

  return clampSwipePercent(((Number(clientX) - left) / width) * 100);
}

/**
 * Apply a keyboard adjustment to the reveal percentage.
 *
 * Returns null for any key this control does not act on, so
 * the caller leaves that key alone rather than swallowing
 * Tab and the browser's own shortcuts.
 *
 * @param {number} current
 * @param {string} key the KeyboardEvent key.
 * @param {boolean} coarse true when Shift is held.
 * @returns {number|null}
 */
export function nextSwipePercent(current, key, coarse = false) {
  const step = coarse ? SWIPE_COARSE_STEP : SWIPE_STEP;
  const from = clampSwipePercent(current);

  switch (key) {
    case "ArrowLeft":
    case "ArrowDown":
      return clampSwipePercent(from - step);
    case "ArrowRight":
    case "ArrowUp":
      return clampSwipePercent(from + step);
    case "PageDown":
      return clampSwipePercent(from - SWIPE_COARSE_STEP);
    case "PageUp":
      return clampSwipePercent(from + SWIPE_COARSE_STEP);
    case "Home":
      return 0;
    case "End":
      return 100;
    default:
      return null;
  }
}
