import {
  useCallback,
  useEffect,
  useState,
} from "react";

import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Leaf,
  RefreshCw,
  Satellite,
  TreePine,
  XCircle,
} from "lucide-react";

import {
  CircleMarker,
  MapContainer,
  Polygon,
  Popup,
  ScaleControl,
  TileLayer,
  ZoomControl,
  useMap,
} from "react-leaflet";

import "leaflet/dist/leaflet.css";

import api from "../services/api";


const DEFAULT_CENTER = [
  -12.50,
  28.25,
];


function SentinelMapView({ sentinel }) {
  const map = useMap();

  useEffect(() => {
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


export default function Dashboard() {
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

  const [mapLoading, setMapLoading] =
    useState(true);

  const [error, setError] =
    useState("");

  const [mapError, setMapError] =
    useState("");

  const [sentinelError, setSentinelError] =
    useState("");

  const [refreshing, setRefreshing] =
    useState(false);


  const loadDashboard =
    useCallback(async () => {
      try {
        setLoading(true);
        setError("");

        const response =
          await api.get(
            "/dashboard"
          );

        setDashboard(
          response.data
        );
      } catch (err) {
        console.error(
          "Dashboard error:",
          err
        );

        setError(
          "Unable to load dashboard data. Please make sure the ForestWatch Zambia backend is running."
        );
      } finally {
        setLoading(false);
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
        setMapLoading(true);
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
        setMapLoading(
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


  const tileUrl =
    sentinel?.tiles?.[0] ||
    null;


  if (
    loading &&
    !dashboard
  ) {
    return (
      <div
        className="dashboard-loading"
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          gap: "12px",
        }}
      >
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
      <div
        className="dashboard-error"
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "15px",
          padding: "30px",
        }}
      >
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
    <div
      className="dashboard-page"
      style={{
        width: "100%",
        minHeight: "100vh",
      }}
    >

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
            deforestation detections
            and alerts across the
            Copperbelt, Zambia.
          </p>
        </div>


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


      <section className="dashboard-section">

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

        </div>


        <div
          style={{
            display: "flex",
            justifyContent:
              "space-between",
            alignItems:
              "center",
            flexWrap:
              "wrap",
            gap: "12px",
            padding:
              "12px 16px",
            background:
              "#ffffff",
            border:
              "1px solid #e2e8e4",
            borderBottom:
              "none",
            borderRadius:
              "12px 12px 0 0",
          }}
        >

          <div
            style={{
              display:
                "flex",
              alignItems:
                "center",
              gap: "10px",
            }}
          >

            <Satellite
              size={18}
            />

            <strong>
              Sentinel-2
            </strong>

            <select
              value="True Color"
              disabled
              style={{
                padding:
                  "7px 12px",
                border:
                  "1px solid #cbd5d1",
                borderRadius:
                  "7px",
                background:
                  "#ffffff",
              }}
            >
              <option>
                True Color
              </option>
            </select>

          </div>


          {sentinel && (
            <div
              style={{
                display:
                  "flex",
                gap:
                  "15px",
                flexWrap:
                  "wrap",
                fontSize:
                  "12px",
                color:
                  "#475569",
              }}
            >

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


        <div
          style={{
            position:
              "relative",
            width:
              "100%",
            height:
              "620px",
            background:
              "#d6d9d7",
            overflow:
              "hidden",
            borderRadius:
              "0 0 12px 12px",
          }}
        >

          {mapLoading && (
            <div
              style={{
                position:
                  "absolute",
                inset: 0,
                zIndex: 2000,
                display:
                  "flex",
                flexDirection:
                  "column",
                alignItems:
                  "center",
                justifyContent:
                  "center",
                gap: "12px",
                background:
                  "rgba(255,255,255,.92)",
              }}
            >

              <RefreshCw
                size={32}
                className="refresh-spin"
              />

              <strong>
                Loading Sentinel-2 imagery...
              </strong>

              <span
                style={{
                  fontSize:
                    "13px",
                  color:
                    "#64748b",
                }}
              >
                Microsoft Planetary
                Computer
              </span>

            </div>
          )}


          {!mapLoading &&
            sentinelError && (
              <div
                style={{
                  position:
                    "absolute",
                  inset: 0,
                  zIndex: 2000,
                  display:
                    "flex",
                  flexDirection:
                    "column",
                  alignItems:
                    "center",
                  justifyContent:
                    "center",
                  gap: "12px",
                  padding:
                    "30px",
                  textAlign:
                    "center",
                  background:
                    "#f8fafc",
                }}
              >

                <XCircle
                  size={42}
                />

                <strong>
                  Sentinel-2 imagery
                  could not be loaded
                </strong>

                <span
                  style={{
                    maxWidth:
                      "600px",
                    color:
                      "#64748b",
                  }}
                >
                  {sentinelError}
                </span>

                <button
                  className="refresh-button"
                  onClick={
                    loadSentinel
                  }
                >
                  <RefreshCw
                    size={15}
                  />

                  Try Again
                </button>

              </div>
            )}


          {!mapLoading &&
            !sentinelError &&
            tileUrl &&
            sentinel && (

              <MapContainer
                key={
                  sentinel.item_id
                }
                center={
                  sentinel.center
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


                <TileLayer
                  key={
                    `${sentinel.item_id}-visual`
                  }
                  url={
                    tileUrl
                  }
                  tileSize={
                    256
                  }
                  minZoom={
                    0
                  }
                  maxZoom={
                    18
                  }
                  maxNativeZoom={
                    18
                  }
                  keepBuffer={
                    3
                  }
                  updateWhenIdle={
                    true
                  }
                  updateWhenZooming={
                    false
                  }
                  attribution={
                    "Sentinel-2 / Microsoft Planetary Computer"
                  }
                />


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


                {detections.map(
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

              </MapContainer>
            )}


          {sentinel &&
            !sentinelError && (
              <div
                style={{
                  position:
                    "absolute",
                  top:
                    "15px",
                  right:
                    "15px",
                  zIndex:
                    1000,
                  padding:
                    "10px 14px",
                  borderRadius:
                    "8px",
                  background:
                    "rgba(255,255,255,.94)",
                  boxShadow:
                    "0 2px 8px rgba(0,0,0,.25)",
                  fontSize:
                    "12px",
                  lineHeight:
                    "1.6",
                }}
              >

                <strong>
                  Sentinel-2 L2A
                </strong>

                <br />

                Acquisition:
                {" "}
                {formatDate(
                  sentinel.datetime
                )}

                <br />

                Cloud cover:
                {" "}
                {Number(
                  sentinel.cloud_cover ??
                    0
                ).toFixed(2)}
                %

              </div>
            )}

        </div>

      </section>


      <section className="dashboard-section">

        <div className="section-heading">

          <div>

            <h2>
              Monitoring Summary
            </h2>

            <p>
              Current ForestWatch
              system status.
            </p>

          </div>

        </div>


        <div className="status-grid">

          <StatusPanel
            title="Detection Status"
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
              },
              {
                label:
                  "Rejected",
                value:
                  detectionStatistics.rejected_detections ??
                  0,
                icon:
                  <XCircle
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

        </div>

      </section>


      <section className="dashboard-section">

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


        <div className="table-container">

          <table>

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

              {dashboard?.recent_detections
                ?.length ? (

                dashboard.recent_detections.map(
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
                    No recent detections.
                  </td>

                </tr>

              )}

            </tbody>

          </table>

        </div>

      </section>


      <section className="dashboard-section">

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

                    <AlertTriangle
                      size={18}
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
}) {
  return (
    <div className="stat-card">

      <div className="stat-card-top">

        <div className="stat-icon">
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


function StatusPanel({
  title,
  items,
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
          ) => (

            <div
              className="status-item"
              key={
                item.label
              }
            >

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

            </div>

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