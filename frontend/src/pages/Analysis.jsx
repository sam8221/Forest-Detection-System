/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Analysis Page
 *
 * Purpose:
 *   Submits a deforestation analysis for a forest area and
 *   follows it to completion.
 *
 * Responsibilities:
 *   - List the forest areas the officer may analyse.
 *   - Submit an analysis job.
 *   - Poll the job until it finishes.
 *   - Report progress, and report failure with its reason.
 *
 * How it works:
 *
 *   Analysis is asynchronous by necessity
 *   -------------------------------------
 *   Building a cloud-free seasonal composite over a district
 *   means downloading Sentinel-2 products of roughly a
 *   gigabyte each, masking cloud with the SCL band and
 *   computing NDVI across both windows. That takes minutes,
 *   far longer than an HTTP request should be held open.
 *
 *   So the server acknowledges the request immediately with a
 *   job in PENDING, and processes it in the background. This
 *   page then polls the job until it reports COMPLETED or
 *   FAILED, at which point the interval is cleared. The
 *   handle is kept in pollingRef rather than state, because
 *   changing it must not trigger a re-render, and because the
 *   cleanup function needs the current value to stop it.
 *
 *   Reading the outcome
 *   -------------------
 *   A job that completes with ZERO detections is a valid
 *   outcome, not a failure, and the two are shown
 *   differently on purpose: the officer's response differs.
 *   Zero detections means no vegetation loss was found above
 *   the half-hectare threshold, and the answer is to wait for
 *   the next acquisition. FAILED means something went wrong
 *   and is worth investigating.
 *
 *   The job carries an execution_log field, which the server
 *   updates as it moves between stages. It is displayed so a
 *   run that takes several minutes shows what it is doing
 *   rather than appearing to have stalled.
 *
 * Note on seasonal windows:
 *   The two periods compared are equivalent calendar windows
 *   in different years, never adjacent months. Miombo
 *   woodland loses leaf across the whole province every dry
 *   season, so comparing consecutive months would report
 *   deforestation everywhere. This is the main
 *   methodological defence of the project and must not be
 *   weakened.
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
  AlertTriangle,
  Calendar,
  CheckCircle2,
  Clock3,
  Cloud,
  Loader2,
  Play,
  RefreshCw,
  Satellite,
  TreePine,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import SatelliteComparisonViewer from "../components/SatelliteComparisonViewer";
import api from "../services/api";
import {
  findEligibleObservation,
  getEligibleObservations,
  getSelectedObservationCards,
  validateObservationPair,
} from "../services/satelliteComparison";
import {
  canDisplayAnalysisResults,
  isConfirmedActiveAnalysisJob,
  restoreSelectedPair,
  selectRestorableAnalysisJob,
} from "../services/analysisJobState";
import {
  analysisMetricDisplays,
  formatMeasurement,
} from "../services/analysisMetrics";

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

export default function Analysis({ initialSelection, onSelectionConsumed }) {
  const [forestAreas, setForestAreas] = useState([]);
  const [selectedArea, setSelectedArea] = useState(
    initialSelection?.forestAreaId
      ? String(initialSelection.forestAreaId)
      : ""
  );

  const [job, setJob] = useState(null);
  const [observations, setObservations] = useState([]);
  const [previousImageId, setPreviousImageId] = useState("");
  const [recentImageId, setRecentImageId] = useState("");
  const [loadingObservations, setLoadingObservations] = useState(false);
  const [observationsLoadedForArea, setObservationsLoadedForArea] = useState("");
  const [observationError, setObservationError] = useState("");
  const [preselectionMessage, setPreselectionMessage] = useState("");

  const [loadingAreas, setLoadingAreas] = useState(true);
  const [loadingJob, setLoadingJob] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const pollingRef = useRef(null);
  const pollingFailuresRef = useRef(0);
  const restoredPairJobRef = useRef(null);
  const initialSelectionRef = useRef(initialSelection);
  const preselectionAppliedRef = useRef(false);

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

      const requestedArea = data.find(
        (area) =>
          String(area.id) ===
          String(initialSelectionRef.current?.forestAreaId)
      );
      const nextArea = requestedArea || data[0];
      setSelectedArea(nextArea ? String(nextArea.id) : "");

      if (initialSelectionRef.current?.forestAreaId && !requestedArea) {
        setPreselectionMessage("The selected forest area is not available to your account. Choose an area you are authorised to analyse.");
        preselectionAppliedRef.current = true;
        onSelectionConsumed?.();
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
  }, []);

  const fetchAnalysisJob = useCallback(async (jobId) => {
    if (!jobId) return null;
    const response = await api.get(`/analysis/jobs/${jobId}`);
    return response.data;
  }, []);

  const loadLatestJob = useCallback(async () => {
    if (!selectedArea) {
      setJob(null);
      return;
    }

    setLoadingJob(true);
    setJob(null);

    try {
      const response = await api.get(
        "/analysis/jobs"
      );

      const jobs = Array.isArray(response.data)
        ? response.data
        : [];

      const candidate = selectRestorableAnalysisJob(jobs, selectedArea);
      if (!candidate) {
        setJob(null);
        return;
      }

      const confirmedJob = await fetchAnalysisJob(candidate.id);
      if (
        ["PENDING", "RUNNING"].includes(normalizeStatus(confirmedJob?.status)) &&
        !isConfirmedActiveAnalysisJob(confirmedJob)
      ) {
        setJob(null);
        return;
      }

      setJob(confirmedJob);
      if (normalizeStatus(confirmedJob?.status) === "FAILED") {
        setError(
          confirmedJob.error_message ||
            "The most recent analysis failed. Select a valid pair and retry."
        );
      } else if (
        normalizeStatus(confirmedJob?.status) === "COMPLETED" &&
        !canDisplayAnalysisResults(confirmedJob)
      ) {
        setError(
          confirmedJob.results_verification_error ||
            "This completed job has no verified results. Run a new analysis."
        );
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
      setJob(null);
    } finally {
      setLoadingJob(false);
    }
  }, [fetchAnalysisJob, selectedArea]);

  const loadJob = useCallback(async (jobId) => {
    if (!jobId) return null;

    try {
      const updatedJob = await fetchAnalysisJob(jobId);
      setJob(updatedJob);
      return updatedJob;
    } catch (err) {
      console.error(
        "Failed to load analysis job:",
        err
      );

      return { pollError: err };
    }
  }, [fetchAnalysisJob]);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearTimeout(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (jobId) => {
      stopPolling();
      pollingFailuresRef.current = 0;

      const poll = async () => {
        const updatedJob = await loadJob(jobId);
        if (updatedJob?.pollError) {
          const statusCode = updatedJob.pollError.response?.status;
          if (statusCode === 404) {
            stopPolling();
            setJob(null);
            setError(
              `Analysis job #${jobId} no longer exists. Select the observation pair and start a new analysis.`
            );
            return;
          }

          pollingFailuresRef.current += 1;
          if (pollingFailuresRef.current >= 5) {
            stopPolling();
            setJob((current) =>
              current?.id === jobId
                ? { ...current, worker_available: false }
                : current
            );
            setError(
              "The backend could not confirm this analysis is still active. Refresh its status or retry the selected pair."
            );
            return;
          }
          pollingRef.current = setTimeout(poll, 3000);
          return;
        }

        pollingFailuresRef.current = 0;
        const status = normalizeStatus(updatedJob?.status);
        if (status === "COMPLETED" || status === "FAILED") {
          stopPolling();
          if (status === "COMPLETED" && canDisplayAnalysisResults(updatedJob)) {
            setError("");
            setMessage("Deforestation analysis completed successfully.");
          } else if (status === "FAILED") {
            setMessage("");
            setError(
              updatedJob.error_message ||
                "The deforestation analysis failed. Select a valid pair and retry."
            );
          } else {
            setMessage("");
            setError(
              updatedJob.results_verification_error ||
                "The job finished but its results could not be verified. Run a new analysis."
            );
          }
          return;
        }

        if (!isConfirmedActiveAnalysisJob(updatedJob)) {
          stopPolling();
          setJob(null);
          setError(
            "The backend no longer confirms an active worker for this job. Select the pair and retry."
          );
          return;
        }
        pollingRef.current = setTimeout(poll, 3000);
      };

      pollingRef.current = setTimeout(poll, 3000);
    },
    [loadJob, stopPolling]
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
    setPreviousImageId("");
    setRecentImageId("");
    restoredPairJobRef.current = null;
    stopPolling();

    loadLatestJob();
  }, [
    selectedArea,
    loadLatestJob,
    stopPolling,
  ]);

  useEffect(() => {
    if (!selectedArea) {
      setObservations([]);
      setObservationsLoadedForArea("");
      return undefined;
    }

    let cancelled = false;
    setLoadingObservations(true);
    setObservationError("");
    setObservationsLoadedForArea("");

    api
      .get(`/satellite-images/forest/${selectedArea}`)
      .then((response) => {
        if (!cancelled) {
          setObservations(
            Array.isArray(response.data) ? response.data : []
          );
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setObservations([]);
          setObservationError(
            err.response?.data?.detail ||
              "Unable to load acquired Sentinel-2 observations for this forest area."
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoadingObservations(false);
          setObservationsLoadedForArea(String(selectedArea));
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedArea]);

  useEffect(() => {
    const requested = initialSelectionRef.current;
    if (
      preselectionAppliedRef.current ||
      !requested?.satelliteImageId ||
      !selectedArea ||
      String(requested.forestAreaId) !== String(selectedArea) ||
      observationsLoadedForArea !== String(selectedArea)
    ) {
      return;
    }

    if (observationError) {
      setPreselectionMessage(observationError);
    } else {
      const selectedImage = findEligibleObservation(
        observations,
        selectedArea,
        requested.satelliteImageId
      );
      if (selectedImage) {
        setRecentImageId(String(selectedImage.id));
        setPreselectionMessage(
          `Preselected ${selectedImage.product_id} (${formatDate(selectedImage.acquisition_date)}). Select an earlier compatible observation to continue.`
        );
      } else {
        setPreselectionMessage(
          "The selected product is no longer active, downloaded, or eligible for analysis. Choose an eligible observation below."
        );
      }
    }

    preselectionAppliedRef.current = true;
    onSelectionConsumed?.();
  }, [
    observations,
    observationsLoadedForArea,
    observationError,
    onSelectionConsumed,
    selectedArea,
  ]);

  useEffect(() => {
    if (
      !job?.id ||
      !job.previous_satellite_image_id ||
      !job.satellite_image_id ||
      !selectedArea ||
      observationsLoadedForArea !== String(selectedArea) ||
      restoredPairJobRef.current === job.id
    ) {
      return;
    }

    const restored = restoreSelectedPair(job, observations, selectedArea);
    if (restored) {
      setPreviousImageId(restored.previousImageId);
      setRecentImageId(restored.recentImageId);
    } else {
      setError(
        "The observation pair recorded on this job is no longer eligible. Choose a currently available pair to run a new analysis."
      );
    }
    restoredPairJobRef.current = job.id;
  }, [
    job?.id,
    job?.previous_satellite_image_id,
    job?.satellite_image_id,
    observations,
    observationsLoadedForArea,
    selectedArea,
  ]);

  useEffect(() => {
    return stopPolling;
  }, [stopPolling]);

  useEffect(() => {
    if (isConfirmedActiveAnalysisJob(job)) {
      startPolling(job.id);
    } else {
      stopPolling();
    }
  }, [job?.id, job?.status, job?.worker_available, startPolling, stopPolling]);

  const jobActive = isConfirmedActiveAnalysisJob(job);
  const busy = submitting || jobActive;

  const runAnalysis = async () => {
    if (!selectedArea) {
      setError(
        "Please select a forest area first."
      );
      return;
    }

    setSubmitting(true);
    setJob(null);
    setPreviousImageId("");
    setRecentImageId("");
    setError("");
    setMessage("");
    restoredPairJobRef.current = null;

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
        worker_available: createdJob.worker_available === true,
      });

      setMessage(
        "Analysis queued. The backend worker will process the request."
      );
    } catch (err) {
      console.error(
        "Failed to start analysis:",
        err
      );

      setError(
        err.response?.data?.detail ||
          "Failed to start deforestation analysis."
      );
    } finally {
      setSubmitting(false);
    }
  };

  const runSelectedPairAnalysis = async () => {
    setError("");
    setMessage("");

    const pair = validateObservationPair(
      observations,
      selectedArea,
      previousImageId,
      recentImageId
    );
    if (!pair.valid) {
      setError(pair.error);
      return;
    }

    setSubmitting(true);
    setJob(null);
    restoredPairJobRef.current = null;
    try {
      const response = await api.post(
        `/analysis/run/${selectedArea}/pair`,
        {
          previous_satellite_image_id: Number(previousImageId),
          recent_satellite_image_id: Number(recentImageId),
        }
      );
      const createdJob = response.data;

      setJob({
        id: createdJob.analysis_job_id,
        forest_area_id: createdJob.forest_area_id,
        previous_satellite_image_id:
          createdJob.previous_satellite_image_id,
        satellite_image_id:
          createdJob.recent_satellite_image_id,
        status: createdJob.status || "PENDING",
        job_type: "MANUAL",
        created_at: new Date().toISOString(),
        worker_available: createdJob.worker_available === true,
      });
      setMessage(
        `Analysis queued for the selected observations (${formatDate(pair.previous.acquisition_date)} and ${formatDate(pair.recent.acquisition_date)}).`
      );
      restoredPairJobRef.current = createdJob.analysis_job_id;
    } catch (err) {
      console.error("Failed to start selected-pair analysis:", err);
      setError(
        err.response?.data?.detail ||
          "The selected Sentinel-2 pair could not be analysed."
      );
    } finally {
      setSubmitting(false);
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

  const eligibleObservations = getEligibleObservations(
    observations,
    selectedArea
  );
  const pairValidation =
    previousImageId && recentImageId
      ? validateObservationPair(
          observations,
          selectedArea,
          previousImageId,
          recentImageId
        )
      : null;
  const selectedObservationCards = getSelectedObservationCards(
    observations,
    selectedArea,
    previousImageId,
    recentImageId
  );

  // Read from the fields the analysis API actually returns:
  // vegetation_change_percentage, detected_area_hectares,
  // mean_confidence_score and detection_count.
  //
  // The affected area and the confidence were previously read
  // from loss_area_hectares, deforestation_area_hectares,
  // deforested_area_hectares, confidence_percentage and
  // confidence - none of which this API has ever sent. Each
  // chain therefore fell through to its "?? 0" default, so
  // every completed analysis reported 0.00 ha affected at
  // 0.00% confidence however much clearing it had found.
  //
  // The rule now lives in services/analysisMetrics.js, where
  // it is tested directly.
  const {
    vegetationChangeDisplay,
    affectedAreaDisplay,
    confidenceDisplay,
  } = analysisMetricDisplays(job);

  const status =
    job?.status || "NOT_STARTED";
  const verifiedResults = canDisplayAnalysisResults(job);

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
          grid-template-columns: repeat(3, minmax(180px, 1fr));
          gap: 16px;
          align-items: start;
        }

        .analysis-actions {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          margin-top: 18px;
        }

        .analysis-observation-details {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
          margin-top: 16px;
        }

        .analysis-observation-card {
          display: grid;
          gap: 5px;
          padding: 12px 14px;
          border: 1px solid #dbeafe;
          border-radius: 8px;
          background: #f8fafc;
          color: #475569;
          font-size: 13px;
        }

        .analysis-observation-card strong {
          color: #0f172a;
        }

        .analysis-selection-hint {
          margin: 14px 0 0;
          color: #64748b;
          font-size: 13px;
          line-height: 1.5;
        }

        .analysis-progress-log {
          margin-top: 12px;
          padding: 12px 14px;
          border-radius: 8px;
          background: #f8fafc;
          color: #475569;
          white-space: pre-wrap;
          font-size: 13px;
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

          .analysis-observation-details {
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
            disabled={loadingJob}
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

      {preselectionMessage && (
        <div className="analysis-alert success" role="status">
          <Satellite size={18} />
          <span>{preselectionMessage}</span>
        </div>
      )}

      <div className="analysis-card">
        <h2 className="analysis-card-title">
          Analysis configuration
        </h2>

        <p className="analysis-selection-hint">
          Compare two acquired Sentinel-2 Level-2A observations for one registered forest area. Opening this page or changing a selection does not download imagery.
        </p>

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
                setPreviousImageId("");
                setRecentImageId("");
                setPreselectionMessage("");
                setMessage("");
                setError("");
                restoredPairJobRef.current = null;
                stopPolling();
              }}
              disabled={
                loadingAreas || busy || loadingJob
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

          <div className="analysis-field">
            <label htmlFor="previous-observation">
              Previous observation
            </label>
            <select
              id="previous-observation"
              className="analysis-select"
              value={previousImageId}
              onChange={(event) => {
                setPreviousImageId(event.target.value);
                setJob(null);
                setMessage("");
                setError("");
                restoredPairJobRef.current = null;
              }}
              disabled={loadingObservations || busy || !selectedArea}
            >
              <option value="">
                {loadingObservations ? "Loading observations..." : "Select earlier date"}
              </option>
              {eligibleObservations.map((image) => (
                <option key={`previous-${image.id}`} value={image.id}>
                  {formatDate(image.acquisition_date)} · {image.tile_id} · {formatMeasurement(image.cloud_cover_percentage, "%", 1)} cloud
                </option>
              ))}
            </select>
          </div>

          <div className="analysis-field">
            <label htmlFor="recent-observation">
              Recent observation
            </label>
            <select
              id="recent-observation"
              className="analysis-select"
              value={recentImageId}
              onChange={(event) => {
                setRecentImageId(event.target.value);
                setJob(null);
                setMessage("");
                setError("");
                restoredPairJobRef.current = null;
              }}
              disabled={loadingObservations || busy || !selectedArea}
            >
              <option value="">
                {loadingObservations ? "Loading observations..." : "Select later date"}
              </option>
              {eligibleObservations.map((image) => (
                <option key={`recent-${image.id}`} value={image.id}>
                  {formatDate(image.acquisition_date)} · {image.tile_id} · {formatMeasurement(image.cloud_cover_percentage, "%", 1)} cloud
                </option>
              ))}
            </select>
          </div>
        </div>

        {observationError && (
          <div className="analysis-alert error" role="alert">
            <AlertTriangle size={18} />
            <span>{observationError}</span>
          </div>
        )}

        {!loadingObservations && !observationError && eligibleObservations.length === 0 && selectedArea && (
          <p className="analysis-selection-hint">
            No active, downloaded Level-2A observations are registered for this forest area. Acquire imagery in Satellite Images, then return here to compare it.
          </p>
        )}

        {selectedObservationCards.length === 2 && (
          <div className="analysis-observation-details">
            {selectedObservationCards.map(({ role, label, image }) => (
              <div
                className="analysis-observation-card"
                key={`selected-${role}-${image.id}`}
                data-observation-role={role}
              >
                <strong>{label}</strong>
                <span><Calendar size={14} /> {formatDate(image.acquisition_date)} · Product {image.product_id}</span>
                <span><Cloud size={14} /> Tile {image.tile_id} · {formatMeasurement(image.cloud_cover_percentage, "%", 1)} catalogue cloud · {image.is_downloaded ? "Downloaded" : "Not downloaded"} · {image.processing_level || "Processing level unavailable"}</span>
              </div>
            ))}
          </div>
        )}

        {pairValidation && !pairValidation.valid && (
          <div className="analysis-alert error" role="alert">
            <AlertTriangle size={18} />
            <span>{pairValidation.error}</span>
          </div>
        )}

        {eligibleObservations.length > 0 && eligibleObservations.length < 2 && (
          <p className="analysis-selection-hint">
            At least two acquired observations are needed. Products must be active Level-2A images for this forest; the backend also verifies local files, same-tile coverage, and acquisition order before processing.
          </p>
        )}

        <div className="analysis-actions">
          <button
            className="analysis-button primary"
            onClick={runSelectedPairAnalysis}
            disabled={
              !selectedArea ||
              busy ||
              loadingJob ||
              loadingObservations ||
              !pairValidation?.valid
            }
          >
            {submitting ? (
              <>
                <Loader2 size={17} />
                Submitting analysis...
              </>
            ) : jobActive && normalizeStatus(job?.status) === "PENDING" ? (
              <>
                <Clock3 size={17} />
                Analysis queued...
              </>
            ) : jobActive && normalizeStatus(job?.status) === "RUNNING" ? (
              <>
                <Loader2 size={17} />
                Analysis Running...
              </>
            ) : (
              <>
                <Play size={17} />
                Run selected-pair analysis
              </>
            )}
          </button>

          <button
            className="analysis-button secondary"
            onClick={runAnalysis}
            disabled={!selectedArea || busy || loadingJob}
            title="Runs the existing automatic seasonal analysis workflow."
          >
            <RefreshCw size={16} />
            Run automatic seasonal analysis
          </button>
        </div>
        <p className="analysis-selection-hint">
          The automatic workflow remains available for existing operations and may acquire imagery after you explicitly start it. Selected-pair analysis uses only the two observations chosen above.
        </p>
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
          {!verifiedResults && (
            <div className="analysis-card" role="status">
              <h2 className="analysis-card-title">Analysis job #{job.id}</h2>
              <div className={statusClass(status)}>{statusLabel(status)}</div>
              <p>
                {normalizeStatus(status) === "PENDING"
                  ? "Queued for the backend analysis worker."
                  : normalizeStatus(status) === "RUNNING"
                    ? "The backend worker is processing this job."
                    : normalizeStatus(status) === "FAILED"
                      ? job.error_message || "The analysis failed. You can retry with a valid pair."
                      : job.results_verification_error || "The completed job's results are not verified. Run a new analysis."}
              </p>
              {job.execution_log && (
                <div className="analysis-progress-log">{job.execution_log}</div>
              )}
            </div>
          )}

          {verifiedResults && <div className="analysis-stat-grid">

            <div className="analysis-stat">
              <div className="analysis-stat-icon">
                <TreePine size={21} />
              </div>

              <div>
                <div className="analysis-stat-label">
                  Vegetation Change
                </div>

                <div className="analysis-stat-value">
                  {vegetationChangeDisplay}
                </div>
              </div>
            </div>

            <div className="analysis-stat">
              <div className="analysis-stat-icon">
                <AlertTriangle size={21} />
              </div>

              <div>
                <div className="analysis-stat-label">
                  Potential Affected Area
                </div>

                <div className="analysis-stat-value">
                  {affectedAreaDisplay}
                </div>
              </div>
            </div>

            <div className="analysis-stat">
              <div className="analysis-stat-icon">
                <CheckCircle2 size={21} />
              </div>

              <div>
                <div className="analysis-stat-label">
                  Mean Detection Confidence
                </div>

                <div className="analysis-stat-value">
                  {confidenceDisplay}
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

          </div>}

          {verifiedResults && normalizeStatus(status) === "COMPLETED" &&
          job.previous_satellite_image_id ? (
            <SatelliteComparisonViewer
              key={`comparison-${job.id}`}
              forestAreaId={job.forest_area_id || selectedArea}
              jobId={job.id}
            />
          ) : null}

          {verifiedResults && normalizeStatus(status) === "COMPLETED" &&
          !job.previous_satellite_image_id ? (
            <div className="analysis-alert success" role="status">
              This automatic seasonal job completed. The swipe and side-by-side viewer is available for explicit observation-pair jobs.
            </div>
          ) : null}

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
                  <span className="image-label">Status</span>
                  <span className="image-value">{statusLabel(status)}</span>
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

              {job.execution_log && (
                <div className="analysis-progress-log" role="status">
                  {job.execution_log}
                </div>
              )}
            </div>

            <div className="analysis-card">
              <h2 className="analysis-card-title">
                Sentinel-2 Processing
              </h2>

              {verifiedResults ? <div className="image-info">

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
                    {formatMeasurement(job.cloud_cover_percentage, "%")}
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    NDVI Threshold
                  </span>

                  <span className="image-value">
                    {formatMeasurement(job.ndvi_threshold)}
                  </span>
                </div>

                <div className="image-row">
                  <span className="image-label">
                    Duration
                  </span>

                  <span className="image-value">
                    {job.duration_seconds
                      ? formatMeasurement(
                          job.duration_seconds,
                          " seconds",
                          1
                        )
                      : "Processing"}
                  </span>
                </div>

              </div> : (
                <p className="analysis-selection-hint">
                  Processing metrics and imagery will appear only after this exact job completes and its outputs pass verification.
                </p>
              )}
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
                  NDVI decline identifies potential vegetation change for review. It does not by itself confirm deforestation.
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
              <strong> Run selected-pair analysis </strong>
              after choosing two acquired observations. The automatic seasonal workflow is also available above.
            </p>

          </div>
        </div>
      )}
    </div>
  );
}
