/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Forest Monitoring Map
 *
 * Purpose:
 *   Draws one forest area over satellite imagery with the
 *   NDVI layers produced for it, and reports the values
 *   under a clicked point.
 *
 * Responsibilities:
 *   - Zoom to the selected forest area and outline it.
 *   - Draw a chosen NDVI layer as a georeferenced overlay.
 *   - Offer a layer control over the layers that exist.
 *   - Report the readings under a clicked coordinate.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 *
 * Note:
 *   OpenLayers, not Leaflet. The overlays are rasters in a
 *   projected coordinate system drawn over a web-mercator
 *   base map, which needs native reprojection and extent
 *   handling, and the project standard records that
 *   decision.
 *
 *   The overlay arrives as a coloured PNG with its bounds.
 *   All raster work happens in the backend: a Sentinel-2
 *   tile is roughly 480 MB as float32, and nothing of that
 *   size reaches the browser.
 *
 *   The base map is Esri imagery. That is a BACKDROP, not
 *   the imagery the vegetation analysis was run on, and the
 *   legend says so. Confusing the two would let an officer
 *   read the basemap's trees as evidence about the analysis
 *   date.
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
import Static from "ol/source/ImageStatic";
import XYZ from "ol/source/XYZ";
import GeoJSON from "ol/format/GeoJSON";
import { transformExtent, toLonLat } from "ol/proj";
import { Fill, Stroke, Style } from "ol/style";

import { API_V1 } from "../config";

const ESRI_IMAGERY =
  "https://server.arcgisonline.com/ArcGIS/rest/services/" +
  "World_Imagery/MapServer/tile/{z}/{y}/{x}";

const ESRI_LABELS =
  "https://server.arcgisonline.com/ArcGIS/rest/services/" +
  "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";

export default function ForestMonitoringMap({
  forestAreaId,
  layers,
  activeLayer,
  boundary,
  imageryBounds,
  opacity = 0.85,
  onSample,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const overlayRef = useRef(null);
  const boundaryRef = useRef(null);

  const [sampling, setSampling] = useState(false);

  const token = () =>
    localStorage.getItem("access_token") ||
    localStorage.getItem("token");

  // =======================================================
  // MAP CREATION
  //
  // Created once. Later changes swap sources on the
  // existing layers rather than rebuilding the map, so the
  // officer's pan and zoom survive a layer change.
  // =======================================================

  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;

    const boundaryLayer = new VectorLayer({
      source: new VectorSource(),
      style: new Style({
        stroke: new Stroke({
          color: "#f8fafc",
          width: 2.5,
        }),
        fill: new Fill({
          color: "rgba(255, 255, 255, 0.04)",
        }),
      }),
      properties: { name: "boundary" },
    });

    const overlay = new ImageLayer({
      properties: { name: "ndvi" },
      opacity,
    });

    const map = new Map({
      target: containerRef.current,
      layers: [
        new TileLayer({
          source: new XYZ({
            url: ESRI_IMAGERY,
            attributions: "Imagery © Esri",
            maxZoom: 19,
          }),
        }),
        overlay,
        boundaryLayer,
        new TileLayer({
          source: new XYZ({
            url: ESRI_LABELS,
            attributions: "Boundaries and places © Esri",
            maxZoom: 19,
          }),
        }),
      ],
      view: new View({
        center: [3140000, -1440000],
        zoom: 8,
      }),
    });

    mapRef.current = map;
    overlayRef.current = overlay;
    boundaryRef.current = boundaryLayer;

    return () => {
      map.setTarget(undefined);
      mapRef.current = null;
    };
  }, [opacity]);

  // =======================================================
  // BOUNDARY AND ZOOM
  // =======================================================

  useEffect(() => {
    const map = mapRef.current;
    const layer = boundaryRef.current;

    if (!map || !layer) return;

    const source = layer.getSource();

    source.clear();

    if (!boundary) return;

    const features = new GeoJSON().readFeatures(
      { type: "Feature", geometry: boundary, properties: {} },
      {
        dataProjection: "EPSG:4326",
        featureProjection: "EPSG:3857",
      }
    );

    source.addFeatures(features);

    // Fit the boundary rather than the imagery. The imagery
    // covers a whole Sentinel-2 tile, roughly 110 km square,
    // and fitting that would leave the forest area a speck.
    const extent = source.getExtent();

    if (extent && Number.isFinite(extent[0])) {
      map.getView().fit(extent, {
        padding: [40, 40, 40, 40],
        maxZoom: 15,
        duration: 400,
      });
    }
  }, [boundary]);

  // =======================================================
  // OVERLAY
  // =======================================================

  useEffect(() => {
    const overlay = overlayRef.current;

    if (!overlay) return;

    if (!activeLayer || !imageryBounds) {
      overlay.setSource(null);
      return;
    }

    const available = layers?.find(
      (one) => one.key === activeLayer
    );

    if (!available?.available) {
      overlay.setSource(null);
      return;
    }

    // The token travels in the query string because an image
    // layer fetches its URL without headers the page can set.
    const url =
      `${API_V1}/monitoring/${forestAreaId}` +
      `/overlay/${activeLayer}.png` +
      `?access_token=${encodeURIComponent(token() || "")}`;

    overlay.setSource(
      new Static({
        url,
        // Bounds arrive as WGS 84 and the view is web
        // mercator, so the extent is reprojected rather than
        // used directly.
        imageExtent: transformExtent(
          imageryBounds,
          "EPSG:4326",
          "EPSG:3857"
        ),
        projection: "EPSG:3857",
        crossOrigin: "anonymous",
      })
    );
  }, [forestAreaId, activeLayer, imageryBounds, layers]);

  useEffect(() => {
    overlayRef.current?.setOpacity(opacity);
  }, [opacity]);

  // =======================================================
  // CLICK TO SAMPLE
  // =======================================================

  useEffect(() => {
    const map = mapRef.current;

    if (!map || !forestAreaId) return;

    const handler = async (event) => {
      const [longitude, latitude] = toLonLat(
        event.coordinate
      );

      setSampling(true);

      try {
        const response = await fetch(
          `${API_V1}/monitoring/${forestAreaId}/sample` +
            `?longitude=${longitude}&latitude=${latitude}`,
          {
            headers: {
              Authorization: `Bearer ${token()}`,
            },
          }
        );

        if (!response.ok) {
          throw new Error(
            `The point could not be read (${response.status}).`
          );
        }

        onSample?.(await response.json());
      } catch (error) {
        onSample?.({
          longitude,
          latitude,
          readings: null,
          error:
            error?.message ||
            "The point could not be read.",
        });
      } finally {
        setSampling(false);
      }
    };

    map.on("singleclick", handler);

    return () => map.un("singleclick", handler);
  }, [forestAreaId, onSample]);

  return (
    <div className="monitoring-map-wrapper">
      <div
        ref={containerRef}
        className="monitoring-map"
      />

      {sampling && (
        <div className="monitoring-map-sampling">
          Reading pixel…
        </div>
      )}
    </div>
  );
}
