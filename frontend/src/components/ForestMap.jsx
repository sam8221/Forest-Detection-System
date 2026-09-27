/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Forest Map
 *
 * Purpose:
 *   Shows Copernicus Sentinel-2 imagery and lets an officer
 *   draw the area they want monitored.
 *
 * Responsibilities:
 *   - Display Sentinel-2 imagery for a chosen date.
 *   - Switch between true colour, false colour and NDVI.
 *   - Let an officer draw, redraw and clear an area.
 *   - Report the drawn area as a WKT polygon.
 *   - Draw existing forest areas and detections.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Note:
 *   Built on OpenLayers rather than Leaflet because this
 *   map needs projection handling that Leaflet does not
 *   provide natively: detections are stored in UTM Zone 35S
 *   (EPSG:32735) so their areas are measured in metres,
 *   while forest boundaries are stored in WGS84
 *   (EPSG:4326), and both are drawn over imagery served in
 *   Web Mercator.
 *
 *   There is deliberately no street map. The purpose of
 *   this map is to show vegetation, and a road base layer
 *   would show none.
 * ===========================================================
 */

import { useEffect, useRef, useState } from "react";

import "ol/ol.css";

import Map from "ol/Map";
import View from "ol/View";
import ImageLayer from "ol/layer/Image";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import VectorSource from "ol/source/Vector";
import ImageWMS from "ol/source/ImageWMS";
import XYZ from "ol/source/XYZ";
import Draw from "ol/interaction/Draw";
import WKT from "ol/format/WKT";
import { fromLonLat } from "ol/proj";

import { API_V1 } from "../config";
import { Fill, Stroke, Style } from "ol/style";
import { getArea } from "ol/sphere";

// ---------------------------------------------------------
// Constants
// ---------------------------------------------------------

const API_ROOT = API_V1;

// The Copperbelt Province, used as the opening view.
const COPPERBELT_CENTRE = [28.2, -12.8];

const DEFAULT_ZOOM = 8;

// Storage is in WGS84 because that is what the ForestArea
// geometry column uses.
const STORAGE_PROJECTION = "EPSG:4326";

const MAP_PROJECTION = "EPSG:3857";

/**
 * Sentinel-2 renderings offered as an overlay.
 *
 * The identifiers must match the layers configured in the
 * Sentinel Hub instance, which the server resolves.
 *
 * "None" is first and is the default. Sentinel-2 is drawn on
 * request rather than served as cached tiles, so a single
 * view costs four to five seconds and roughly two megabytes.
 * That is the right price to see vegetation on a specific
 * date, and the wrong price for simply finding a place on
 * the map, which is what this component is mostly used for.
 */
const SENTINEL_OVERLAYS = [
  {
    id: "",
    label: "None",
    help:
      "Base map only. Fastest, and enough for locating " +
      "an area.",
  },
  {
    id: "1_TRUE_COLOR",
    label: "Sentinel-2 true colour",
    help: "Natural colour. Vegetation appears green.",
  },
  {
    id: "2_FALSE_COLOR",
    label: "Sentinel-2 false colour",
    help:
      "Near-infrared. Healthy vegetation appears bright " +
      "red, cleared ground appears pale.",
  },
  {
    id: "3_NDVI",
    label: "NDVI",
    help:
      "Vegetation index. Darker green is denser " +
      "vegetation.",
  },
];

// ---------------------------------------------------------
// Base maps
//
// Esri rather than OpenStreetMap, consistent with the rest
// of the system, so one attribution covers the whole map.
//
// These are cached tiles: they draw in under a second, have
// no per-request cost and no dependency on this project's
// Copernicus quota. That is what makes one of them, rather
// than Sentinel-2, the layer that is always present.
// ---------------------------------------------------------

const ESRI_IMAGERY_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/" +
  "World_Imagery/MapServer/tile/{z}/{y}/{x}";

const ESRI_STREET_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/" +
  "World_Street_Map/MapServer/tile/{z}/{y}/{x}";

/**
 * Transparent overlay of place names, district boundaries
 * and main roads.
 *
 * This is the layer that makes the map answer an
 * operational question rather than merely show terrain. A
 * raw satellite view of the Copperbelt at province zoom is
 * an undifferentiated expanse of miombo: an officer cannot
 * tell Kitwe from Ndola, find the district boundary a
 * reserve sits inside, or judge which road reaches a
 * clearing. With names and boundaries drawn over the
 * imagery, all three become readable without giving up the
 * view of the vegetation underneath.
 */
const ESRI_LABELS_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/" +
  "Reference/World_Boundaries_and_Places/MapServer/" +
  "tile/{z}/{y}/{x}";

const BASE_MAPS = [
  {
    id: "satellite",
    label: "Satellite",
    url: ESRI_IMAGERY_URL,
    attribution: "Imagery © Esri",
    help: "Aerial imagery. Shows vegetation and clearings.",
  },
  {
    id: "street",
    label: "Street and terrain",
    url: ESRI_STREET_URL,
    attribution: "Map data © Esri",
    help:
      "Roads, settlements and rivers. Use when planning " +
      "how to reach an area.",
  },
];

/**
 * Load a protected image through the API.
 *
 * The imagery endpoint requires authentication, and a plain
 * image request carries no Authorization header. The image
 * is therefore fetched with the token attached and handed
 * to OpenLayers as a blob.
 *
 * Keeping the endpoint authenticated matters: it spends
 * Copernicus quota on every call, and this system is not
 * public.
 *
 * @param {object} image OpenLayers image wrapper
 * @param {string} source request URL
 */
function loadAuthenticatedImage(image, source) {
  const element = image.getImage();

  const token = localStorage.getItem("access_token");

  fetch(source, {
    headers: token
      ? { Authorization: `Bearer ${token}` }
      : {},
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Imagery request failed: ${response.status}`);
      }

      return response.blob();
    })
    .then((blob) => {
      const objectUrl = URL.createObjectURL(blob);

      // Released once the browser has decoded the image,
      // otherwise every pan would leak a blob.
      element.onload = () => URL.revokeObjectURL(objectUrl);

      element.src = objectUrl;
    })
    .catch(() => {
      // OpenLayers reports the failure through its own
      // error event; the caller surfaces it to the officer.
      element.src = "";
    });
}

/**
 * Map showing Sentinel-2 imagery with optional drawing.
 *
 * @param {object} props
 * @param {boolean} props.drawable
 *   Whether the officer may draw an area.
 * @param {string} props.value
 *   Existing area as a WKT polygon.
 * @param {Function} props.onChange
 *   Called with the drawn area as WKT, or "" when cleared.
 * @param {Array} props.forestAreas
 *   Existing forest boundaries as WKT strings.
 * @param {Array} props.detections
 *   Detection outlines as WKT strings.
 * @param {string} props.acquisitionDate
 *   Imagery date, as YYYY-MM-DD.
 * @param {number} props.height
 */
function ForestMap({
  drawable = false,
  value = "",
  onChange,
  forestAreas = [],
  detections = [],
  acquisitionDate = "",
  height = 460,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const drawSourceRef = useRef(null);
  const drawInteractionRef = useRef(null);
  const wmsSourceRef = useRef(null);

  // The last boundary this map reported upwards.
  //
  // The parent echoes that value straight back as a prop,
  // and redrawing from the echo would wipe the officer's
  // work mid-interaction. Comparing against what was sent
  // distinguishes an echo from a genuinely new boundary,
  // such as one pasted into the coordinate field, which
  // must still be drawn.
  const lastEmittedRef = useRef(null);

  // Which cached base map is drawn underneath everything.
  const [baseMapId, setBaseMapId] = useState("satellite");

  // Which Sentinel-2 rendering, if any, is drawn over it.
  // Empty means none, which is the default.
  const [layerId, setLayerId] = useState("");

  // Place names and boundaries. On by default: without them
  // the officer cannot tell which district they are looking
  // at, which is the first thing they need to know.
  const [showLabels, setShowLabels] = useState(true);

  const [drawnArea, setDrawnArea] = useState(null);

  const [imageryError, setImageryError] = useState(false);

  // Sentinel-2 takes seconds to render. Without this the map
  // simply sits unchanged and reads as broken.
  const [imageryLoading, setImageryLoading] = useState(false);

  // -------------------------------------------------------
  // Build the map once
  // -------------------------------------------------------

  useEffect(() => {
    if (!containerRef.current || mapRef.current) {
      return;
    }

    // ---------------------------------------------------
    // Copernicus Sentinel-2 imagery
    //
    // A single image per view is requested rather than
    // tiles. Sentinel Hub bills per request, and one image
    // for the visible extent costs far less than the many
    // tiles that would cover it.
    // ---------------------------------------------------

    const wmsSource = new ImageWMS({
      url: `${API_ROOT}/sentinel/wms`,
      params: {
        LAYERS: SENTINEL_OVERLAYS[1].id,
        FORMAT: "image/png",
        TRANSPARENT: false,
      },
      ratio: 1,
      imageLoadFunction: loadAuthenticatedImage,
      crossOrigin: "anonymous",
    });

    wmsSource.on("imageloadstart", () => {
      setImageryLoading(true);
      setImageryError(false);
    });

    wmsSource.on("imageloaderror", () => {
      setImageryLoading(false);
      setImageryError(true);
    });

    wmsSource.on("imageloadend", () => {
      setImageryLoading(false);
      setImageryError(false);
    });

    wmsSourceRef.current = wmsSource;

    // Starts hidden. The officer asks for Sentinel-2 when
    // they want to inspect vegetation; until then the base
    // map answers the question faster and for free.
    const sentinelLayer = new ImageLayer({
      source: wmsSource,
      visible: false,
      properties: { name: "sentinel" },
    });

    // ---------------------------------------------------
    // Base map
    //
    // Always present, underneath everything else, and never
    // switched off. Sentinel-2 imagery is rendered on
    // request and takes several seconds, so without a
    // cached base map every pan would leave the view blank
    // until the render arrived, and a failed or
    // unconfigured request would leave it blank
    // indefinitely. The base map means the officer is
    // always looking at real ground.
    // ---------------------------------------------------

    const baseLayer = new TileLayer({
      source: new XYZ({
        url: BASE_MAPS[0].url,
        attributions: BASE_MAPS[0].attribution,
        maxZoom: 19,
      }),
      properties: { name: "base" },
    });

    // Place names and boundaries, drawn above the imagery
    // so they stay readable whichever layer is beneath.
    const labelLayer = new TileLayer({
      source: new XYZ({
        url: ESRI_LABELS_URL,
        attributions: "Boundaries and places © Esri",
        maxZoom: 19,
      }),
      properties: { name: "labels" },
    });

    // ---------------------------------------------------
    // Existing forest boundaries
    // ---------------------------------------------------

    const forestSource = new VectorSource();

    const forestLayer = new VectorLayer({
      source: forestSource,
      properties: { name: "forests" },
      style: new Style({
        stroke: new Stroke({
          color: "#22c55e",
          width: 2,
        }),
        fill: new Fill({
          color: "rgba(34, 197, 94, 0.10)",
        }),
      }),
    });

    // ---------------------------------------------------
    // Detections
    //
    // Drawn in red: these are the areas where vegetation
    // was lost.
    // ---------------------------------------------------

    const detectionSource = new VectorSource();

    const detectionLayer = new VectorLayer({
      source: detectionSource,
      properties: { name: "detections" },
      style: new Style({
        stroke: new Stroke({
          color: "#dc2626",
          width: 2,
        }),
        fill: new Fill({
          color: "rgba(220, 38, 38, 0.35)",
        }),
      }),
    });

    // ---------------------------------------------------
    // The area being drawn
    // ---------------------------------------------------

    const drawSource = new VectorSource();

    drawSourceRef.current = drawSource;

    const drawLayer = new VectorLayer({
      source: drawSource,
      properties: { name: "draw" },
      style: new Style({
        stroke: new Stroke({
          color: "#f59e0b",
          width: 3,
        }),
        fill: new Fill({
          color: "rgba(245, 158, 11, 0.20)",
        }),
      }),
    });

    const map = new Map({
      target: containerRef.current,
      // Drawing order, bottom to top: cached ground, then
      // Sentinel-2 if asked for, then place names so they
      // stay legible over either, then the vectors the
      // officer works with.
      layers: [
        baseLayer,
        sentinelLayer,
        labelLayer,
        forestLayer,
        detectionLayer,
        drawLayer,
      ],
      view: new View({
        center: fromLonLat(COPPERBELT_CENTRE),
        zoom: DEFAULT_ZOOM,
        projection: MAP_PROJECTION,
      }),
    });

    mapRef.current = map;

    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
    };
  }, []);

  // -------------------------------------------------------
  // Find a layer by the name it was built with
  // -------------------------------------------------------

  const findLayer = (name) => {
    const map = mapRef.current;

    if (!map) {
      return null;
    }

    return (
      map
        .getLayers()
        .getArray()
        .find((layer) => layer.get("name") === name) || null
    );
  };

  // -------------------------------------------------------
  // Base map
  // -------------------------------------------------------

  useEffect(() => {
    const layer = findLayer("base");

    if (!layer) {
      return;
    }

    const chosen =
      BASE_MAPS.find((item) => item.id === baseMapId) ||
      BASE_MAPS[0];

    // On the first run the layer was already built with this
    // source, so replacing it would discard a set of tiles
    // the browser is still fetching and request them again.
    const current = layer.getSource()?.getUrls?.() || [];

    if (current.includes(chosen.url)) {
      return;
    }

    // The source is replaced rather than a second layer
    // being toggled, so only one set of tiles is ever
    // requested and the attribution stays correct.
    layer.setSource(
      new XYZ({
        url: chosen.url,
        attributions: chosen.attribution,
        maxZoom: 19,
      })
    );
  }, [baseMapId]);

  // -------------------------------------------------------
  // Sentinel-2 overlay
  //
  // Requested only when a rendering is selected. An empty
  // selection hides the layer without issuing a request, so
  // no Copernicus quota is spent while the officer is only
  // navigating.
  //
  // Without a date Sentinel Hub returns its most recent
  // cloud-free composite, which is rarely the date the
  // officer is looking at, so the acquisition date is passed
  // through whenever one is known.
  // -------------------------------------------------------

  useEffect(() => {
    const layer = findLayer("sentinel");

    if (!layer || !wmsSourceRef.current) {
      return;
    }

    if (!layerId) {
      layer.setVisible(false);
      setImageryError(false);
      setImageryLoading(false);
      return;
    }

    const parameters = { LAYERS: layerId };

    if (acquisitionDate) {
      parameters.TIME = acquisitionDate;
    }

    wmsSourceRef.current.updateParams(parameters);

    layer.setVisible(true);
  }, [layerId, acquisitionDate]);

  // -------------------------------------------------------
  // Place names and boundaries
  // -------------------------------------------------------

  useEffect(() => {
    const layer = findLayer("labels");

    if (layer) {
      layer.setVisible(showLabels);
    }
  }, [showLabels]);

  // -------------------------------------------------------
  // Draw existing geometry
  // -------------------------------------------------------

  useEffect(() => {
    const map = mapRef.current;

    if (!map) {
      return;
    }

    const format = new WKT();

    const paint = (layerName, wktList) => {
      const layer = map
        .getLayers()
        .getArray()
        .find((item) => item.get("name") === layerName);

      if (!layer) {
        return;
      }

      const source = layer.getSource();

      source.clear();

      wktList
        .filter(Boolean)
        .forEach((wkt) => {
          try {
            const feature = format.readFeature(wkt, {
              dataProjection: STORAGE_PROJECTION,
              featureProjection: MAP_PROJECTION,
            });

            source.addFeature(feature);
          } catch {
            // A geometry that cannot be read is skipped
            // rather than breaking the whole map.
          }
        });
    };

    paint("forests", forestAreas);
    paint("detections", detections);
  }, [forestAreas, detections]);

  // -------------------------------------------------------
  // Show an area supplied by the parent
  // -------------------------------------------------------

  useEffect(() => {
    const source = drawSourceRef.current;

    if (!source) {
      return;
    }

    // Ignore the echo of what this map just reported, but
    // accept any other change so a pasted or edited
    // boundary is still drawn.
    if (value && value === lastEmittedRef.current) {
      return;
    }

    source.clear();

    if (!value) {
      setDrawnArea(null);

      return;
    }

    try {
      const feature = new WKT().readFeature(value, {
        dataProjection: STORAGE_PROJECTION,
        featureProjection: MAP_PROJECTION,
      });

      source.addFeature(feature);

      setDrawnArea(
        getArea(feature.getGeometry()) / 10_000
      );

      const map = mapRef.current;

      if (map) {
        map.getView().fit(
          feature.getGeometry().getExtent(),
          { padding: [40, 40, 40, 40], maxZoom: 14 }
        );
      }
    } catch {
      setDrawnArea(null);
    }
  }, [value]);

  // -------------------------------------------------------
  // Drawing
  // -------------------------------------------------------

  useEffect(() => {
    const map = mapRef.current;

    const source = drawSourceRef.current;

    if (!map || !source || !drawable) {
      return;
    }

    const draw = new Draw({
      source,
      type: "Polygon",
    });

    // Only one area is monitored per forest, so a new
    // drawing replaces the previous one rather than adding
    // a second overlapping boundary.
    draw.on("drawstart", () => source.clear());

    draw.on("drawend", (event) => {
      const geometry = event.feature.getGeometry();

      // Measured on the sphere, so the figure is true
      // ground area rather than area in Web Mercator,
      // which exaggerates with distance from the equator.
      setDrawnArea(getArea(geometry) / 10_000);

      const wkt = new WKT().writeGeometry(geometry, {
        dataProjection: STORAGE_PROJECTION,
        featureProjection: MAP_PROJECTION,
      });

      lastEmittedRef.current = wkt;

      if (onChange) {
        onChange(wkt);
      }
    });

    map.addInteraction(draw);

    drawInteractionRef.current = draw;

    return () => {
      map.removeInteraction(draw);
      drawInteractionRef.current = null;
    };
  }, [drawable, onChange]);

  /**
   * Discard the drawn area.
   */
  const handleClear = () => {
    if (drawSourceRef.current) {
      drawSourceRef.current.clear();
    }

    setDrawnArea(null);

    lastEmittedRef.current = null;

    if (onChange) {
      onChange("");
    }
  };

  const activeBaseMap =
    BASE_MAPS.find((item) => item.id === baseMapId) ||
    BASE_MAPS[0];

  const activeOverlay = SENTINEL_OVERLAYS.find(
    (layer) => layer.id === layerId
  );

  return (
    <div className="forest-map">
      <div className="forest-map-toolbar">
        <label className="forest-map-control">
          <span>Base map</span>

          <select
            value={baseMapId}
            onChange={(event) =>
              setBaseMapId(event.target.value)
            }
          >
            {BASE_MAPS.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </label>

        <label className="forest-map-control">
          <span>Sentinel-2</span>

          <select
            value={layerId}
            onChange={(event) =>
              setLayerId(event.target.value)
            }
          >
            {SENTINEL_OVERLAYS.map((layer) => (
              <option key={layer.id} value={layer.id}>
                {layer.label}
              </option>
            ))}
          </select>
        </label>

        <label className="forest-map-toggle">
          <input
            type="checkbox"
            checked={showLabels}
            onChange={(event) =>
              setShowLabels(event.target.checked)
            }
          />

          <span>Place names</span>
        </label>

        {imageryLoading && (
          <span
            className="forest-map-loading"
            role="status"
            aria-live="polite"
          >
            Rendering Sentinel-2 imagery…
          </span>
        )}

        {drawable && (
          <div className="forest-map-actions">
            <span className="forest-map-hint">
              Click on the map to place each corner of the
              area. Double-click to finish.
            </span>

            <button
              type="button"
              className="secondary-button"
              onClick={handleClear}
            >
              Clear area
            </button>
          </div>
        )}
      </div>

      <div
        ref={containerRef}
        className="forest-map-canvas"
        style={{ height: `${height}px` }}
      />

      <div className="forest-map-footer">
        <span>
          {layerId
            ? activeOverlay?.help
            : activeBaseMap.help}{" "}
          {activeBaseMap.attribution}
        </span>

        {drawnArea !== null && (
          <strong>
            Selected area: {drawnArea.toFixed(2)} hectares
          </strong>
        )}
      </div>

      {/* A Sentinel-2 failure is now a lost overlay rather
          than a lost map: the base map underneath is still
          showing real ground, so the wording says what is
          missing instead of implying the map is broken. */}

      {imageryError && layerId && (
        <div className="forest-map-warning">
          Sentinel-2 imagery could not be loaded for this
          view. There may be no cloud-free acquisition for
          the selected date. The base map below it is
          unaffected — try another date, or set Sentinel-2
          to None.
        </div>
      )}
    </div>
  );
}

export default ForestMap;
