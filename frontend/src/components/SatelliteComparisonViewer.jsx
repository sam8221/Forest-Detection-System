import { useEffect, useRef, useState } from "react";
import Map from "ol/Map";
import View from "ol/View";
import GeoJSON from "ol/format/GeoJSON";
import ImageLayer from "ol/layer/Image";
import VectorLayer from "ol/layer/Vector";
import Static from "ol/source/ImageStatic";
import VectorSource from "ol/source/Vector";
import { defaults as defaultControls } from "ol/control/defaults";
import { transformExtent } from "ol/proj";
import { Fill, Stroke, Style } from "ol/style";
import { unByKey } from "ol/Observable";
import "ol/ol.css";

import { API_V1 } from "../config";
import { getApiErrorMessage } from "../services/apiError";
import { comparisonFigureUrls } from "../services/analysisJobState";
import {
  applySynchronizedViewState,
  COMPARISON_MODES,
  clampSwipePercent,
  comparisonLayoutClass,
  formatComparisonMeanNdvi,
  nextSwipePercent,
  SELECTED_COMPARISON_LAYERS,
  swipeClipPath,
  swipePercentFromPointer,
} from "../services/satelliteComparison";

function authHeaders() {
  const token = localStorage.getItem("access_token") || localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function readJson(url) {
  const response = await fetch(url, { headers: authHeaders() });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(getApiErrorMessage(
      { response: { status: response.status, data: body } },
      "The selected comparison could not be loaded."
    ));
  }
  return body;
}

async function readImage(url) {
  const response = await fetch(url, { headers: authHeaders() });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(getApiErrorMessage(
      { response: { status: response.status, data: body } },
      "The comparison image could not be loaded."
    ));
  }
  return URL.createObjectURL(await response.blob());
}

function imageExtent(bounds) {
  return transformExtent(bounds, "EPSG:4326", "EPSG:3857");
}

function createMap(target, imageUrl, bounds, boundary) {
  const image = new ImageLayer({
    source: new Static({
      url: imageUrl,
      imageExtent: imageExtent(bounds),
      projection: "EPSG:3857",
    }),
    properties: { comparisonRole: "image" },
  });
  const features = new GeoJSON().readFeatures(
    { type: "Feature", geometry: boundary, properties: {} },
    { dataProjection: "EPSG:4326", featureProjection: "EPSG:3857" }
  );
  const boundarySource = new VectorSource({ features });
  const outline = new VectorLayer({
    source: boundarySource,
    style: new Style({
      stroke: new Stroke({ color: "#f8fafc", width: 2.5 }),
      fill: new Fill({ color: "rgba(0,0,0,0)" }),
    }),
    properties: { comparisonRole: "boundary" },
  });
  const view = new View({ center: [0, 0], zoom: 2, constrainOnlyCenter: true });
  const map = new Map({
    target,
    controls: defaultControls(),
    layers: [image, outline],
    view,
  });
  const extent = boundarySource.getExtent();
  if (extent && Number.isFinite(extent[0])) {
    requestAnimationFrame(() => {
      map.updateSize();
      map.getView().fit(extent, {
        size: map.getSize(),
        padding: [32, 32, 32, 32],
        maxZoom: 17,
      });
    });
  }
  return map;
}

export default function SatelliteComparisonViewer({ forestAreaId, jobId }) {
  const previousTargetRef = useRef(null);
  const recentTargetRef = useRef(null);
  const changeTargetRef = useRef(null);
  const mapsRef = useRef({ previous: null, recent: null, change: null });
  const swipeAreaRef = useRef(null);
  const swipeDraggingRef = useRef(false);
  const [mode, setMode] = useState(COMPARISON_MODES.SWIPE);
  const [swipe, setSwipe] = useState(50);
  const [changeLayer, setChangeLayer] = useState(
    SELECTED_COMPARISON_LAYERS.NDVI_DIFFERENCE
  );
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [resources, setResources] = useState(null);
  const [changeUrl, setChangeUrl] = useState("");
  const [figureAssets, setFigureAssets] = useState(null);
  const [figureError, setFigureError] = useState("");

  useEffect(() => {
    let disposed = false;
    const objectUrls = [];
    setLoading(true);
    setError("");
    setResources(null);
    setFigureAssets(null);
    setFigureError("");

    (async () => {
      const base = `${API_V1}/monitoring/${forestAreaId}/comparison/${jobId}`;
      const metadata = await readJson(base);
      const [previousUrl, recentUrl] = await Promise.all([
        readImage(`${base}/image/previous.png`),
        readImage(`${base}/image/recent.png`),
      ]);
      if (disposed) {
        URL.revokeObjectURL(previousUrl);
        URL.revokeObjectURL(recentUrl);
        return;
      }
      objectUrls.push(previousUrl, recentUrl);
      setDetail(metadata);
      setResources({ previousUrl, recentUrl });
    })()
      .catch((requestError) => {
        if (!disposed) setError(getApiErrorMessage(requestError, "Comparison could not be loaded."));
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });

    return () => {
      disposed = true;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [forestAreaId, jobId]);

  useEffect(() => {
    let disposed = false;
    const objectUrls = [];
    if (!detail) return undefined;
    setFigureAssets(null);
    setFigureError("");
    const panelNames = ["previous_rgb", "previous_ndvi", "recent_ndvi", "ndvi_difference"];
    const figureUrls = comparisonFigureUrls(API_V1, forestAreaId, jobId);
    const loadImage = (url) => readImage(url).then((imageUrl) => {
      objectUrls.push(imageUrl);
      return imageUrl;
    });
    Promise.all([
      loadImage(figureUrls.figure),
      ...panelNames.map((panel) => loadImage(figureUrls.panels[panel])),
    ])
      .then(([downloadUrl, ...panelUrls]) => {
        if (disposed) {
          objectUrls.forEach((url) => URL.revokeObjectURL(url));
          objectUrls.length = 0;
          return;
        }
        setFigureAssets({
          downloadUrl,
          panels: Object.fromEntries(panelNames.map((name, index) => [name, panelUrls[index]])),
        });
      })
      .catch((requestError) => {
        objectUrls.forEach((url) => URL.revokeObjectURL(url));
        objectUrls.length = 0;
        if (!disposed) {
          setFigureError(
            getApiErrorMessage(
              requestError,
              "The scientific figure export is unavailable for this analysis."
            )
          );
        }
      });
    return () => {
      disposed = true;
      objectUrls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [detail, forestAreaId, jobId]);

  useEffect(() => {
    let disposed = false;
    let objectUrl = "";
    setChangeUrl("");
    if (!detail) return undefined;
    const url = `${API_V1}/monitoring/${forestAreaId}/comparison/${jobId}/layer/${changeLayer}.png`;
    readImage(url)
      .then((imageUrl) => {
        objectUrl = imageUrl;
        if (disposed) URL.revokeObjectURL(imageUrl);
        else setChangeUrl(imageUrl);
      })
      .catch((requestError) => {
        if (!disposed) setError(getApiErrorMessage(requestError, "The change layer could not be loaded."));
      });
    return () => {
      disposed = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [changeLayer, detail, forestAreaId, jobId]);

  useEffect(() => {
    if (
      !resources || !detail || !changeUrl ||
      !previousTargetRef.current || !recentTargetRef.current || !changeTargetRef.current
    ) return undefined;

    const bounds = detail.grid.bounds;
    const previous = createMap(
      previousTargetRef.current,
      resources.previousUrl,
      detail.observations.previous.bounds || bounds,
      detail.forest_area.boundary
    );
    const recent = createMap(
      recentTargetRef.current,
      resources.recentUrl,
      detail.observations.recent.bounds || bounds,
      detail.forest_area.boundary
    );
    const change = createMap(
      changeTargetRef.current,
      changeUrl,
      bounds,
      detail.forest_area.boundary
    );
    mapsRef.current = { previous, recent, change };

    let syncing = false;
    const synchronize = (source, target) => {
      const update = () => {
        if (syncing) return;
        syncing = true;
        try {
          applySynchronizedViewState(source.getView(), target.getView());
        } finally {
          syncing = false;
        }
      };
      return [
        source.getView().on("change:center", update),
        source.getView().on("change:resolution", update),
        source.getView().on("change:rotation", update),
      ];
    };
    const mapList = [previous, recent, change];
    const keys = [];
    mapList.forEach((source, index) => {
      mapList.forEach((target, targetIndex) => {
        if (index !== targetIndex) keys.push(...synchronize(source, target));
      });
    });

    return () => {
      unByKey(keys);
      mapList.forEach((map) => map.setTarget(undefined));
      mapsRef.current = { previous: null, recent: null, change: null };
    };
  }, [resources, detail, changeUrl]);

  useEffect(() => {
    Object.values(mapsRef.current).forEach((map) => map?.updateSize());
  }, [mode]);

  if (loading) return <div className="satellite-comparison-status">Loading selected Sentinel-2 observations...</div>;
  if (error) return <div className="satellite-comparison-error" role="alert">{error}</div>;
  // The observations block is checked as well as the detail
  // itself. Reading detail.observations.previous without it
  // throws for any response that arrives without one, and
  // because this component sits inside the results section
  // that exception unmounts the whole subtree: the stat
  // tiles and the measurement panel disappear along with the
  // viewer, so a partial comparison response reads as an
  // analysis that produced nothing at all.
  if (
    !detail ||
    !detail.observations ||
    !detail.observations.previous ||
    !detail.observations.recent ||
    !resources ||
    !changeUrl
  ) {
    return null;
  }

  const previous = detail.observations.previous;
  const recent = detail.observations.recent;
  const titleDate = (value) => new Date(value).toLocaleDateString("en-ZM", {
    day: "2-digit", month: "short", year: "numeric",
  });
  const isNdviChange = changeLayer === SELECTED_COMPARISON_LAYERS.NDVI_DIFFERENCE;

  // -----------------------------------------------------
  // Swipe divider
  //
  // Dragging is driven by pointer events with pointer
  // capture, so one gesture keeps hold of the divider even
  // when the pointer runs past the edge of the map or over
  // the OpenLayers canvas beneath. The arithmetic lives in
  // services/satelliteComparison.js, where it is tested
  // without a browser.
  // -----------------------------------------------------

  const revealPercent = clampSwipePercent(swipe);

  const moveSwipeToPointer = (clientX) => {
    const next = swipePercentFromPointer(
      clientX,
      swipeAreaRef.current?.getBoundingClientRect()
    );

    if (next !== null) setSwipe(next);
  };

  const handleSwipePointerDown = (event) => {
    // Without this the same press also starts a pan on the
    // map underneath, and the scene slides while the divider
    // moves.
    event.preventDefault();
    event.stopPropagation();

    swipeDraggingRef.current = true;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.currentTarget.focus?.();
    moveSwipeToPointer(event.clientX);
  };

  const handleSwipePointerMove = (event) => {
    if (!swipeDraggingRef.current) return;

    event.preventDefault();
    moveSwipeToPointer(event.clientX);
  };

  const handleSwipePointerRelease = (event) => {
    if (!swipeDraggingRef.current) return;

    swipeDraggingRef.current = false;

    // Releasing a capture that was never taken throws, and a
    // cancelled gesture can arrive after the browser has
    // already dropped it.
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  const handleSwipeKeyDown = (event) => {
    const next = nextSwipePercent(swipe, event.key, event.shiftKey);

    // null means a key this control does not act on, such as
    // Tab, which must keep working.
    if (next === null) return;

    event.preventDefault();
    setSwipe(next);
  };

  return (
    <section className="satellite-comparison" aria-label="Sentinel-2 image comparison">
      <div className="satellite-comparison-heading">
        <div>
          <h3>{detail.forest_area.name}: selected Sentinel-2 comparison</h3>
          <p>Analysis job #{detail.analysis_job_id} · Tile {previous.tile_id}</p>
        </div>
        <div className="satellite-comparison-modes" role="group" aria-label="Comparison mode">
          <button type="button" aria-pressed={mode === COMPARISON_MODES.SWIPE} onClick={() => setMode(COMPARISON_MODES.SWIPE)}>Swipe</button>
          <button type="button" aria-pressed={mode === COMPARISON_MODES.SIDE_BY_SIDE} onClick={() => setMode(COMPARISON_MODES.SIDE_BY_SIDE)}>Side by side</button>
        </div>
      </div>

      <div className="satellite-comparison-dates">
        <div>
          <strong>Panel A · Previous · {titleDate(previous.acquisition_date)}</strong>
          <span>{previous.product_id} · Catalogue cloud {Number(previous.cloud_cover_percentage).toFixed(1)}% · clear inside boundary {previous.valid_percentage}%</span>
        </div>
        <div>
          <strong>Panel B · Recent · {titleDate(recent.acquisition_date)}</strong>
          <span>{recent.product_id} · Catalogue cloud {Number(recent.cloud_cover_percentage).toFixed(1)}% · clear inside boundary {recent.valid_percentage}%</span>
        </div>
      </div>

      <section className="satellite-scientific-figure" aria-labelledby="scientific-figure-title">
        <div className="satellite-scientific-figure-heading">
          <div>
            <h4 id="scientific-figure-title">Scientific comparison figure</h4>
            <p>Four panels from the selected products and this completed analysis job.</p>
          </div>
          {figureAssets && (
            <div className="satellite-scientific-figure-actions">
              <a href={figureAssets.downloadUrl} download={`forestwatch-job-${jobId}-comparison.png`}>
                Download high-resolution figure
              </a>
              <a href={figureAssets.downloadUrl} target="_blank" rel="noreferrer">
                Open full size
              </a>
            </div>
          )}
        </div>
        {figureAssets ? (
          <>
            <div className="satellite-scientific-panels">
              <figure>
                <figcaption>
                  <strong>(a) Previous observation · true-colour RGB</strong>
                  <span>{titleDate(previous.acquisition_date)} · {previous.product_id} · B04/B03/B02</span>
                </figcaption>
                <img src={figureAssets.panels.previous_rgb} alt={`Previous Sentinel-2 true-colour image for ${detail.forest_area.name}, clipped to its boundary.`} />
              </figure>
              <figure>
                <figcaption>
                  <strong>(b) Previous observation · NDVI</strong>
                  <span>{titleDate(previous.acquisition_date)} · {previous.product_id}</span>
                </figcaption>
                <img src={figureAssets.panels.previous_ndvi} alt="Previous-observation NDVI map, masked to the selected forest boundary and valid pixels." />
              </figure>
              <figure>
                <figcaption>
                  <strong>(c) Recent observation · NDVI</strong>
                  <span>{titleDate(recent.acquisition_date)} · {recent.product_id}</span>
                </figcaption>
                <img src={figureAssets.panels.recent_ndvi} alt="Recent-observation NDVI map, masked to the selected forest boundary and valid pixels." />
              </figure>
              <figure>
                <figcaption>
                  <strong>(d) NDVI difference · recent minus previous</strong>
                  <span>Negative: potential decline · near zero: little change · positive: increase</span>
                </figcaption>
                <img src={figureAssets.panels.ndvi_difference} alt="NDVI difference map calculated as recent minus previous, masked to common valid pixels inside the forest boundary." />
              </figure>
            </div>
            {detail.figure?.ndvi_scale && (
              <div className="satellite-scientific-ndvi-legend" aria-label="Shared NDVI classes for panels b and c">
                <strong>Shared NDVI classes (same colours and boundaries in panels b and c)</strong>
                <div>
                  {detail.figure.ndvi_scale.labels.map((label, index) => (
                    <span key={label}>
                      <i style={{ backgroundColor: detail.figure.ndvi_scale.colors[index] }} aria-hidden="true" />
                      {label}
                    </span>
                  ))}
                </div>
              </div>
            )}
            {detail.figure?.difference_scale && (() => {
              // The legend must state the stretch the panel was actually drawn
              // with, not the observed extreme, or the colours read wrongly.
              const scale = detail.figure.difference_scale;
              const displayed = Number(
                scale.display_maximum_absolute_difference ?? scale.maximum_absolute_valid_difference,
              );
              const saturated = Number(scale.saturated_pixels ?? 0);
              const validPixels = Number(scale.valid_pixels ?? 0);
              return (
                <div className="satellite-scientific-difference-legend" aria-label="NDVI difference legend">
                  <strong>NDVI difference (recent − previous)</strong>
                  <div
                    className="satellite-scientific-difference-gradient"
                    style={displayed === 0 ? { background: "#f7f7f7" } : undefined}
                    aria-hidden="true"
                  />
                  <div>
                    {displayed === 0 ? (
                      <span>0 · all valid pixels show no measured difference</span>
                    ) : (
                      <>
                        <span>{saturated ? "≤ −" : "−"}{displayed.toFixed(4)} · potential decline</span>
                        <span>0 · little change</span>
                        <span>{saturated ? "≥ +" : "+"}{displayed.toFixed(4)} · increase</span>
                      </>
                    )}
                  </div>
                  <small>
                    {scale.display_percentile
                      ? `Stretched to the ${scale.display_percentile}th percentile of |difference| so a few extreme pixels cannot flatten the map. `
                      : "Scale uses the observed maximum absolute valid difference. "}
                    {saturated && validPixels
                      ? `${saturated.toLocaleString()} of ${validPixels.toLocaleString()} valid pixels fall beyond it and are drawn saturated. `
                      : ""}
                    The stored raster retains every original value.
                  </small>
                </div>
              );
            })()}
            <p className="satellite-comparison-note">
              All maps are clipped to the registered forest boundary. Cloud, shadow, nodata, and other invalid pixels are omitted under the existing quality masks. NDVI decline indicates potential vegetation change; it is not definitive proof of deforestation.
            </p>
          </>
        ) : figureError ? (
          <div className="satellite-comparison-error" role="alert">{figureError}</div>
        ) : (
          <div className="satellite-comparison-status" role="status">Loading the validated four-panel figure…</div>
        )}
      </section>

      <div className={`satellite-comparison-observation-maps ${comparisonLayoutClass(mode)}`}>
        <div className="satellite-comparison-panel satellite-comparison-previous">
          <span className="satellite-map-caption">Previous · {titleDate(previous.acquisition_date)}</span>
          <div className="satellite-comparison-map" ref={previousTargetRef} />
        </div>
        <div
          className="satellite-comparison-panel satellite-comparison-recent"
          style={mode === COMPARISON_MODES.SWIPE ? { clipPath: swipeClipPath(swipe) } : undefined}
        >
          <span className="satellite-map-caption">Recent · {titleDate(recent.acquisition_date)}</span>
          <div className="satellite-comparison-map" ref={recentTargetRef} />
        </div>
        {mode === COMPARISON_MODES.SWIPE && (
          <div className="satellite-swipe-control" ref={swipeAreaRef}>
            {/*
              The divider is the control, rather than a
              transparent slider laid over the middle of the
              map. It spans the full height of the seam, so it
              can be grabbed anywhere along it, and it is
              positioned against the same box the clip path
              measures, so the white line stays under the
              pointer instead of drifting toward the edges.
            */}
            <div
              className="satellite-swipe-divider"
              style={{ left: `${revealPercent}%` }}
              role="slider"
              tabIndex={0}
              aria-label="Swipe reveal position"
              aria-orientation="vertical"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(revealPercent)}
              aria-valuetext={`Recent observation revealed across ${Math.round(revealPercent)}% of the view`}
              onPointerDown={handleSwipePointerDown}
              onPointerMove={handleSwipePointerMove}
              onPointerUp={handleSwipePointerRelease}
              onPointerCancel={handleSwipePointerRelease}
              onKeyDown={handleSwipeKeyDown}
            >
              <span className="satellite-swipe-grip" aria-hidden="true" />
            </div>
          </div>
        )}
      </div>

      <div className="satellite-comparison-panel satellite-comparison-change-panel">
        <div className="satellite-change-heading">
          <div>
            <strong>Panel C · {isNdviChange ? "NDVI vegetation change" : "Persistence candidates"}</strong>
            <span>{isNdviChange ? "Recent NDVI minus previous NDVI" : "Existing threshold-based candidate layer"}</span>
          </div>
          <label className="satellite-change-select">Change map
            <select value={changeLayer} onChange={(event) => setChangeLayer(event.target.value)}>
              <option value={SELECTED_COMPARISON_LAYERS.NDVI_DIFFERENCE}>NDVI change</option>
              <option value={SELECTED_COMPARISON_LAYERS.PERSISTENCE_CANDIDATES}>Persistence candidates</option>
            </select>
          </label>
        </div>
        <div className="satellite-comparison-map" ref={changeTargetRef} />
        {isNdviChange ? (
          <div className="satellite-comparison-legend" aria-label="NDVI change legend">
            <div className="satellite-comparison-legend-labels">
              <span>Decline · negative</span>
              <span>Little change · 0</span>
              <span>Increase · positive</span>
            </div>
            <div className="satellite-ndvi-change-gradient" aria-hidden="true" />
          </div>
        ) : (
          <p className="satellite-comparison-note">Red pixels meet the existing persistence threshold and remain candidates for field review.</p>
        )}
      </div>

      <div className="satellite-comparison-metrics">
        <p className="satellite-comparison-summary">
          Mean NDVI across {detail.valid_comparison_pixels} common clear pixels: previous {formatComparisonMeanNdvi(detail.mean_previous_ndvi)}, recent {formatComparisonMeanNdvi(detail.mean_recent_ndvi)}; mean change (recent minus previous) {formatComparisonMeanNdvi(detail.mean_ndvi_change)}.
        </p>
        <p className="satellite-comparison-summary">
          Potential vegetation-decline area inside this boundary: {Number(detail.affected_area_hectares || 0).toFixed(2)} ha
          ({detail.confirmed_pixels} candidate pixels from {detail.valid_comparison_pixels} valid paired pixels).
        </p>
      </div>
      <p className="satellite-comparison-note">
        Red means NDVI declined (negative recent-minus-previous values), pale means little change, and green means NDVI increased. Transparent pixels are outside the selected forest boundary or excluded by the Sentinel-2 quality masks. NDVI decline indicates potential vegetation change and is not by itself confirmed deforestation.
      </p>
    </section>
  );
}
