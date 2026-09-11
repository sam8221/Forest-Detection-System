import React, { useEffect, useState } from "react";
import {
  Satellite,
  RefreshCw,
  Calendar,
  Cloud,
  MapPin,
  Image as ImageIcon,
  AlertCircle,
  Search,
  CheckCircle2,
  Globe,
  Database,
} from "lucide-react";

const API_URL = "http://127.0.0.1:8000";

export default function SatelliteImages() {
  const [images, setImages] = useState([]);
  const [forestAreas, setForestAreas] = useState([]);
  const [selectedForestArea, setSelectedForestArea] = useState("");

  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [cloudCover, setCloudCover] = useState(30);
  const [searchLimit] = useState(20);

  const [products, setProducts] = useState([]);

  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [searchError, setSearchError] = useState("");

  // =========================================================
  // AUTHENTICATION
  // =========================================================

  const getToken = () => {
    return (
      localStorage.getItem("access_token") ||
      localStorage.getItem("token")
    );
  };

  const getHeaders = () => {
    const token = getToken();

    return {
      "Content-Type": "application/json",
      ...(token
        ? {
            Authorization: `Bearer ${token}`,
          }
        : {}),
    };
  };

  // =========================================================
  // DEFAULT DATES
  // =========================================================

  const getDefaultDates = () => {
    const today = new Date();

    const end = new Date(today);

    const start = new Date(today);
    start.setDate(start.getDate() - 15);

    const format = (date) =>
      date.toISOString().split("T")[0];

    return {
      start: format(start),
      end: format(end),
    };
  };

  // =========================================================
  // LOAD FOREST AREAS
  // =========================================================

  const fetchForestAreas = async () => {
    try {
      const response = await fetch(
        `${API_URL}/api/v1/forest-areas`,
        {
          method: "GET",
          headers: getHeaders(),
        }
      );

      if (!response.ok) {
        throw new Error(
          `Unable to load forest areas. Server returned ${response.status}.`
        );
      }

      const data = await response.json();

      const areas = Array.isArray(data)
        ? data
        : Array.isArray(data.items)
        ? data.items
        : [];

      setForestAreas(areas);

      if (
        areas.length > 0 &&
        !selectedForestArea
      ) {
        setSelectedForestArea(
          String(areas[0].id)
        );
      }
    } catch (err) {
      console.error(
        "Forest Areas Error:",
        err
      );
    }
  };

  // =========================================================
  // LOAD REGISTERED SATELLITE IMAGES
  // =========================================================

  const fetchSatelliteImages = async () => {
    try {
      setLoading(true);
      setError("");

      const response = await fetch(
        `${API_URL}/api/v1/satellite-images`,
        {
          method: "GET",
          headers: getHeaders(),
        }
      );

      if (!response.ok) {
        throw new Error(
          `Unable to load satellite images. Server returned ${response.status}.`
        );
      }

      const data = await response.json();

      setImages(
        Array.isArray(data) ? data : []
      );
    } catch (err) {
      console.error(
        "Satellite Images Error:",
        err
      );

      setError(
        err.message ||
          "Failed to load satellite images."
      );
    } finally {
      setLoading(false);
    }
  };

  // =========================================================
  // SEARCH SENTINEL-2
  // =========================================================

  const searchSentinelImages = async () => {
    if (!selectedForestArea) {
      setSearchError(
        "Please select a forest area first."
      );
      return;
    }

    if (!startDate || !endDate) {
      setSearchError(
        "Please select both start and end dates."
      );
      return;
    }

    if (startDate > endDate) {
      setSearchError(
        "Start date cannot be later than end date."
      );
      return;
    }

    try {
      setSearching(true);
      setSearchError("");
      setProducts([]);

      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        cloud_cover: String(cloudCover),
        limit: String(searchLimit),
      });

      const url =
        `${API_URL}/api/v1/satellite-images/forest/` +
        `${selectedForestArea}/search?${params.toString()}`;

      const response = await fetch(url, {
        method: "GET",
        headers: getHeaders(),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail ||
            `Sentinel search failed. Server returned ${response.status}.`
        );
      }

      setProducts(
        Array.isArray(data.products)
          ? data.products
          : []
      );
    } catch (err) {
      console.error(
        "Sentinel Search Error:",
        err
      );

      setSearchError(
        err.message ||
          "Unable to retrieve Sentinel-2 imagery."
      );
    } finally {
      setSearching(false);
    }
  };

  // =========================================================
  // INITIAL LOAD
  // =========================================================

  useEffect(() => {
    const dates = getDefaultDates();

    setStartDate(dates.start);
    setEndDate(dates.end);

    fetchSatelliteImages();
    fetchForestAreas();
  }, []);

  // =========================================================
  // FORMAT DATE
  // =========================================================

  const formatDate = (date) => {
    if (!date) return "—";

    try {
      return new Date(date).toLocaleDateString(
        "en-ZM",
        {
          day: "2-digit",
          month: "short",
          year: "numeric",
        }
      );
    } catch {
      return date;
    }
  };

  const formatDateTime = (date) => {
    if (!date) return "—";

    try {
      return new Date(date).toLocaleString(
        "en-ZM",
        {
          day: "2-digit",
          month: "short",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
        }
      );
    } catch {
      return date;
    }
  };

  // =========================================================
  // CLOUD COVER
  // =========================================================

  const getCloudCoverage = (product) => {
    const value =
      product.cloud_cover_percentage ??
      product.cloud_cover ??
      product.cloudCoverage;

    if (
      value === null ||
      value === undefined
    ) {
      return "—";
    }

    return `${Number(value).toFixed(1)}%`;
  };

  // =========================================================
  // SELECTED FOREST
  // =========================================================

  const selectedForest = forestAreas.find(
    (area) =>
      String(area.id) ===
      String(selectedForestArea)
  );

  // =========================================================
  // RENDER
  // =========================================================

  return (
    <div className="satellite-page">

      {/* =====================================================
          HEADER
      ===================================================== */}

      <div className="satellite-header">

        <div className="satellite-title-row">

          <div className="satellite-title-icon">
            <Satellite size={25} />
          </div>

          <div>
            <h1>Satellite Images</h1>

            <p>
              Search and manage real Sentinel-2
              satellite imagery for forest
              monitoring in the Copperbelt, Zambia.
            </p>
          </div>

        </div>

        <button
          className="refresh-button"
          onClick={() => {
            fetchSatelliteImages();
            fetchForestAreas();
          }}
          disabled={loading}
        >
          <RefreshCw
            size={16}
            className={
              loading
                ? "refresh-spinning"
                : ""
            }
          />

          {loading
            ? "Loading..."
            : "Refresh"}
        </button>

      </div>

      {/* =====================================================
          SUMMARY
      ===================================================== */}

      <div className="satellite-summary">

        <div className="satellite-summary-card">

          <div className="summary-icon">
            <ImageIcon size={20} />
          </div>

          <div>
            <span>Registered Images</span>

            <strong>{images.length}</strong>
          </div>

        </div>

        <div className="satellite-summary-card">

          <div className="summary-icon">
            <Satellite size={20} />
          </div>

          <div>
            <span>Satellite</span>

            <strong>Sentinel-2</strong>
          </div>

        </div>

        <div className="satellite-summary-card">

          <div className="summary-icon">
            <MapPin size={20} />
          </div>

          <div>
            <span>Monitoring Region</span>

            <strong>Copperbelt</strong>
          </div>

        </div>

      </div>

      {/* =====================================================
          SENTINEL SEARCH
      ===================================================== */}

      <div className="satellite-search-panel">

        <div className="satellite-search-heading">

          <div>
            <h2>
              Search Sentinel-2 Imagery
            </h2>

            <p>
              Retrieve real satellite products
              from the Copernicus Data Space.
            </p>
          </div>

          <div className="copernicus-status">
            <Globe size={15} />
            Copernicus Data Space
          </div>

        </div>

        <div className="satellite-search-form">

          {/* FOREST AREA */}

          <div className="satellite-form-group">

            <label>Forest Area</label>

            <select
              value={selectedForestArea}
              onChange={(e) =>
                setSelectedForestArea(
                  e.target.value
                )
              }
            >

              <option value="">
                Select forest area
              </option>

              {forestAreas.map(
                (area) => (
                  <option
                    key={area.id}
                    value={area.id}
                  >
                    {area.name ||
                      area.forest_code ||
                      `Forest Area #${area.id}`}
                  </option>
                )
              )}

            </select>

          </div>

          {/* START DATE */}

          <div className="satellite-form-group">

            <label>Start Date</label>

            <div className="date-input">

              <Calendar size={15} />

              <input
                type="date"
                value={startDate}
                onChange={(e) =>
                  setStartDate(
                    e.target.value
                  )
                }
              />

            </div>

          </div>

          {/* END DATE */}

          <div className="satellite-form-group">

            <label>End Date</label>

            <div className="date-input">

              <Calendar size={15} />

              <input
                type="date"
                value={endDate}
                onChange={(e) =>
                  setEndDate(
                    e.target.value
                  )
                }
              />

            </div>

          </div>

          {/* CLOUD COVER */}

          <div className="satellite-form-group">

            <label>Max Cloud Cover</label>

            <div className="cloud-input">

              <Cloud size={15} />

              <input
                type="number"
                min="0"
                max="100"
                step="1"
                value={cloudCover}
                onChange={(e) =>
                  setCloudCover(
                    Math.min(
                      100,
                      Math.max(
                        0,
                        Number(
                          e.target.value
                        )
                      )
                    )
                  )
                }
              />

              <span>%</span>

            </div>

          </div>

          {/* SEARCH */}

          <button
            className="sentinel-search-button"
            onClick={
              searchSentinelImages
            }
            disabled={searching}
          >

            {searching ? (
              <>
                <RefreshCw
                  size={17}
                  className="refresh-spinning"
                />

                Searching...
              </>
            ) : (
              <>
                <Search size={17} />

                Search Sentinel-2
              </>
            )}

          </button>

        </div>

        {searchError && (
          <div className="sentinel-search-error">

            <AlertCircle size={18} />

            <span>
              {searchError}
            </span>

          </div>
        )}

      </div>

      {/* =====================================================
          SEARCH RESULTS
      ===================================================== */}

      {products.length > 0 && (

        <div className="satellite-results-section">

          <div className="section-heading">

            <div>

              <h2>
                Sentinel-2 Search Results
              </h2>

              <p>
                Real products returned from
                Copernicus Data Space.
              </p>

            </div>

            <div className="forest-count">
              {products.length} Products
            </div>

          </div>

          <div className="satellite-table-wrapper">

            <table className="satellite-table">

              <thead>

                <tr>
                  <th>Product</th>
                  <th>Tile</th>
                  <th>Acquisition</th>
                  <th>Cloud Cover</th>
                  <th>Processing</th>
                  <th>Availability</th>
                </tr>

              </thead>

              <tbody>

                {products.map(
                  (product) => (

                    <tr
                      key={
                        product.product_id
                      }
                    >

                      <td>
                        <div className="sentinel-product">

                          <div className="sentinel-product-icon">
                            <Satellite
                              size={17}
                            />
                          </div>

                          <div>

                            <strong>
                              {product.product_name ||
                                product.name ||
                                "Sentinel-2 Product"}
                            </strong>

                            <span>
                              {product.satellite ||
                                "Sentinel-2"}
                            </span>

                          </div>

                        </div>
                      </td>

                      <td>
                        <strong>
                          <span className="tile-badge">
                            {product.tile_id ||
                              "—"}
                          </span>
                        </strong>
                      </td>

                      <td>

                        <div className="satellite-date">

                          <Calendar size={15} />

                          <span>
                            {formatDateTime(
                              product.acquisition_date
                            )}
                          </span>

                        </div>

                      </td>

                      <td>

                        <div className="cloud-coverage">

                          <Cloud size={15} />

                          <strong>
                            {getCloudCoverage(
                              product
                            )}
                          </strong>

                        </div>

                      </td>

                      <td>

                        <strong>
                          <span className="processing-badge">
                            {product.processing_level ||
                              "S2MSI2A"}
                          </span>
                        </strong>

                      </td>

                      <td>

                        {product.online ? (
                          <strong>
                            <span className="online-badge">

                              <CheckCircle2
                                size={13}
                              />

                              ONLINE

                            </span>
                          </strong>
                        ) : (
                          <strong>
                            <span className="offline-badge">
                              OFFLINE
                            </span>
                          </strong>
                        )}

                      </td>

                    </tr>

                  )
                )}

              </tbody>

            </table>

          </div>

          {selectedForest && (

            <div className="sentinel-result-info">

              <MapPin size={17} />

              <span>
                Showing Sentinel-2 products
                intersecting:

                <strong>
                  {" "}
                  {selectedForest.name ||
                    selectedForest.forest_code}
                </strong>

                {selectedForest.area_hectares && (
                  <>
                    {" "}
                    ({selectedForest.area_hectares} ha)
                  </>
                )}

              </span>

            </div>

          )}

        </div>

      )}

      {/* =====================================================
          EMPTY SEARCH
      ===================================================== */}

      {!searching &&
        products.length === 0 &&
        !searchError && (

          <div className="sentinel-empty">

            <Database size={32} />

            <h3>
              No Sentinel-2 Search Results
            </h3>

            <p>
              Select a forest area and date
              range, then click{" "}
              <strong>
                Search Sentinel-2
              </strong>{" "}
              to retrieve real imagery
              from Copernicus.
            </p>

          </div>

        )}

      {/* =====================================================
          REGISTERED IMAGES
      ===================================================== */}

      {!loading && !error && (

        <div className="registered-images-section">

          <div className="section-heading">

            <div>

              <h2>
                Registered Satellite Images
              </h2>

              <p>
                Sentinel-2 images already
                registered in ForestWatch.
              </p>

            </div>

            <div className="forest-count">
              {images.length} Images
            </div>

          </div>

          {images.length > 0 ? (

            <div className="satellite-table-wrapper">

              <table className="satellite-table">

                <thead>

                  <tr>
                    <th>ID</th>
                    <th>Satellite</th>
                    <th>Forest Area</th>
                    <th>Acquisition Date</th>
                    <th>Cloud Coverage</th>
                    <th>Status</th>
                  </tr>

                </thead>

                <tbody>

                  {images.map(
                    (image) => (

                      <tr
                        key={
                          image.id ||
                          image.image_id
                        }
                      >

                        {/* ID */}

                        <td>
                          <strong>
                            #
                            {image.id ||
                              image.image_id ||
                              "—"}
                          </strong>
                        </td>

                        {/* SATELLITE */}

                        <td>

                          <div className="satellite-name">

                            <Satellite
                              size={17}
                            />

                            <strong>
                              {image.satellite_name ||
                                image.satellite ||
                                "Sentinel-2"}
                            </strong>

                          </div>

                        </td>

                        {/* FOREST AREA */}

                        <td>

                          <div className="satellite-location">

                            <MapPin
                              size={15}
                            />

                            <strong>
                              {image.forest_name ||
                                image.forest_area_name ||
                                `Forest Area #${
                                  image.forest_area_id ||
                                  "—"
                                }`}
                            </strong>

                          </div>

                        </td>

                        {/* ACQUISITION DATE */}

                        <td>

                          <div className="satellite-date">

                            <Calendar
                              size={15}
                            />

                            <span>
                              {formatDate(
                                image.acquisition_date
                              )}
                            </span>

                          </div>

                        </td>

                        {/* CLOUD COVER */}

                        <td>

                          <div className="cloud-coverage">

                            <Cloud
                              size={15}
                            />

                            <span>
                              {image.cloud_cover_percentage !==
                              undefined
                                ? `${Number(
                                    image.cloud_cover_percentage
                                  ).toFixed(1)}%`
                                : "—"}
                            </span>

                          </div>

                        </td>

                        {/* STATUS */}

                        <td>

                          <strong>
                            <span className="satellite-status">

                              {image.is_processed
                                ? "PROCESSED"
                                : image.is_downloaded
                                ? "DOWNLOADED"
                                : "REGISTERED"}

                            </span>
                          </strong>

                        </td>

                      </tr>

                    )
                  )}

                </tbody>

              </table>

            </div>

          ) : (

            <div className="message-card">

              <div className="loading-spinner">
                <Satellite size={30} />
              </div>

              <h3>
                No Registered Images
              </h3>

              <p>
                Search Copernicus above to
                find Sentinel-2 imagery.
              </p>

            </div>

          )}

        </div>

      )}

    </div>
  );
}