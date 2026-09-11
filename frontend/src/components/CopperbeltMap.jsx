import {
  MapContainer,
  ImageOverlay,
  Marker,
  LayersControl,
  ScaleControl,
  ZoomControl,
  useMap,
} from "react-leaflet";

import L from "leaflet";
import {
  useEffect,
  useState,
} from "react";

import "leaflet/dist/leaflet.css";

// =========================================================
// COPPERBELT CONFIGURATION
// =========================================================

const COPPERBELT_CENTER = [
  -12.50,
  28.25,
];

const COPPERBELT_BOUNDS = [
  [-13.70, 27.20],
  [-11.70, 29.50],
];

// =========================================================
// COPERNICUS WMS
// =========================================================

const SENTINEL_WMS_URL =
  "https://sh.dataspace.copernicus.eu/ogc/wms/0a0b0bc0-5f64-4a9b-826a-28a79ef8007b";

// =========================================================
// PLACE LABEL ICON
// =========================================================

function createPlaceIcon(name) {
  return L.divIcon({
    className: "copperbelt-place-label",
    html: `
      <div>${name}</div>
    `,
    iconSize: [100, 24],
    iconAnchor: [50, 12],
  });
}

// =========================================================
// COPPERBELT PLACES
// =========================================================

const COPPERBELT_PLACES = [
  {
    name: "Chingola",
    position: [-12.52897, 27.8838],
  },
  {
    name: "Kitwe",
    position: [-12.8024, 28.2132],
  },
  {
    name: "Mufulira",
    position: [-12.5498, 28.2407],
  },
  {
    name: "Ndola",
    position: [-12.9587, 28.6366],
  },
  {
    name: "Luanshya",
    position: [-13.1367, 28.4166],
  },
  {
    name: "Kalulushi",
    position: [-12.8412, 28.0948],
  },
  {
    name: "Lufwanyama",
    position: [-13.1717, 27.4429],
  },
  {
    name: "Mpongwe",
    position: [-13.5097, 28.1557],
  },
];

// =========================================================
// BUILD SENTINEL GETMAP URL
// =========================================================

function buildSentinelUrl(
  map,
  layer,
) {
  const bounds = map.getBounds();

  const southWest = map.options.crs.project(
    bounds.getSouthWest(),
  );

  const northEast = map.options.crs.project(
    bounds.getNorthEast(),
  );

  const size = map.getSize();

  const bbox = [
    southWest.x,
    southWest.y,
    northEast.x,
    northEast.y,
  ].join(",");

  const params = new URLSearchParams({
    SERVICE: "WMS",
    VERSION: "1.1.1",
    REQUEST: "GetMap",

    LAYERS: layer,

    STYLES: "",

    FORMAT: "image/jpeg",

    TRANSPARENT: "FALSE",

    SRS: "EPSG:3857",

    BBOX: bbox,

    WIDTH: Math.min(
      Math.max(size.x, 512),
      1600,
    ).toString(),

    HEIGHT: Math.min(
      Math.max(size.y, 512),
      1000,
    ).toString(),

    MAXCC: "60",
  });

  return `${SENTINEL_WMS_URL}?${params.toString()}`;
}

// =========================================================
// SENTINEL IMAGE LAYER
// =========================================================

function SentinelImageLayer({
  layer,
  onLoading,
  onLoaded,
  onError,
}) {
  const map = useMap();

  const [
    imageUrl,
    setImageUrl,
  ] = useState(null);

  const [
    imageBounds,
    setImageBounds,
  ] = useState(null);

  useEffect(() => {
    let cancelled = false;

    const loadImage = () => {
      if (!map) {
        return;
      }

      onLoading();

      const bounds = map.getBounds();

      const url = buildSentinelUrl(
        map,
        layer,
      );

      const image = new Image();

      image.onload = () => {
        if (cancelled) {
          return;
        }

        setImageUrl(url);

        setImageBounds([
          [
            bounds.getSouth(),
            bounds.getWest(),
          ],
          [
            bounds.getNorth(),
            bounds.getEast(),
          ],
        ]);

        onLoaded();
      };

      image.onerror = () => {
        if (cancelled) {
          return;
        }

        console.error(
          "Sentinel-2 WMS image failed:",
          url,
        );

        onError();
      };

      image.src = url;
    };

    loadImage();

    return () => {
      cancelled = true;
    };
  }, [
    map,
    layer,
    onLoading,
    onLoaded,
    onError,
  ]);

  if (
    !imageUrl ||
    !imageBounds
  ) {
    return null;
  }

  return (
    <ImageOverlay
      key={imageUrl}
      url={imageUrl}
      bounds={imageBounds}
      opacity={1}
      zIndex={1}
      className="sentinel-image-overlay"
    />
  );
}

// =========================================================
// MAP REFRESH CONTROLLER
// =========================================================

function MapRefreshController({
  onRefresh,
}) {
  const map = useMap();

  useEffect(() => {
    const refresh = () => {
      onRefresh();
    };

    map.on(
      "moveend",
      refresh,
    );

    map.on(
      "zoomend",
      refresh,
    );

    return () => {
      map.off(
        "moveend",
        refresh,
      );

      map.off(
        "zoomend",
        refresh,
      );
    };
  }, [
    map,
    onRefresh,
  ]);

  return null;
}

// =========================================================
// MAIN MAP
// =========================================================

export default function CopperbeltMap() {

  const [
    selectedLayer,
    setSelectedLayer,
  ] = useState(
    "1_TRUE_COLOR",
  );

  const [
    loading,
    setLoading,
  ] = useState(true);

  const [
    error,
    setError,
  ] = useState(false);

  const [
    refreshKey,
    setRefreshKey,
  ] = useState(0);

  const refreshMap = () => {
    setRefreshKey(
      (value) => value + 1,
    );
  };

  const handleLoading = () => {
    setLoading(true);
    setError(false);
  };

  const handleLoaded = () => {
    setLoading(false);
    setError(false);
  };

  const handleError = () => {
    setLoading(false);
    setError(true);
  };

  const changeLayer = (
    layer,
  ) => {
    setSelectedLayer(layer);
    setLoading(true);
    setError(false);
  };

  return (
    <section className="dashboard-section copperbelt-map-section">

      {/* =================================================
          HEADER
      ================================================= */}

      <div className="section-heading">

        <div>

          <p className="eyebrow">
            SENTINEL-2 SATELLITE MONITORING
          </p>

          <h2>
            Copperbelt Forest Monitoring Map
          </h2>

          <p>
            Current Sentinel-2 satellite
            imagery for the Copperbelt,
            Zambia.
          </p>

        </div>

      </div>


      {/* =================================================
          MAP
      ================================================= */}

      <div
        className="copperbelt-map-container"
        style={{
          position: "relative",
          width: "100%",
          height: "620px",
          overflow: "hidden",
          borderRadius: "12px",
          background: "#d9dde0",
        }}
      >

        <MapContainer
          center={COPPERBELT_CENTER}
          zoom={9}
          minZoom={8}
          maxZoom={16}
          maxBounds={COPPERBELT_BOUNDS}
          maxBoundsViscosity={1}
          scrollWheelZoom={true}
          zoomControl={false}
          style={{
            width: "100%",
            height: "100%",
          }}
        >

          {/* =================================================
              SENTINEL IMAGE
          ================================================= */}

          <SentinelImageLayer
            key={`${selectedLayer}-${refreshKey}`}
            layer={selectedLayer}
            onLoading={handleLoading}
            onLoaded={handleLoaded}
            onError={handleError}
          />


          {/* =================================================
              REFRESH WHEN MAP MOVES
          ================================================= */}

          <MapRefreshController
            onRefresh={refreshMap}
          />


          {/* =================================================
              PLACE NAMES
          ================================================= */}

          <LayersControl.Overlay
            checked
            name="Place Names"
          >

            <>
              {COPPERBELT_PLACES.map(
                (place) => (

                  <Marker
                    key={place.name}
                    position={place.position}
                    icon={createPlaceIcon(
                      place.name,
                    )}
                    interactive={false}
                    zIndexOffset={1000}
                  />

                ),
              )}
            </>

          </LayersControl.Overlay>


          {/* =================================================
              CONTROLS
          ================================================= */}

          <ZoomControl
            position="bottomright"
          />

          <ScaleControl
            position="bottomleft"
          />

        </MapContainer>


        {/* =================================================
            SENTINEL STATUS
        ================================================= */}

        <div
          className="map-information-panel"
          style={{
            position: "absolute",
            left: "15px",
            top: "15px",
            zIndex: 1000,
          }}
        >

          <div className="map-status">

            <span
              className={
                loading
                  ? "map-status-dot loading"
                  : "map-status-dot"
              }
            />

            <span>
              {loading
                ? "Loading Sentinel-2"
                : "Live Sentinel-2"}
            </span>

          </div>

          <div className="map-region">

            <strong>
              Copperbelt, Zambia
            </strong>

            <span>
              Latest available satellite imagery
            </span>

          </div>

        </div>


        {/* =================================================
            SENTINEL LAYER SELECTOR
        ================================================= */}

        <div
          className="sentinel-layer-selector"
          style={{
            position: "absolute",
            top: "15px",
            right: "55px",
            zIndex: 1000,
          }}
        >

          <div className="sentinel-layer-title">
            Sentinel-2 Layers
          </div>


          <button
            type="button"
            className={
              selectedLayer ===
              "1_TRUE_COLOR"
                ? "active"
                : ""
            }
            onClick={() =>
              changeLayer(
                "1_TRUE_COLOR",
              )
            }
          >
            True Color
          </button>


          <button
            type="button"
            className={
              selectedLayer ===
              "2_FALSE_COLOR"
                ? "active"
                : ""
            }
            onClick={() =>
              changeLayer(
                "2_FALSE_COLOR",
              )
            }
          >
            False Color
          </button>


          <button
            type="button"
            className={
              selectedLayer ===
              "3_NDVI"
                ? "active"
                : ""
            }
            onClick={() =>
              changeLayer(
                "3_NDVI",
              )
            }
          >
            NDVI
          </button>

        </div>


        {/* =================================================
            ERROR
        ================================================= */}

        {error && (

          <div
            className="sentinel-map-error"
          >

            <div className="error-icon">
              ⚠
            </div>

            <strong>
              Sentinel-2 imagery could not be loaded.
            </strong>

            <span>
              Copernicus did not return
              imagery for this request.
            </span>

            <button
              type="button"
              onClick={refreshMap}
            >
              Retry
            </button>

          </div>

        )}

      </div>

    </section>
  );
}