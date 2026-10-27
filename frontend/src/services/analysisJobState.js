import { validateObservationPair } from "./satelliteComparison.js";

const ACTIVE_STATUSES = new Set(["PENDING", "RUNNING"]);
const TERMINAL_STATUSES = new Set(["COMPLETED", "FAILED"]);

export function normalizeAnalysisStatus(status) {
  return String(status || "").toUpperCase();
}

export function isConfirmedActiveAnalysisJob(job) {
  return Boolean(
    job?.id &&
      ACTIVE_STATUSES.has(normalizeAnalysisStatus(job.status)) &&
      job.worker_available === true
  );
}

export function isTerminalAnalysisJob(job) {
  return TERMINAL_STATUSES.has(normalizeAnalysisStatus(job?.status));
}

export function selectRestorableAnalysisJob(jobs, forestAreaId) {
  const areaJobs = (Array.isArray(jobs) ? jobs : [])
    .filter((job) => String(job.forest_area_id) === String(forestAreaId))
    .sort((a, b) => {
      const byCreated = String(b.created_at || "").localeCompare(
        String(a.created_at || "")
      );
      return byCreated || Number(b.id) - Number(a.id);
    });

  return (
    areaJobs.find(isConfirmedActiveAnalysisJob) ||
    areaJobs.find(isTerminalAnalysisJob) ||
    null
  );
}

export function canDisplayAnalysisResults(job) {
  return Boolean(
    normalizeAnalysisStatus(job?.status) === "COMPLETED" &&
      job.results_verified === true &&
      job.started_at &&
      job.completed_at
  );
}

export function restoreSelectedPair(job, observations, forestAreaId) {
  if (!job?.previous_satellite_image_id || !job?.satellite_image_id) {
    return null;
  }
  const pair = validateObservationPair(
    observations,
    forestAreaId,
    job.previous_satellite_image_id,
    job.satellite_image_id
  );
  if (!pair.valid) return null;
  return {
    previousImageId: String(pair.previous.id),
    recentImageId: String(pair.recent.id),
  };
}

export function comparisonFigureUrls(apiV1, forestAreaId, jobId) {
  const base = `${apiV1}/monitoring/${forestAreaId}/comparison/${jobId}`;
  return {
    figure: `${base}/figure.png`,
    panels: {
      previous_rgb: `${base}/panel/previous_rgb.png`,
      previous_ndvi: `${base}/panel/previous_ndvi.png`,
      recent_ndvi: `${base}/panel/recent_ndvi.png`,
      ndvi_difference: `${base}/panel/ndvi_difference.png`,
    },
  };
}
