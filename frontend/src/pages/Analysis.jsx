import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  Play,
  RefreshCw,
  Satellite,
  TreePine,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import api from "../services/api";

const formatDate = (value) => {
  if (!value) return "Not available";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Not available";
  }

  return date.toLocaleString("en-ZM", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const formatNumber = (value, decimals = 2) => {
  const number = Number(value);

  if (!Number.isFinite(number)) {
    return "0.00";
  }

  return number.toFixed(decimals);
};

const normalizeStatus = (status) =>
  String(status || "").toUpperCase();

const statusLabel = (status) => {
  const value = normalizeStatus(status);

  if (value === "COMPLETED") return "Completed";
  if (value === "RUNNING") return "Running";
  if (value === "PENDING") return "Pending";
  if (value === "FAILED") return "Failed";

  return status || "Not started";
};

const statusClass = (status) => {
  const value = normalizeStatus(status);

  if (value === "COMPLETED") {
    return "status-badge completed";
  }

  if (value === "FAILED") {
    return "status-badge failed";
  }

  if (
    value === "RUNNING" ||
    value === "PENDING"
  ) {
    return "status-badge running";
  }

  return "status-badge";
};

export default function Analysis() {
  const [forestAreas, setForestAreas] = useState([]);
  const [selectedArea, setSelectedArea] = useState("");

  const [job, setJob] = useState(null);

  const [loadingAreas, setLoadingAreas] = useState(true);
  const [loadingJob, setLoadingJob] = useState(false);
  const [running, setRunning] = useState(false);

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const pollingRef = useRef(null);

  const loadForestAreas = useCallback(async () => {
    setLoadingAreas(true);
    setError("");

    try {
      const response = await api.get("/forest-areas");

      const data = Array.isArray(response.data)
        ? response.data
        : response.data?.items ||
          response.data?.data ||
          [];

      setForestAreas(data);

      if (data.length > 0 && !selectedArea) {
        setSelectedArea(String(data[0].id));
      }
    } catch (err) {
      console.error(
        "Failed to load forest areas:",
        err
      );

      setError(
        err.response?.data?.detail ||
          "Failed to load forest areas."
      );
    } finally {
      setLoadingAreas(false);
    }
  }, [selectedArea]);

  const loadLatestJob = useCallback(async () => {
    if (!selectedArea) {
      setJob(null);
      return;
    }

    setLoadingJob(true);

    try {
      const response = await api.get(
        "/analysis/jobs"
      );

      const jobs = Array.isArray(response.data)
        ? response.data
        : [];

      const areaJobs = jobs.filter(
        (item) =>
          String(item.forest_area_id) ===
          String(selectedArea)
      );

      if (areaJobs.length > 0) {
        setJob(areaJobs[0]);
      } else {
        setJob(null);
      }
    } catch (err) {
      console.error(
        "Failed to load analysis jobs:",
        err
      );

      setError(
        err.response?.data?.detail ||
          "Failed to load analysis information."
      );
    } finally {
      setLoadingJob(false);
    }
  }, [selectedArea]);

  const loadJob = useCallback(async (jobId) => {
    if (!jobId) return null;

    try {
      const response = await api.get(
        `/analysis/jobs/${jobId}`
      );

      setJob(response.data);

      return response.data;
    } catch (err) {
      console.error(
        "Failed to load analysis job:",
        err
      );

      return null;
    }
  }, []);

  const startPolling = useCallback(
    (jobId) => {
      if (pollingRef.current) {
        clearInterval(
          pollingRef.current
        );
      }

      pollingRef.current = setInterval(
        async () => {
          const updatedJob =
            await loadJob(jobId);

          if (!updatedJob) {
            return;
          }

          const status =
            normalizeStatus(
              updatedJob.status
            );

          if (
            status === "COMPLETED" ||
            status === "FAILED"
          ) {
            clearInterval(
              pollingRef.current
            );

            pollingRef.current = null;

            setRunning(false);

            if (status === "COMPLETED") {
              setMessage(
                "Deforestation analysis completed successfully."
              );
            }

            if (status === "FAILED") {
              setError(
                updatedJob.error_message ||
                  "The deforestation analysis failed."
              );
            }
          }
        },
        3000
      );
    },
    [loadJob]
  );

  useEffect(() => {
    loadForestAreas();
  }, [loadForestAreas]);

  useEffect(() => {
    if (!selectedArea) {
      return;
    }

    setJob(null);
    setMessage("");
    setError("");

    loadLatestJob();
  }, [
    selectedArea,
    loadLatestJob,
  ]);

  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(
          pollingRef.current
        );
      }
    };
  }, []);

  const runAnalysis = async () => {
    if (!selectedArea) {
      setError(
        "Please select a forest area first."
      );
      return;
    }

    setRunning(true);
    setError("");
    setMessage("");

    try {
      const response = await api.post(
        `/analysis/run/${selectedArea}`
      );

      const createdJob = response.data;

      setJob({
        id: createdJob.analysis_job_id,
        forest_area_id:
          createdJob.forest_area_id,
        satellite_image_id:
          createdJob.satellite_image_id,
        status:
          createdJob.status || "PENDING",
        job_type:
          createdJob.job_type || "AUTOMATIC",
      });

      setMessage(
        "Analysis started. Sentinel-2 processing is running in the background."
      );

      startPolling(
        createdJob.analysis_job_id
      );
    } catch (err) {
      console.error(
        "Failed to start analysis:",
        err
      );

      setRunning(false);

      setError(
        err.response?.data?.detail ||
          "Failed to start deforestation analysis."
      );
    }
  };

  const refresh = async () => {
    setError("");
    setMessage("");

    await loadLatestJob();
  };

  const selectedForestArea =
    forestAreas.find(
      (area) =>
        String(area.id) ===
        String(selectedArea)
    );

  const vegetationChange =
    job?.vegetation_change_percentage ?? 0;

  const confidence =
    job?.confidence_percentage ??
    job?.confidence ??
    0;

  const deforestedArea =
    job?.loss_area_hectares ??
    job?.deforestation_area_hectares ??
    job?.deforested_area_hectares ??
    0;

  const status =
    job?.status || "NOT_STARTED";

  return (
    <div className="analysis-page">

      <style>{`
        .analysis-page {
          padding: 24px;
          max-width: 1400px;
          margin: 0 auto;
        }

        .analysis-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 20px;
          margin-bottom: 24px;
        }

        .analysis-title {
          display: flex;
          align-items: center;
          gap: 12px;
          margin: 0;
          font-size: 28px;
          font-weight: 700;
          color: #0f172a;
        }

        .analysis-subtitle {
          margin: 8px 0 0;
          color: #64748b;
          font-size: 15px;
        }

        .analysis-header-actions {
          display: flex;
          gap: 10px;
        }

        .analysis-button {
          border: none;
          border-radius: 8px;
          padding: 11px 16px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
        }

        .analysis-button.primary {
          background: #166534;
          color: white;
        }

        .analysis-button.primary:hover {
          background: #14532d;
        }

        .analysis-button.secondary {
          background: white;
          color: #334155;
          border: 1px solid #cbd5e1;
        }

        .analysis-button:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .analysis-card {
          background: white;
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          padding: 20px;
          margin-bottom: 20px;
          box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        }

        .analysis-card-title {
          margin: 0 0 16px;
          font-size: 17px;
          font-weight: 700;
          color: #0f172a;
        }

        .analysis-controls {
          display: grid;
          grid-template-columns: 1fr auto;
          gap: 16px;
          align-items: end;
        }

        .analysis-field {
          display: flex;
          flex-direction: column;
          gap: 7px;
        }

        .analysis-field label {
          font-size: 13px;
          font-weight: 600;
          color: #475569;
        }

        .analysis-select {
          width: 100%;
          padding: 11px 12px;
          border: 1px solid #cbd5e1;
          border-radius: 8px;
          background: white;
          color: #0f172a;
          font-size: 14px;
          outline: none;
        }

        .analysis-select:focus {
          border-color: #166534;
        }

        .analysis-alert {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 14px;
          border-radius: 8px;
          margin-bottom: 20px;
          font-size: 14px;
        }

        .analysis-alert.error {
          background: #fef2f2;
          color: #991b1b;
          border: 1px solid #fecaca;
        }

        .analysis-alert.success {
          background: #f0fdf4;
          color: #166534;
          border: 1px solid #bbf7d0;
        }

        .analysis-stat-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 16px;
          margin-bottom: 20px;
        }

        .analysis-stat {
          background: white;
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          padding: 18px;
          display: flex;
          align-items: flex-start;
          gap: 13px;
        }

        .analysis-stat-icon {
          width: 42px;
          height: 42px;
          border-radius: 10px;
          background: #f0fdf4;
          color: #166534;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }

        .analysis-stat-label {
          color: #64748b;
          font-size: 12px;
          margin-bottom: 5px;
        }

        .analysis-stat-value {
          color: #0f172a;
          font-size: 22px;
          font-weight: 700;
        }

        .analysis-two-column {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 20px;
        }

        .image-info {
          display: grid;
          gap: 12px;
        }

        .image-row {
          display: flex;
          justify-content: space-between;
          gap: 15px;
          padding-bottom: 10px;
          border-bottom: 1px solid #f1f5f9;
        }

        .image-row:last-child {
          border-bottom: none;
          padding-bottom: 0;
        }

        .image-label {
          color: #64748b;
          font-size: 13px;
        }

        .image-value {
          color: #0f172a;
          font-size: 13px;
          font-weight: 600;
          text-align: right;
        }

        .status-badge {
          display: inline-flex;
          align-items: center;
          gap: 7px;
          padding: 7px 11px;
          border-radius: 999px;
          background: #f1f5f9;
          color: #475569;
          font-size: 13px;
          font-weight: 600;
        }

        .status-badge.completed {
          background: #dcfce7;
          color: #166534;
        }

        .status-badge.failed {
          background: #fee2e2;
          color: #991b1b;
        }

        .status-badge.running {
          background: #fef3c7;
          color: #92400e;
        }

        .analysis-empty {
          text-align: center;
          padding: 45px 20px;
          color: #64748b;
        }

        .analysis-empty-icon {
          margin-bottom: 12px;
          color: #94a3b8;
        }

        .analysis-method {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 14px;
          margin-top: 16px;
        }

        .method-item {
          padding: 14px;
          border-radius: 8px;
          background: #f8fafc;
          border: 1px solid #e2e8f0;
        }

        .method-item strong {
          display: block;
          margin-bottom: 5px;
          color: #0f172a;
          font-size: 13px;
        }

        .method-item span {
          color: #64748b;
          font-size: 12px;
        }

        @media (max-width: 1000px) {
          .analysis-stat-grid {
            grid-template-columns: repeat(2, 1fr);
          }

          .analysis-two-column {
            grid-template-columns: 1fr;
          }
        }

        @media (max-width: 700px) {
          .analysis-page {
            padding: 15px;
          }

          .analysis-header {
            flex-direction: column;
          }

          .analysis-controls {
            grid-template-columns: 1fr;
          }

          .analysis-stat-grid {
            grid-template-columns: 1fr;
          }

          .analysis-method {
            grid-template-columns: 1fr;
          }
        }
      `}</style>

      <div className="analysis-header">
        <div>
          <h1 className="analysis-title">
            <Satellite size={30} />
            Deforestation Analysis
          </h1>

          <p className="analysis-subtitle">
            Compare Sentinel-2 imagery to detect vegetation
            loss within monitored forest areas.
          </p>
        </div>

        <div className="analysis-header-actions">
          <button
            className="analysis-button secondary"
            onClick={refresh}
            disabled={loadingJob || running}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="analysis-alert error">
          <AlertTriangle size={18} />
          <span>{error}</span>
        </div>
      )}

      {message && (
        <div className="analysis-alert success">
          <CheckCircle2 size={18} />
          <span>{message}</span>
        </div>
      )}

      <div className="analysis-card">
        <h2 className="analysis-card-title">
          Start Forest Analysis
        </h2>

        <div className="analysis-controls">
          <div className="analysis-field">
            <label htmlFor="forest-area">
              Forest Area
            </label>

            <select
              id="forest-area"
              className="analysis-select"
              value={selectedArea}
              onChange={(event) => {
                setSelectedArea(
                  event.target.value
                );
                setJob(null);
                setMessage("");
                setError("");

                if (pollingRef.current) {
                  clearInterval(
                    pollingRef.current
                  );

                  pollingRef.current = null;
                }

                setRunning(false);
              }}
              disabled={
                loadingAreas || running
              }
            >
              <option value="">
                {loadingAreas
                  ? "Loading forest areas..."
                  : "Select a forest area"}
              </option>

              {forestAreas.map((area) => (
                <option
                  key={area.id}
                  value={area.id}
                >
                  {area.name ||
                    area.area_name ||
                    `Forest Area ${area.id}`}
                </option>
              ))}
            </select>
          </div>

          <button
            className="analysis-button primary"
            onClick={runAnalysis}
            disabled={
              !selectedArea || running
            }
          >
            {running ? (
              <>
                <Loader2 size={17} />
                Analysis Running...
              </>
            ) : (
              <>
                <Play size={17} />
                Run Analysis
              </>
            )}
          </button>
        </div>
      </div>

      {selectedForestArea && (
        <div className="analysis-card">
          <h2 className="analysis-card-title">
            Selected Forest Area
          </h2>

          <div className="image-info">
            <div className="image-row">
              <span className="image-label">
                Name
              </span>

              <span className="image-value">
                {selectedForestArea.name ||
                  selectedForestArea.area_name ||
                  `Forest Area ${selectedForestArea.id}`}
              </span>
            </div>

            <div className="image-row">
              <span className="image-label">
                District
              </span>

              <span className="image-value">
                {selectedForestArea.district_name ||
                  selectedForestArea.district?.name ||
                  "Not available"}
              </span>
            </div>

            <div className="image-row">
              <span className="image-label">
                Status
              </span>

              <span className="image-value">
                {selectedForestArea.status ||
                  "Monitored"}
              </span>
            </div>
          </div>
        </div>
      )}

      {loadingJob ? (
        <div className="analysis-card">
          <div className="analysis-empty">
            <Loader2
              size={35}
              className="analysis-empty-icon"
            />

            <div>
              Loading analysis...
            </div>
          </div>
        </div>
      ) : job ? (
        <>
          <div className="analysis-stat-grid">

            <div className="analysis-stat">
              <div className="analysis-stat-icon">
                <TreePine size={21} />
              </div>

              <div>
                <div className="analysis-stat-label">
                  Vegetation Change
                </div>

                <div className="analysis-stat-value">
                  {formatNumber(
                    vegetationChange
                  )}%
                </div>
              </div>
            </div>

            <div className="analysis-stat">
              <div className="analysis-stat-icon">
                <AlertTriangle size={21} />
              </div>

              <div>
                <div className="analysis-stat-label">
                  Deforested Area
                </div>

                <div className="analysis-stat-value">
                  {formatNumber(
                    deforestedArea
                  )} ha
                </div>
              </div>
            </div>

            <div className="analysis-stat">
              <div className="analysis-stat-icon">
                <CheckCircle2 size={21} />
              </div>

              <div>
                <div className="analysis-stat-label">
                  Confidence
                </div>

                <div className="analysis-stat-value">
                  {formatNumber(
                    confidence
                  )}%
                </div>
              </div>
            </div>

            <div className="analysis-stat">
              <div className="analysis-stat-icon">
                {normalizeStatus(status) ===
                "COMPLETED" ? (
                  <CheckCircle2 size={21} />
                ) : normalizeStatus(status) ===
                  "FAILED" ? (
                  <XCircle size={21} />
                ) : (
                  <Clock3 size={21} />
                )}
              </div>

              <div>
                <div className="analysis-stat-label">
                  Analysis Status
                </div>

                <div
                  className={statusClass(
                    status
                  )}
                >
                  {normalizeStatus(status) ===
                  "COMPLETED" ? (
                    <CheckCircle2 size={16} />
                  ) : normalizeStatus(status) ===
                    "FAILED" ? (
                    <XCircle size={16} />
                  ) : (
                    <Clock3 size={16} />
                  )}

                  {statusLabel(status)}
                </div>
              </div>
            </div>

          </div>

          <div className="analysis-two-column">

            <div className="analysis-card">
              <h2 className="analysis-card-title">
                Analysis Job
              </h2>

              <div className="image-info">

                <div className="image-row">
                  <span className="image-label">
                    Job ID
                  </span>

                  <span className="image-value">
                    #{job.id}
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    Job Type
                  </span>

                  <span className="image-value">
                    {job.job_type ||
                      "AUTOMATIC"}
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    Created
                  </span>

                  <span className="image-value">
                    {formatDate(
                      job.created_at
                    )}
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    Started
                  </span>

                  <span className="image-value">
                    {formatDate(
                      job.started_at
                    )}
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    Completed
                  </span>

                  <span className="image-value">
                    {formatDate(
                      job.completed_at
                    )}
                  </span>
                </div>

              </div>
            </div>

            <div className="analysis-card">
              <h2 className="analysis-card-title">
                Sentinel-2 Processing
              </h2>

              <div className="image-info">

                <div className="image-row">
                  <span className="image-label">
                    Current Image ID
                  </span>

                  <span className="image-value">
                    {job.satellite_image_id ||
                      "Not available"}
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    Previous Image ID
                  </span>

                  <span className="image-value">
                    {job.previous_satellite_image_id ||
                      "Not available"}
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    Cloud Cover
                  </span>

                  <span className="image-value">
                    {formatNumber(
                      job.cloud_cover_percentage
                    )}%
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    NDVI Threshold
                  </span>

                  <span className="image-value">
                    {formatNumber(
                      job.ndvi_threshold
                    )}
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    Duration
                  </span>

                  <span className="image-value">
                    {job.duration_seconds
                      ? `${formatNumber(
                          job.duration_seconds,
                          1
                        )} seconds`
                      : "Processing"}
                  </span>
                </div>

              </div>
            </div>

          </div>

          {normalizeStatus(status) ===
            "FAILED" &&
            job.error_message && (
              <div className="analysis-alert error">
                <XCircle size={18} />

                <span>
                  {job.error_message}
                </span>
              </div>
            )}

          <div className="analysis-card">
            <h2 className="analysis-card-title">
              Analysis Method
            </h2>

            <div className="analysis-method">

              <div className="method-item">
                <strong>
                  Sentinel-2 L2A
                </strong>

                <span>
                  Satellite imagery is used as
                  the observation source.
                </span>
              </div>

              <div className="method-item">
                <strong>
                  NDVI Comparison
                </strong>

                <span>
                  Current and previous vegetation
                  conditions are compared.
                </span>
              </div>

              <div className="method-item">
                <strong>
                  Vegetation Loss
                </strong>

                <span>
                  Significant vegetation reduction
                  is evaluated as possible
                  deforestation.
                </span>
              </div>

            </div>
          </div>
        </>
      ) : (
        <div className="analysis-card">
          <div className="analysis-empty">

            <Satellite
              size={45}
              className="analysis-empty-icon"
            />

            <h3>
              No Analysis Result
            </h3>

            <p>
              Select a forest area and click
              <strong> Run Analysis </strong>
              to begin Sentinel-2 deforestation
              analysis.
            </p>

          </div>
        </div>
      )}
    </div>
  );
}