/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Dashboard Page
 *
 * Purpose:
 *   The screen an officer opens first. Summarises the state
 *   of forest monitoring across the area they are responsible
 *   for, and shows it on a map.
 *
 * Responsibilities:
 *   - Report headline counts: forest areas, detections,
 *     alerts and imagery held.
 *   - Draw the monitored province with detections on it.
 *   - Offer Sentinel-2 true colour, false colour and NDVI.
 *   - List the most recent detections and alerts.
 *   - Compare districts, for provincial officers and
 *     administrators only.
 *
 * How it works:
 *
 *   Everything shown here is already scoped by the server.
 *   A district officer's counts cover their district alone,
 *   because the repository layer filters before counting.
 *   This page performs no filtering of its own and must not
 *   start doing so.
 *
 *   The map, and why it has three sources
 *   -------------------------------------
 *   Base layer, from Esri. Cached tiles, drawn in under a
 *   second, no credential and no quota. It is always present
 *   so the map never shows an empty canvas.
 *
 *   Sentinel-2, through the server's authenticated Copernicus
 *   proxy. Rendered on request rather than served from a tile
 *   cache, so a single view costs four to five seconds. It is
 *   therefore selected deliberately, not loaded by default.
 *
 *   Place names and boundaries, from Esri, drawn over the
 *   imagery. Without them a satellite view of the Copperbelt
 *   at province zoom is undifferentiated miombo: an officer
 *   cannot tell Kitwe from Ndola or see which district a
 *   clearing falls in.
 *
 *   The scene summary panel
 *   -----------------------
 *   The acquisition date and cloud figure come from a
 *   secondary catalogue lookup. That lookup is the only part
 *   of this screen that can fail on its own, and when it does
 *   the map is unaffected, so the failure is reported as a
 *   notice along the top edge rather than as a panel covering
 *   the map.
 *
 * Note on imagery and OpenStreetMap:
 *   The base layers are Esri, not OpenStreetMap. The map
 *   exists to show vegetation, and a road map is the wrong
 *   base layer for that; the street option is provided only
 *   for judging whether a detection can be reached on a field
 *   visit.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  AlertTriangle,
  BellRing,
  CheckCircle2,
  Clock3,
  Leaf,
  Map as MapIcon,
  RefreshCw,
  Satellite,
  Search,
  SendHorizontal,
  TreePine,
  X,
  XCircle,
} from "lucide-react";

import {
  CircleMarker,
  MapContainer,
  Polygon,
  Popup,
  ScaleControl,
  TileLayer,
  WMSTileLayer,
  ZoomControl,
  useMap,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";

import api from "../services/api";
import { TOKEN_KEY } from "../services/auth";
import {
  satelliteSignature,
  shouldReloadImagery,
} from "../services/dashboardUpdates";
import { formatZambiaShortTime } from "../services/zambiaTime";
import CloudMonitoringCard from "../components/CloudMonitoringCard";


import { API_URL as CONFIG_API_URL } from "../config";
// ---------------------------------------------------------
// Imagery source
//
// Requests go to this system's own proxy rather than to
// Copernicus directly, so the Sentinel Hub instance
// identifier stays on the server.
// ---------------------------------------------------------

const API_URL = CONFIG_API_URL;

/**
 * Return the stored access token.
 *
 * Read at render time rather than captured once, so a map
 * drawn after signing back in uses the current token.
 *
 * @returns {string}
 */
function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

/**
 * Imagery layers offered on the dashboard map.
 *
 * Esri is the default because it is fast. Sentinel Hub
 * renders each view on demand and a single request measured
 * around twenty seconds against this instance, while an
 * Esri tile returns in well under one. Waiting twenty
 * seconds after every pan made the map feel broken.
 *
 * The Sentinel-2 layers stay, because they are what the
 * analysis is actually based on and NDVI is the only layer
 * that shows vegetation loss directly. They are opt-in
 * rather than default: chosen deliberately, for one view,
 * rather than paid for on every movement of the map.
 *
 * The Sentinel-2 names must match the layers configured in
 * the Sentinel Hub instance the server proxies to.
 */
const BASE_IMAGERY = {
  id: "esri",
  label: "Satellite",
  help:
    "High-resolution satellite imagery. Fast, and always " +
    "available.",
};

const STREET_IMAGERY = {
  id: "street",
  label: "Street map",
  help:
    "Roads, towns and place names, for working out where a " +
    "forest area actually is and how to reach it.",
};

// Esri street basemap. A different provider from
// OpenStreetMap, and consistent with the satellite imagery
// already in use, so one attribution covers the map.
const ESRI_STREET_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/" +
  "World_Street_Map/MapServer/tile/{z}/{y}/{x}";

// Transparent overlay of boundaries and place names. Drawn
// ON TOP of imagery so an officer can read where they are
// without giving up the view of the vegetation, which is
// the point of the map.
const ESRI_LABELS_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/" +
  "Reference/World_Boundaries_and_Places/MapServer/" +
  "tile/{z}/{y}/{x}";

const SENTINEL_LAYERS = [
  {
    id: "1_TRUE_COLOR",
    label: "Sentinel true colour",
    help:
      "Natural colour from Sentinel-2. Slower to draw: " +
      "each view is rendered on request.",
  },
  {
    id: "2_FALSE_COLOR",
    label: "Sentinel false colour",
    help:
      "Near-infrared. Healthy vegetation is bright red, " +
      "cleared ground is pale.",
  },
  {
    id: "3_NDVI",
    label: "NDVI",
    help:
      "Vegetation index. This is the layer that shows " +
      "vegetation loss directly.",
  },
];

const IMAGERY_OPTIONS = [
  BASE_IMAGERY,
  STREET_IMAGERY,
  ...SENTINEL_LAYERS,
];

/**
 * Report whether a layer comes from Sentinel Hub.
 *
 * Those layers need an access token and are rendered on
 * request; the Esri layers need neither.
 *
 * @param {string} layerId
 * @returns {boolean}
 */
function isSentinelLayer(layerId) {
  return SENTINEL_LAYERS.some(
    (layer) => layer.id === layerId
  );
}

// Esri World Imagery: plain tiles, no key, no proxy and no
// per-request quota, which is what makes it dependable as
// the layer the map falls back to.
const ESRI_IMAGERY_URL =
  "https://services.arcgisonline.com/ArcGIS/rest/services/" +
  "World_Imagery/MapServer/tile/{z}/{y}/{x}";


const DEFAULT_CENTER = [
  -12.50,
  28.25,
];


/*
  How often the dashboard asks for new figures.

  Sentinel-2 revisits the Copperbelt about every five days,
  so the imagery itself does not change minute to minute.
  What does change on that scale is this system's own work
  on it: a product finishing downloading, a queued analysis
  completing, and the detections that analysis writes. A
  minute is short enough that an officer watching a job
  finish sees the result without reaching for Refresh, and
  long enough that a dashboard left open all day costs about
  sixty requests an hour against one small summary endpoint.
*/
const AUTO_REFRESH_INTERVAL_MS = 60000;


/*
  How many refreshes may fail in a row before automatic
  updating stops.

  A dashboard that keeps polling a backend that is down
  turns one outage into a flood of requests, and an officer
  is better told that the figures have stopped updating than
  left reading figures that quietly stopped.
*/
const AUTO_REFRESH_FAILURE_LIMIT = 4;


function SentinelMapView({ sentinel }) {
  const map = useMap();

  /*
    Whether the officer has moved the map themselves.

    The map is drawn immediately and the scene summary
    arrives a second or two later, so without this the view
    would be re-centred under the hands of anyone who had
    already started panning. A map that moves on its own
    while being read is worse than one centred slightly off
    the newest scene.

    Only drag and wheel are watched. fitBounds raises
    movestart and zoomstart itself, so listening for those
    would make the map count its own correction as an
    interaction.
  */
  const officerMovedMap = useRef(false);

  useEffect(() => {
    const remember = () => {
      officerMovedMap.current = true;
    };

    map.on("dragstart", remember);
    map.on("wheel", remember);

    return () => {
      map.off("dragstart", remember);
      map.off("wheel", remember);
    };
  }, [map]);

  useEffect(() => {
    if (
      officerMovedMap.current
    ) {
      return;
    }

    if (
      !sentinel ||
      !Array.isArray(sentinel.bounds) ||
      sentinel.bounds.length !== 4
    ) {
      return;
    }

    const west = Number(
      sentinel.bounds[0]
    );

    const south = Number(
      sentinel.bounds[1]
    );

    const east = Number(
      sentinel.bounds[2]
    );

    const north = Number(
      sentinel.bounds[3]
    );

    if (
      [
        west,
        south,
        east,
        north,
      ].some(Number.isNaN)
    ) {
      return;
    }

    map.fitBounds(
      [
        [south, west],
        [north, east],
      ],
      {
        padding: [30, 30],
        maxZoom: 11,
        animate: false,
      }
    );
  }, [map, sentinel]);

  return null;
}


/**
 * Keep the Leaflet viewport the size of its container.
 *
 * The map panel is stretched by the dashboard grid to the
 * height of the panels beside it, so the container can
 * change size after Leaflet has measured it — when the
 * summary figures arrive and alter the height of the column
 * next to the map, for instance. Leaflet watches the window
 * for resizes but not its own container, and a container
 * that grew underneath it leaves the imagery drawn for the
 * size it had before.
 */
function MapFillsContainer() {
  const map = useMap();

  useEffect(() => {
    if (
      typeof ResizeObserver ===
      "undefined"
    ) {
      return undefined;
    }

    let frame = 0;

    const observer =
      new ResizeObserver(() => {
        /*
          Coalesced into one call per frame. The observer can
          report several times while a grid row settles, and
          each invalidateSize redraws every visible tile.
        */
        cancelAnimationFrame(frame);

        frame = requestAnimationFrame(
          () => {
            map.invalidateSize({
              animate: false,
            });
          }
        );
      });

    observer.observe(
      map.getContainer()
    );

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [map]);

  return null;
}


export default function Dashboard({
  onOpenMonitoringMap,
}) {
  const [dashboard, setDashboard] =
    useState(null);

  const [forestAreas, setForestAreas] =
    useState([]);

  const [detections, setDetections] =
    useState([]);

  const [sentinel, setSentinel] =
    useState(null);

  const [loading, setLoading] =
    useState(true);

  // Which imagery layer the map is showing. Defaults to the
  // fast satellite base rather than a Sentinel-2 render.
  const [sentinelLayer, setSentinelLayer] =
    useState(BASE_IMAGERY.id);

  // Place names drawn over the imagery. On by default: a
  // detection is somewhere an officer may have to travel to,
  // and bare imagery gives no clue where that is.
  const [showLabels, setShowLabels] = useState(true);

  // Reported when an imagery layer fails, so a blank map is
  // never left unexplained.
  const [layerError, setLayerError] = useState("");

  // Whether the scene summary lookup is in flight. It
  // gates the notice in the corner of the map, never the
  // map itself.
  const [sceneLoading, setSceneLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const [mapError, setMapError] =
    useState("");

  const [sentinelError, setSentinelError] =
    useState("");

  const [refreshing, setRefreshing] =
    useState(false);

  // Set once automatic updating has given up, so the page
  // can say so rather than appear current while standing
  // still. The officer can start it again.
  const [liveUpdatesPaused, setLiveUpdatesPaused] =
    useState(false);

  // Consecutive failed background refreshes, and the last
  // state of the data the map and scene were drawn from.
  // Both are refs: neither should cause a render on its own,
  // and the poller needs to read them without being rebuilt
  // every time they change.
  const autoRefreshFailuresRef = useRef(0);

  const dataSignatureRef = useRef(null);

  // Changes when new satellite imagery lands. Held as state
  // rather than only in the ref above because the cloud card
  // has to re-render on it; the ref exists to compare
  // signatures without causing one.
  const [satelliteStamp, setSatelliteStamp] = useState(null);


  // Which detection status the officer is looking at, and a
  // forest-area name to narrow it further. Both are held on
  // the page: see the note over the derived lists below.
  const [statusFilter, setStatusFilter] =
    useState("ALL");

  const [areaQuery, setAreaQuery] =
    useState("");

  // The moment the summary figures last arrived. Set only
  // on a successful response, so a failed refresh does not
  // make stale figures look current.
  const [lastUpdated, setLastUpdated] =
    useState(null);


  /**
   * Load the summary figures.
   *
   * A silent load is a background refresh: it shows no
   * spinner and, if it fails, neither reports an error nor
   * disturbs the figures already on screen. It returns the
   * data so the caller can see whether anything changed,
   * and null if the request failed.
   */
  const loadDashboard =
    useCallback(async ({
      silent = false,
    } = {}) => {
      try {
        if (!silent) {
          setLoading(true);
          setError("");
        }

        const response =
          await api.get(
            "/dashboard"
          );

        setDashboard(
          response.data
        );

        setLastUpdated(
          new Date()
        );

        return response.data;
      } catch (err) {
        console.error(
          "Dashboard error:",
          err
        );

        /*
          A failed background refresh replaces nothing. The
          figures already on screen stay, and lastUpdated is
          deliberately left alone so the timestamp ages in
          view: an officer can see for themselves that what
          they are reading is no longer current, which is
          more use than an error over figures that are still
          broadly right.
        */
        if (!silent) {
          setError(
            "Unable to load dashboard data. Please make sure the ForestWatch Zambia backend is running."
          );
        }

        return null;
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    }, []);


  const loadMapData =
    useCallback(async () => {
      try {
        setMapError("");

        const [
          forestResponse,
          detectionResponse,
        ] = await Promise.all([
          api.get(
            "/forest-areas"
          ),
          api.get(
            "/detections"
          ),
        ]);

        const forestData =
          forestResponse.data;

        const detectionData =
          detectionResponse.data;


        if (
          Array.isArray(
            forestData
          )
        ) {
          setForestAreas(
            forestData
          );
        } else if (
          Array.isArray(
            forestData?.items
          )
        ) {
          setForestAreas(
            forestData.items
          );
        } else if (
          Array.isArray(
            forestData?.data
          )
        ) {
          setForestAreas(
            forestData.data
          );
        } else {
          setForestAreas([]);
        }


        if (
          Array.isArray(
            detectionData
          )
        ) {
          setDetections(
            detectionData
          );
        } else if (
          Array.isArray(
            detectionData?.items
          )
        ) {
          setDetections(
            detectionData.items
          );
        } else if (
          Array.isArray(
            detectionData?.data
          )
        ) {
          setDetections(
            detectionData.data
          );
        } else {
          setDetections([]);
        }

      } catch (err) {
        console.error(
          "Map data error:",
          err
        );

        setMapError(
          "Unable to load forest monitoring data."
        );
      }
    }, []);


  const loadSentinel =
    useCallback(async () => {
      try {
        setSceneLoading(true);
        setSentinelError("");

        const response =
          await api.get(
            "/planetary/sentinel",
            {
              timeout: 60000,
            }
          );

        const data =
          response.data;


        if (
          !data ||
          !Array.isArray(
            data.tiles
          ) ||
          data.tiles.length === 0
        ) {
          throw new Error(
            "Planetary Computer did not return satellite map tiles."
          );
        }


        if (
          !Array.isArray(
            data.bounds
          ) ||
          data.bounds.length !== 4
        ) {
          throw new Error(
            "Planetary Computer did not return valid satellite image bounds."
          );
        }


        setSentinel(
          data
        );

      } catch (err) {
        console.error(
          "Sentinel-2 error:",
          err
        );

        setSentinel(
          null
        );

        setSentinelError(
          err.response?.data
            ?.detail ||
            err.message ||
            "Unable to load Sentinel-2 imagery."
        );

      } finally {
        setSceneLoading(
          false
        );
      }
    }, []);


  const refreshAll =
    async () => {
      try {
        setRefreshing(true);

        await Promise.all([
          loadDashboard(),
          loadMapData(),
          loadSentinel(),
        ]);

      } finally {
        setRefreshing(false);
      }
    };


  useEffect(() => {
    loadDashboard();
    loadMapData();
    loadSentinel();
  }, [
    loadDashboard,
    loadMapData,
    loadSentinel,
  ]);


  // =========================================================
  // AUTOMATIC UPDATING
  //
  // The figures on this page are the result of work that
  // finishes while nobody is watching: a satellite product
  // downloads, a queued analysis runs, detections are
  // written. Without this the dashboard showed whatever was
  // true when it was opened, and an officer had no way of
  // knowing new results existed except by pressing Refresh.
  //
  // Three things keep the cost of that honest:
  //
  //   Each pass asks only for the summary. The map and the
  //   scene are reloaded solely when that summary shows the
  //   underlying data has actually moved, so a quiet hour
  //   costs one small request a minute and nothing else.
  //
  //   A hidden tab is not polled at all.
  //
  //   Repeated failures stop it rather than retrying
  //   forever against a backend that is down.
  //
  // The passes are chained with a timeout rather than run
  // from an interval, so a slow response delays the next
  // request instead of letting them overlap.
  // =========================================================

  useEffect(() => {
    if (liveUpdatesPaused) {
      return undefined;
    }

    let cancelled = false;
    let timeoutId;

    function schedule() {
      if (cancelled) {
        return;
      }

      timeoutId = window.setTimeout(
        tick,
        AUTO_REFRESH_INTERVAL_MS
      );
    }

    async function tick() {
      /*
        Nothing is fetched for a dashboard nobody is looking
        at. This is checked when the request is due rather
        than by stopping the timer, so a tab returned to is
        brought up to date by the handler below without
        waiting out a further minute.
      */
      if (document.hidden) {
        schedule();
        return;
      }

      const data =
        await loadDashboard({
          silent: true,
        });

      if (cancelled) {
        return;
      }

      if (!data) {
        autoRefreshFailuresRef.current += 1;

        if (
          autoRefreshFailuresRef.current >=
          AUTO_REFRESH_FAILURE_LIMIT
        ) {
          setLiveUpdatesPaused(true);
          return;
        }

        schedule();
        return;
      }

      autoRefreshFailuresRef.current = 0;

      const signature =
        satelliteSignature(data);

      const reload =
        shouldReloadImagery(
          dataSignatureRef.current,
          signature
        );

      dataSignatureRef.current = signature;

      if (reload) {
        loadMapData();
        loadSentinel();

        // New imagery means the cloud cover recorded for
        // this district can have changed, so the cloud card
        // refetches rather than waiting out its own timer.
        setSatelliteStamp(signature);
      }

      schedule();
    }

    // Coming back to the tab asks straight away rather than
    // leaving the officer looking at figures from whenever
    // they last left it.
    const refreshOnReturn = () => {
      if (document.hidden) {
        return;
      }

      window.clearTimeout(timeoutId);
      tick();
    };

    document.addEventListener(
      "visibilitychange",
      refreshOnReturn
    );

    schedule();

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);

      document.removeEventListener(
        "visibilitychange",
        refreshOnReturn
      );
    };
  }, [
    liveUpdatesPaused,
    loadDashboard,
    loadMapData,
    loadSentinel,
  ]);


  const resumeLiveUpdates = useCallback(() => {
    autoRefreshFailuresRef.current = 0;
    setLiveUpdatesPaused(false);
  }, []);


  const statistics =
    dashboard?.statistics || {};

  const forests =
    statistics.forests || {};

  const detectionStatistics =
    statistics.detections || {};

  const alerts =
    statistics.alerts || {};

  const satelliteImages =
    statistics.satellite_images ||
    {};


  // =========================================================
  // DRILL-DOWN FILTERS
  //
  // The page already holds every detection it draws and every
  // forest area it needs to name them, so narrowing happens
  // here rather than by asking the API again. Nothing below
  // adds a request, a query parameter or an endpoint: the
  // records already fetched are simply filtered before they
  // are drawn.
  //
  // One filter feeds both the map and the table, so the two
  // can never disagree about what is being looked at.
  // =========================================================

  // Detections carry a forest area id, not its name, so the
  // name search needs the areas indexed by id. Built once per
  // change of areas rather than searched per detection.
  const forestNameById = useMemo(() => {
    const index = new Map();

    forestAreas.forEach((forest) => {
      index.set(
        Number(forest.id),
        String(forest.name || "")
      );
    });

    return index;
  }, [forestAreas]);


  const normalisedQuery =
    areaQuery.trim().toLowerCase();

  const filtersActive =
    statusFilter !== "ALL" ||
    normalisedQuery !== "";


  const matchesFilters = useCallback(
    (status, forestName) => {
      if (
        statusFilter !== "ALL" &&
        String(status || "").toUpperCase() !==
          statusFilter
      ) {
        return false;
      }

      if (!normalisedQuery) {
        return true;
      }

      return String(forestName || "")
        .toLowerCase()
        .includes(normalisedQuery);
    },
    [statusFilter, normalisedQuery]
  );


  // Drawn on the map.
  const visibleDetections = useMemo(
    () =>
      detections.filter((detection) =>
        matchesFilters(
          detection.status,
          forestNameById.get(
            Number(detection.forest_area_id)
          )
        )
      ),
    [
      detections,
      forestNameById,
      matchesFilters,
    ]
  );


  // Listed in the table. These arrive already named by the
  // dashboard endpoint, so they are matched on their own
  // forest_name rather than through the index above.
  const visibleRecentDetections = useMemo(
    () =>
      (
        dashboard?.recent_detections || []
      ).filter((detection) =>
        matchesFilters(
          detection.status,
          detection.forest_name
        )
      ),
    [dashboard, matchesFilters]
  );


  const clearFilters = useCallback(() => {
    setStatusFilter("ALL");
    setAreaQuery("");
  }, []);


  // The counts come from the dashboard endpoint, which has
  // already scoped them to the officer's jurisdiction, so a
  // chip can never advertise records they may not open.
  const statusFilterOptions = [
    {
      id: "ALL",
      label: "All",
      count:
        detectionStatistics.total_detections ??
        0,
    },
    {
      id: "PENDING",
      label: "Pending",
      count:
        detectionStatistics.pending_detections ??
        0,
    },
    {
      id: "VERIFIED",
      label: "Verified",
      count:
        detectionStatistics.verified_detections ??
        0,
    },
    {
      id: "REJECTED",
      label: "Rejected",
      count:
        detectionStatistics.rejected_detections ??
        0,
    },
  ];


  // Named from the same list the switch over the map is
  // built from, so the toolbar cannot disagree with the
  // layer being drawn.
  const activeImageryLabel =
    IMAGERY_OPTIONS.find(
      (layer) =>
        layer.id === sentinelLayer
    )?.label ||
    BASE_IMAGERY.label;


  if (
    loading &&
    !dashboard
  ) {
    return (
      <div className="dashboard-loading">
        <RefreshCw
          size={30}
          className="refresh-spin"
        />

        <strong>
          Loading ForestWatch Zambia...
        </strong>
      </div>
    );
  }


  if (
    error &&
    !dashboard
  ) {
    return (
      <div className="dashboard-error">
        <AlertTriangle
          size={30}
        />

        <div>
          <strong>
            Dashboard unavailable
          </strong>

          <p>
            {error}
          </p>

          <button
            onClick={
              refreshAll
            }
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }


  return (
    <div className="dashboard-page">

      <div className="dashboard-heading">

        <div>
          <p className="eyebrow">
            FOREST MONITORING OVERVIEW
          </p>

          <h1>
            Dashboard
          </h1>

          <p>
            Monitor forest areas,
            satellite imagery,
            potential vegetation loss
            and alerts across the
            Copperbelt Province,
            Zambia.
          </p>
        </div>


        <div className="dashboard-heading-actions">

          <button
            className="refresh-button"
            onClick={
              refreshAll
            }
            disabled={
              refreshing
            }
          >
            <RefreshCw
              size={16}
              className={
                refreshing
                  ? "refresh-spin"
                  : ""
              }
            />

            {refreshing
              ? "Refreshing..."
              : "Refresh Data"}
          </button>

          {/*
            Shown only once a request has actually succeeded.
            An invented "just now" would be worse than no
            timestamp at all, because an officer uses this to
            judge whether the figures are worth acting on.
          */}
          {lastUpdated && (
            <span className="dashboard-last-updated">
              Updated
              {" "}
              {formatZambiaShortTime(lastUpdated)}
            </span>
          )}

          {/*
            Says whether the figures are keeping themselves
            current. Without it an officer cannot tell a
            dashboard that is quiet because nothing has
            happened from one that is quiet because it
            stopped asking.
          */}
          {liveUpdatesPaused ? (
            <span className="dashboard-live is-paused">

              <i
                className="dashboard-live-dot"
                aria-hidden="true"
              />

              Updates paused

              <button
                type="button"
                className="dashboard-live-resume"
                onClick={
                  resumeLiveUpdates
                }
              >
                Resume
              </button>

            </span>
          ) : (
            <span className="dashboard-live">

              <i
                className="dashboard-live-dot"
                aria-hidden="true"
              />

              Updating automatically

            </span>
          )}

        </div>

      </div>


      <div className="statistics-grid">

        <StatCard
          title="Forest Areas"
          value={
            forests.total_forests ??
            0
          }
          subtitle={
            `${
              forests.monitored_forests ??
              0
            } monitored`
          }
          icon={
            <TreePine
              size={22}
            />
          }
        />


        <StatCard
          title="Deforestation Detections"
          value={
            detectionStatistics.total_detections ??
            0
          }
          subtitle={
            `${
              detectionStatistics.pending_detections ??
              0
            } pending verification`
          }
          icon={
            <Leaf
              size={22}
            />
          }
        />


        <StatCard
          title="Alerts"
          tone="critical"
          value={
            alerts.total_alerts ??
            0
          }
          subtitle={
            `${
              alerts.pending_alerts ??
              0
            } pending`
          }
          icon={
            <AlertTriangle
              size={22}
            />
          }
        />


        <StatCard
          title="Satellite Images"
          value={
            satelliteImages.total_images ??
            0
          }
          subtitle={
            `${
              satelliteImages.processed_images ??
              0
            } processed`
          }
          icon={
            <Satellite
              size={22}
            />
          }
        />

      </div>


      <section className="dashboard-section dashboard-map-section">

        <div className="section-heading">

          <div>

            <p className="eyebrow">
              LIVE SATELLITE MONITORING
            </p>

            <h2>
              Copperbelt Forest Monitoring Map
            </h2>

            <p>
              Latest available
              Sentinel-2 L2A imagery
              from Microsoft Planetary
              Computer.
            </p>

          </div>

          {/*
            The dashboard map is deliberately small. Field
            work is planned on the Monitoring Map page, so
            there has to be a way through to it from here.
            Navigation is App's responsibility, as it is for
            every other page.
          */}
          {onOpenMonitoringMap && (
            <button
              type="button"
              className="section-action"
              onClick={onOpenMonitoringMap}
            >
              <MapIcon
                size={15}
                aria-hidden="true"
              />

              Open Monitoring Map
            </button>
          )}

        </div>


        <div className="map-toolbar">

          <div className="map-toolbar-layer">

            <Satellite
              size={17}
              aria-hidden="true"
            />

            <strong>
              {activeImageryLabel}
            </strong>

          </div>


          {sentinel && (
            <div className="map-toolbar-scene">

              <span>
                Image:
                {" "}
                <strong>
                  Sentinel-2 L2A
                </strong>
              </span>

              <span>
                Date:
                {" "}
                <strong>
                  {formatDate(
                    sentinel.datetime
                  )}
                </strong>
              </span>

              <span>
                Cloud:
                {" "}
                <strong>
                  {Number(
                    sentinel.cloud_cover ??
                      0
                  ).toFixed(2)}
                  %
                </strong>
              </span>

            </div>
          )}

        </div>


        <div className="map-canvas">

          {/* Scene lookup and map loading run independently. */}
          {sceneLoading && (
            <div
              className="map-canvas-loading"
              role="status"
              aria-live="polite"
            >

              <RefreshCw
                size={15}
                className="refresh-spin"
                aria-hidden="true"
              />

              <div>

                <strong>
                  Checking latest scene
                </strong>

                <span>
                  Microsoft Planetary
                  Computer
                </span>

              </div>

            </div>
          )}


          {/* =================================================
              The map does not depend on the scene lookup.

              Imagery comes from the Copernicus proxy, which
              serves any extent the map asks for. The scene
              lookup is only used to centre the view on the
              most recent acquisition, so when it is
              unavailable the map still draws over the
              Copperbelt rather than disappearing.
              ================================================= */}

          <MapContainer
            center={
              sentinel?.center
                ? [
                    Number(
                      sentinel
                        .center[1]
                    ),
                    Number(
                      sentinel
                        .center[0]
                    ),
                  ]
                : DEFAULT_CENTER
            }
            zoom={10}
            minZoom={6}
            maxZoom={18}
            scrollWheelZoom={
              true
            }
            zoomControl={
              false
            }
            attributionControl={
              true
            }
            style={{
              width:
                "100%",
              height:
                "100%",
            }}
          >

            <SentinelMapView
              sentinel={
                sentinel
              }
            />


            <MapFillsContainer />


            {/* =================================================
                COPERNICUS SENTINEL-2 IMAGERY

                Served through this system's own proxy,
                which keeps the Sentinel Hub instance
                identifier on the server instead of
                exposing it in the page source.

                The token travels as a query parameter
                because a Leaflet tile layer requests
                images with plain <img> tags and cannot
                set an Authorization header.

                There is no street base layer. This map
                exists to show vegetation.
                ================================================= */}

            {sentinelLayer === BASE_IMAGERY.id && (
              <TileLayer
                key="esri-satellite"
                url={ESRI_IMAGERY_URL}
                tileSize={256}
                minZoom={0}
                maxZoom={18}
                maxNativeZoom={18}
                keepBuffer={3}
                attribution={
                  "Imagery © Esri, Maxar, Earthstar " +
                  "Geographics"
                }
              />
            )}

            {sentinelLayer === STREET_IMAGERY.id && (
              <TileLayer
                key="esri-street"
                url={ESRI_STREET_URL}
                tileSize={256}
                minZoom={0}
                maxZoom={18}
                maxNativeZoom={18}
                keepBuffer={3}
                attribution="© Esri"
              />
            )}

            {isSentinelLayer(sentinelLayer) && (
              <WMSTileLayer
                key={
                  `${sentinelLayer}-copernicus`
                }
                url={
                  `${API_URL}/api/v1/sentinel/wms`
                }
                params={{
                  LAYERS: sentinelLayer,
                  FORMAT: "image/png",
                  TRANSPARENT: false,
                  access_token: getAccessToken(),
                }}
                tileSize={512}
                minZoom={0}
                maxZoom={18}
                keepBuffer={1}
                updateWhenIdle={true}
                updateWhenZooming={false}
                attribution={
                  "Sentinel-2 © Copernicus Data Space Ecosystem"
                }
                eventHandlers={{
                  /*
                    Without this a failed tile is simply
                    blank. An expired session is the
                    common cause, and it looked
                    identical to "this layer is broken",
                    which is what made these layers seem
                    not to work at all.
                  */
                  tileerror: () =>
                    setLayerError(
                      "Sentinel-2 imagery could not be " +
                        "loaded. If you have been " +
                        "signed in a while, sign out " +
                        "and back in, then try again."
                    ),
                  tileload: () => setLayerError(""),
                }}
              />
            )}

            {/*
              Place names drawn over whichever imagery is
              selected, so the officer can tell where
              they are while still looking at vegetation.
              Pointless over the street map, which
              already carries its own labels.
            */}
            {showLabels &&
              sentinelLayer !== STREET_IMAGERY.id && (
                <TileLayer
                  key="esri-labels"
                  url={ESRI_LABELS_URL}
                  tileSize={256}
                  minZoom={0}
                  maxZoom={18}
                  maxNativeZoom={18}
                  opacity={0.9}
                  zIndex={400}
                />
              )}


            {forestAreas.map(
              (
                forest
              ) => {

                const coordinates =
                  parseGeometry(
                    forest.geometry
                  );

                if (
                  !coordinates ||
                  coordinates.length <
                    3
                ) {
                  return null;
                }

                return (
                  <Polygon
                    key={
                      `forest-${forest.id}`
                    }
                    positions={
                      coordinates
                    }
                    pathOptions={{
                      color:
                        "#16A34A",
                      weight:
                        2,
                      fillColor:
                        "#22C55E",
                      fillOpacity:
                        0.18,
                    }}
                  >

                    <Popup>

                      <strong>
                        {forest.name ||
                          `Forest Area #${forest.id}`}
                      </strong>

                      <hr />

                      <div>
                        Area:
                        {" "}
                        {Number(
                          forest.area_hectares ||
                            0
                        ).toFixed(
                          2
                        )}
                        {" "}
                        ha
                      </div>

                      {forest.district_name && (
                        <div>
                          District:
                          {" "}
                          {
                            forest.district_name
                          }
                        </div>
                      )}

                    </Popup>

                  </Polygon>
                );
              }
            )}


            {visibleDetections.map(
              (
                detection
              ) => {

                const forest =
                  forestAreas.find(
                    (
                      item
                    ) =>
                      Number(
                        item.id
                      ) ===
                      Number(
                        detection.forest_area_id
                      )
                  );

                if (
                  !forest
                ) {
                  return null;
                }

                const coordinates =
                  parseGeometry(
                    forest.geometry
                  );

                const center =
                  getPolygonCenter(
                    coordinates
                  );

                if (
                  !center
                ) {
                  return null;
                }

                return (
                  <CircleMarker
                    key={
                      `detection-${detection.id}`
                    }
                    center={
                      center
                    }
                    radius={
                      8
                    }
                    pathOptions={{
                      color:
                        "#991B1B",
                      weight:
                        2,
                      fillColor:
                        "#DC2626",
                      fillOpacity:
                        0.95,
                    }}
                  >

                    <Popup>

                      <strong>
                        Deforestation Detection
                        #
                        {
                          detection.id
                        }
                      </strong>

                      <hr />

                      <div>
                        Detected Area:
                        {" "}
                        {Number(
                          detection.detected_area_hectares ||
                            0
                        ).toFixed(
                          2
                        )}
                        {" "}
                        ha
                      </div>

                      <div>
                        Confidence:
                        {" "}
                        {formatConfidence(
                          detection.confidence_score
                        )}
                      </div>

                      <div>
                        Status:
                        {" "}
                        {
                          detection.status ||
                          "PENDING"
                        }
                      </div>

                    </Popup>

                  </CircleMarker>
                );
              }
            )}


            <ZoomControl
              position="bottomright"
            />

            <ScaleControl
              position="bottomleft"
            />

            {/* =================================================
                IMAGERY SELECTOR

                NDVI is the layer that actually shows
                vegetation loss, so it has to be
                reachable rather than buried. Rendered
                outside the Leaflet pane so it sits
                above the tiles.
                ================================================= */}

            <div className="map-layer-switch">

              {IMAGERY_OPTIONS.map((layer) => (
                <button
                  key={layer.id}
                  type="button"
                  title={layer.help}
                  className={
                    sentinelLayer === layer.id
                      ? "map-layer-option active"
                      : "map-layer-option"
                  }
                  onClick={(event) => {
                    // Leaflet would otherwise treat the
                    // click as a map interaction.
                    event.stopPropagation();
                    setSentinelLayer(layer.id);
                  }}
                >
                  {layer.label}
                </button>
              ))}

              {/*
                Separated from the imagery choices: this
                is an overlay drawn on top of whichever
                of them is selected, not an alternative
                to them.
              */}
              {sentinelLayer !== STREET_IMAGERY.id && (
                <label
                  className="map-label-toggle"
                  title={
                    "Show town and district names over " +
                    "the imagery"
                  }
                  onClick={(event) =>
                    event.stopPropagation()
                  }
                >
                  <input
                    type="checkbox"
                    checked={showLabels}
                    onChange={(event) =>
                      setShowLabels(
                        event.target.checked
                      )
                    }
                  />
                  Place names
                </label>
              )}

            </div>

            {/*
              Sentinel Hub renders each view on request,
              which takes appreciably longer than serving
              a prepared tile. Saying so removes the
              main reason the map felt broken: a long
              pause with nothing explaining it.
            */}
            {isSentinelLayer(sentinelLayer) &&
              !layerError &&
              !sentinelError && (
                <div className="map-layer-hint">
                  Sentinel-2 imagery is rendered on
                  request and may take a few seconds to
                  appear.
                </div>
              )}

            {layerError && (
              <div className="map-layer-hint error">
                {layerError}
              </div>
            )}

            {/*
              The scene lookup and the monitoring data fail
              independently of a tile request, and both
              failures were recorded and never shown, so
              either one left the map looking merely empty.
              They report here, in the same slot as a tile
              failure, so one place explains why the map is
              not showing what the officer expected.
            */}
            {sentinelError && (
              <div className="map-layer-hint error">
                {sentinelError}
              </div>
            )}

            {mapError && (
              <div className="map-layer-hint error">
                {mapError}
              </div>
            )}

          </MapContainer>


          {/*
            The scene summary used to be repeated here, in a
            panel over the top right of the map. It said
            exactly what the toolbar above the map already
            says — the product, the acquisition date and the
            cloud figure — and it sat on top of the imagery
            switch, covering the NDVI option and the place
            names toggle.

            Two copies of the same three facts, one of them
            obscuring the controls: the copy over the map is
            the one to drop.
          */}

        </div>

      </section>


      <aside className="dashboard-summary-column">

        {/* Cloud conditions first in this column: whether
            the imagery is usable is the question an officer
            asks before reading the detection counts below,
            because it decides whether those counts are
            based on anything they can see. */}
        <CloudMonitoringCard
          refreshSignal={satelliteStamp}
        />

        <StatusPanel
          title="Detection Status"
          footer={
            <DistributionBar
              total={
                detectionStatistics.total_detections ??
                0
              }
              segments={[
                {
                  label: "Verified",
                  value:
                    detectionStatistics.verified_detections ??
                    0,
                  tone: "verified",
                  active:
                    statusFilter ===
                    "VERIFIED",
                  onSelect: () =>
                    setStatusFilter(
                      "VERIFIED"
                    ),
                },
                {
                  label: "Pending",
                  value:
                    detectionStatistics.pending_detections ??
                    0,
                  tone: "pending",
                  active:
                    statusFilter ===
                    "PENDING",
                  onSelect: () =>
                    setStatusFilter(
                      "PENDING"
                    ),
                },
                {
                  label: "Rejected",
                  value:
                    detectionStatistics.rejected_detections ??
                    0,
                  tone: "rejected",
                  active:
                    statusFilter ===
                    "REJECTED",
                  onSelect: () =>
                    setStatusFilter(
                      "REJECTED"
                    ),
                },
              ]}
            />
          }
          items={[
            {
              label:
                "Total Detections",
              value:
                detectionStatistics.total_detections ??
                0,
              icon:
                <Leaf
                  size={18}
                />,
              active:
                statusFilter === "ALL",
              onSelect: () =>
                setStatusFilter("ALL"),
            },
            {
              label:
                "Pending Verification",
              value:
                detectionStatistics.pending_detections ??
                0,
              icon:
                <Clock3
                  size={18}
                />,
              active:
                statusFilter ===
                "PENDING",
              onSelect: () =>
                setStatusFilter(
                  "PENDING"
                ),
            },
            {
              label:
                "Verified",
              value:
                detectionStatistics.verified_detections ??
                0,
              icon:
                <CheckCircle2
                  size={18}
                />,
              active:
                statusFilter ===
                "VERIFIED",
              onSelect: () =>
                setStatusFilter(
                  "VERIFIED"
                ),
            },
            {
              label:
                "Rejected",
              tone: "rejected",
              value:
                detectionStatistics.rejected_detections ??
                0,
              icon:
                <XCircle
                  size={18}
                />,
              active:
                statusFilter ===
                "REJECTED",
              onSelect: () =>
                setStatusFilter(
                  "REJECTED"
                ),
            },
          ]}
        />


        <StatusPanel
          title="Alert Delivery"
          items={[
            {
              label:
                "Sent",
              value:
                alerts.sent_alerts ??
                0,
              icon:
                <SendHorizontal
                  size={18}
                />,
            },
            {
              label:
                "Pending",
              value:
                alerts.pending_alerts ??
                0,
              icon:
                <Clock3
                  size={18}
                />,
            },
            {
              label:
                "Failed",
              tone: "failed",
              value:
                alerts.failed_alerts ??
                0,
              icon:
                <XCircle
                  size={18}
                />,
            },
            {
              label:
                "Resolved",
              value:
                alerts.resolved_alerts ??
                0,
              icon:
                <CheckCircle2
                  size={18}
                />,
            },
          ]}
        />


        <StatusPanel
          title="Satellite Imagery"
          items={[
            {
              label:
                "Total Images",
              value:
                satelliteImages.total_images ??
                0,
              icon:
                <Satellite
                  size={18}
                />,
            },
            {
              label:
                "Processed",
              value:
                satelliteImages.processed_images ??
                0,
              icon:
                <CheckCircle2
                  size={18}
                />,
            },
            {
              label:
                "Latest Source",
              value:
                sentinel
                  ? "Sentinel-2"
                  : "Unavailable",
              icon:
                <Satellite
                  size={18}
                />,
            },
            {
              label:
                "Cloud Cover",
              value:
                sentinel
                  ? `${Number(
                      sentinel.cloud_cover ??
                        0
                    ).toFixed(2)}%`
                  : "—",
              icon:
                <Clock3
                  size={18}
                />,
            },
          ]}
        />

      </aside>


      <section className="dashboard-section dashboard-detections-section">

        <div className="section-heading">

          <div>

            <h2>
              Recent Deforestation
              Detections
            </h2>

            <p>
              Latest detection records
              generated by ForestWatch
              Zambia.
            </p>

          </div>

        </div>


        <DetectionFilters
          options={
            statusFilterOptions
          }
          active={statusFilter}
          onSelect={setStatusFilter}
          query={areaQuery}
          onQueryChange={setAreaQuery}
          onClear={clearFilters}
          filtersActive={filtersActive}
          showing={
            visibleDetections.length
          }
          total={detections.length}
        />


        <div className="table-container">

          <table className="dashboard-table">

            <thead>

              <tr>

                <th>
                  ID
                </th>

                <th>
                  Forest Area
                </th>

                <th>
                  Affected Area
                </th>

                <th>
                  Confidence
                </th>

                <th>
                  Status
                </th>

              </tr>

            </thead>


            <tbody>

              {visibleRecentDetections.length ? (

                visibleRecentDetections.map(
                  (
                    detection
                  ) => (

                    <tr
                      key={
                        detection.id
                      }
                    >

                      <td>
                        #
                        {
                          detection.id
                        }
                      </td>

                      <td>
                        <strong>
                          {
                            detection.forest_name ||
                            "Unknown Forest Area"
                          }
                        </strong>
                      </td>

                      <td>
                        {Number(
                          detection.detected_area_hectares ||
                            0
                        ).toFixed(
                          2
                        )}
                        {" "}
                        ha
                      </td>

                      <td>
                        {formatConfidence(
                          detection.confidence_score
                        )}
                      </td>

                      <td>
                        <StatusBadge
                          status={
                            detection.status
                          }
                        />
                      </td>

                    </tr>

                  )
                )

              ) : (

                <tr>

                  <td
                    colSpan="5"
                    className="empty-table"
                  >
                    {/*
                      An empty list because nothing was found
                      and an empty list because the filters
                      exclude everything are different
                      situations, and the officer's next move
                      differs: wait for the next analysis, or
                      widen the filter. Saying which it is
                      keeps an active filter from reading as
                      "there are no detections".
                    */}
                    {filtersActive ? (
                      <>
                        No detections match the
                        current filters.
                        {" "}
                        <button
                          type="button"
                          className="empty-table-action"
                          onClick={
                            clearFilters
                          }
                        >
                          Clear filters
                        </button>
                      </>
                    ) : (
                      "No recent detections."
                    )}
                  </td>

                </tr>

              )}

            </tbody>

          </table>

        </div>

      </section>


      <section className="dashboard-section dashboard-alerts-section">

        <div className="section-heading">

          <div>

            <h2>
              Recent Alerts
            </h2>

            <p>
              Latest alerts generated
              by the detection system.
            </p>

          </div>

        </div>


        <div className="alert-list">

          {dashboard?.recent_alerts
            ?.length ? (

            dashboard.recent_alerts.map(
              (
                alert
              ) => (

                <div
                  className="alert-row"
                  key={
                    alert.id
                  }
                >

                  <div className="alert-icon">

                    <BellRing
                      size={17}
                      aria-hidden="true"
                    />

                  </div>


                  <div className="alert-information">

                    <strong>
                      {
                        alert.title ||
                        "Deforestation Alert"
                      }
                    </strong>

                    <span>
                      Alert #
                      {
                        alert.id
                      }
                    </span>

                  </div>


                  <StatusBadge
                    status={
                      alert.priority
                    }
                  />


                  <StatusBadge
                    status={
                      alert.status
                    }
                  />

                </div>

              )
            )

          ) : (

            <div className="empty-alerts">
              No recent alerts.
            </div>

          )}

        </div>

      </section>

    </div>
  );
}


function parseGeometry(
  geometry
) {
  if (!geometry) {
    return null;
  }


  if (
    typeof geometry ===
    "object"
  ) {

    if (
      geometry.type ===
        "Polygon" &&
      Array.isArray(
        geometry.coordinates
      )
    ) {

      return geometry
        .coordinates[0]
        .map(
          ([
            lng,
            lat,
          ]) => [
            lat,
            lng,
          ]
        );
    }


    if (
      geometry.type ===
        "MultiPolygon" &&
      Array.isArray(
        geometry.coordinates
      )
    ) {

      const polygon =
        geometry.coordinates[0];

      if (
        Array.isArray(
          polygon
        ) &&
        Array.isArray(
          polygon[0]
        )
      ) {

        return polygon[0]
          .map(
            ([
              lng,
              lat,
            ]) => [
              lat,
              lng,
            ]
          );
      }
    }

    return null;
  }


  if (
    typeof geometry !==
    "string"
  ) {
    return null;
  }


  try {

    const polygonMatch =
      geometry.match(
        /POLYGON\s*\(\((.*?)\)\)/i
      );

    if (
      polygonMatch
    ) {

      return polygonMatch[1]
        .split(",")
        .map(
          (pair) => {

            const parts =
              pair
                .trim()
                .split(
                  /\s+/
                )
                .map(
                  Number
                );

            if (
              parts.length <
                2 ||
              Number.isNaN(
                parts[0]
              ) ||
              Number.isNaN(
                parts[1]
              )
            ) {
              return null;
            }

            return [
              parts[1],
              parts[0],
            ];
          }
        )
        .filter(Boolean);
    }


    return null;

  } catch {
    return null;
  }
}


function getPolygonCenter(
  coordinates
) {
  if (
    !coordinates ||
    !coordinates.length
  ) {
    return null;
  }


  let latitude = 0;
  let longitude = 0;


  coordinates.forEach(
    ([
      lat,
      lng,
    ]) => {
      latitude += lat;
      longitude += lng;
    }
  );


  return [
    latitude /
      coordinates.length,
    longitude /
      coordinates.length,
  ];
}


function formatDate(
  value
) {
  if (!value) {
    return "Unavailable";
  }


  try {
    return new Date(
      value
    ).toLocaleString();
  } catch {
    return "Unavailable";
  }
}


function formatConfidence(
  value
) {
  const number =
    Number(value);


  if (
    Number.isNaN(number)
  ) {
    return "0.0%";
  }


  if (
    number <= 1
  ) {
    return `${(
      number * 100
    ).toFixed(1)}%`;
  }


  return `${number.toFixed(
    1
  )}%`;
}


function StatCard({
  title,
  value,
  subtitle,
  icon,
  tone,
}) {
  return (
    <div className="stat-card">

      <div className="stat-card-top">

        <div className={`stat-icon${tone ? ` stat-icon--${tone}` : ""}`}>
          {icon}
        </div>

      </div>


      <p>
        {title}
      </p>


      <strong>
        {value}
      </strong>


      <span>
        {subtitle}
      </span>

    </div>
  );
}


/**
 * Status chips and a name search that narrow what the map
 * draws and what the table lists.
 *
 * The chips carry the counts the dashboard endpoint already
 * returns, so how much sits behind each one is visible
 * before it is chosen. Selecting a chip filters the records
 * already on the page; it does not navigate and it does not
 * fetch, so the figures cannot shift underneath the officer
 * while they are reading them.
 */
function DetectionFilters({
  options,
  active,
  onSelect,
  query,
  onQueryChange,
  onClear,
  filtersActive,
  showing,
  total,
}) {
  return (
    <div className="detection-filters">

      <div
        className="filter-chips"
        role="group"
        aria-label="Filter detections by status"
      >

        {options.map(
          (option) => (

            <button
              key={option.id}
              type="button"
              className={
                `filter-chip${
                  option.id === active
                    ? " is-active"
                    : ""
                }`
              }
              aria-pressed={
                option.id === active
              }
              onClick={() =>
                onSelect(option.id)
              }
            >

              {option.label}

              <span className="filter-chip-count">
                {option.count}
              </span>

            </button>

          )
        )}

      </div>


      <div className="filter-tools">

        <div className="filter-search">

          <Search
            size={15}
            aria-hidden="true"
          />

          <input
            type="search"
            value={query}
            placeholder="Search forest area"
            aria-label="Search detections by forest area name"
            onChange={(event) =>
              onQueryChange(
                event.target.value
              )
            }
          />

        </div>


        {/*
          Offered only when something is actually filtered,
          so the control is never a dead button sitting next
          to an unfiltered list.
        */}
        {filtersActive && (
          <button
            type="button"
            className="filter-clear"
            onClick={onClear}
          >

            <X
              size={14}
              aria-hidden="true"
            />

            Clear

          </button>
        )}

      </div>


      {/*
        Announced politely rather than assertively: the count
        changes on every keystroke of the search, and an
        assertive region would interrupt the officer mid-word.
      */}
      <p
        className="filter-count"
        role="status"
        aria-live="polite"
      >

        <strong>
          {showing}
        </strong>

        {" of "}

        {total}

        {total === 1
          ? " detection"
          : " detections"}

        {filtersActive
          ? " match"
          : " shown"}

      </p>

    </div>
  );
}


function StatusPanel({
  title,
  items,
  footer,
}) {
  return (
    <div className="status-panel">

      <h2>
        {title}
      </h2>


      <div className="status-items">

        {items.map(
          (
            item
          ) => {

            const content = (
              <>
                <div className="status-item-label">

                  {item.icon}

                  <span>
                    {
                      item.label
                    }
                  </span>

                </div>


                <strong>
                  {
                    item.value
                  }
                </strong>
              </>
            );

            // A row that filters is a control and is built
            // as a button, so it carries its pressed state
            // and reaches the keyboard. A row that only
            // reports a figure stays plain text rather than
            // offering an interaction that does nothing.
            if (
              typeof item.onSelect !==
              "function"
            ) {
              return (
                <div
                  className={`status-item${item.tone ? ` status-item--${item.tone}` : ""}`}
                  key={
                    item.label
                  }
                >
                  {content}
                </div>
              );
            }

            return (
              <button
                type="button"
                key={
                  item.label
                }
                className={
                  `status-item status-item-action${
                    item.tone
                      ? ` status-item--${item.tone}`
                      : ""
                  }${
                    item.active
                      ? " is-active"
                      : ""
                  }`
                }
                aria-pressed={Boolean(
                  item.active
                )}
                onClick={
                  item.onSelect
                }
              >
                {content}
              </button>
            );
          }
        )}

      </div>


      {footer}

    </div>
  );
}


/**
 * Show how a total divides between its parts.
 *
 * Drawn from counts the dashboard endpoint already returns.
 * Nothing is estimated: a zero total renders no bar at all
 * rather than an empty frame suggesting a figure is missing.
 */
function DistributionBar({
  total,
  segments,
}) {
  const sum =
    Number(total) || 0;

  if (
    sum <= 0
  ) {
    return null;
  }

  return (
    <div className="distribution">

      <div
        className="distribution-bar"
        role="img"
        aria-label={
          segments
            .map(
              (segment) =>
                `${segment.label}: ${segment.value}`
            )
            .join(", ")
        }
      >

        {segments.map(
          (segment) => {

            const share =
              (Number(
                segment.value
              ) || 0) / sum;

            if (
              share <= 0
            ) {
              return null;
            }

            const className =
              `distribution-segment ` +
              `distribution-${segment.tone}`;

            // The bar already shows how the total divides.
            // Where a segment can also select that part, it
            // becomes a button so the proportion an officer
            // is reading is the thing they can act on.
            if (
              typeof segment.onSelect !==
              "function"
            ) {
              return (
                <span
                  key={
                    segment.label
                  }
                  className={className}
                  style={{
                    width:
                      `${share * 100}%`,
                  }}
                />
              );
            }

            return (
              <button
                type="button"
                key={
                  segment.label
                }
                className={
                  `${className} ` +
                  `distribution-segment-action${
                    segment.active
                      ? " is-active"
                      : ""
                  }`
                }
                style={{
                  width:
                    `${share * 100}%`,
                }}
                title={
                  `${segment.label}: ${segment.value}`
                }
                aria-pressed={Boolean(
                  segment.active
                )}
                aria-label={
                  `Show only ` +
                  `${segment.label.toLowerCase()} ` +
                  `detections`
                }
                onClick={
                  segment.onSelect
                }
              />
            );
          }
        )}

      </div>


      <div className="distribution-key">

        {segments.map(
          (segment) => (

            <span
              key={
                segment.label
              }
              className="distribution-key-item"
            >

              <i
                className={
                  `distribution-dot ` +
                  `distribution-${segment.tone}`
                }
                aria-hidden="true"
              />

              {segment.label}
              {" "}
              <strong>
                {segment.value}
              </strong>

            </span>

          )
        )}

      </div>

    </div>
  );
}


function StatusBadge({
  status,
}) {
  const value =
    String(
      status ||
        "UNKNOWN"
    ).toUpperCase();


  return (
    <span
      className={
        `status-badge status-${value.toLowerCase()}`
      }
    >
      {value}
    </span>
  );
}
