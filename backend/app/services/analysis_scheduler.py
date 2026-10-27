"""Lifecycle-managed polling loop for the persistent analysis queue."""

from __future__ import annotations

import logging
import threading
import time

from app.services.analysis_worker import AnalysisWorker, recover_abandoned_analysis_jobs


logger = logging.getLogger(__name__)


class AnalysisScheduler:
    """Run the database-backed analysis worker while FastAPI is alive."""

    def __init__(self, interval_seconds: float = 1.0) -> None:
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker = AnalysisWorker()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        next_recovery = 0.0
        while not self._stop_event.is_set():
            try:
                now = time.monotonic()
                if now >= next_recovery:
                    recover_abandoned_analysis_jobs()
                    next_recovery = now + 10.0
                worked = self._worker.run_once()
            except Exception:
                logger.exception("Analysis worker queue cycle failed")
                worked = False

            if not worked:
                self._stop_event.wait(self.interval_seconds)

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="forestwatch-analysis-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("Analysis worker queue started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            # Let a job already in progress record its final status and release
            # its advisory lock before this process shuts down.
            self._thread.join(timeout=30)
        logger.info("Analysis worker queue stopped")

