# services/advanced_analysis_worker.py
"""
Parallel AdvancedAnalysisWorker for Musicians Organizer.

This QThread delegates heavy audio feature extraction to a ThreadPoolExecutor,
maximizing multi-core utilization while ensuring all database writes occur
after worker shutdown to avoid SQLite lock conflicts.
"""

from __future__ import annotations
import concurrent.futures as _cf
import logging
import os
import threading
import time
import math
from typing import Any, Dict, List, Optional

from PyQt5 import QtCore

from services.analysis_engine import AnalysisEngine
from services.database_manager import DatabaseManager

# Configuration values; MAX_PARALLEL_ANALYSIS is optional in settings
try:
    from config.settings import AUDIO_EXTENSIONS, ALL_FEATURE_KEYS, MAX_PARALLEL_ANALYSIS
except ImportError:
    AUDIO_EXTENSIONS = {".wav", ".aiff", ".flac", ".mp3", ".ogg"} # Use full set here
    ALL_FEATURE_KEYS: List[str] = []
    MAX_PARALLEL_ANALYSIS: Optional[int] = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# services/advanced_analysis_worker.py
# (Keep imports: annotations, _cf, logging, os, threading, time, typing, QtCore)
# (Keep AnalysisEngine, DatabaseManager imports)
# (Keep settings imports and fallbacks)
import copy
import math # Keep for now, might be needed if logic refined later

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG) # Set logging level elsewhere

def _analyze_and_update_file(file_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a single file. If analysis succeeds (returns a non-empty dict),
    update the dictionary with all returned features and return the updated
    version. Otherwise, return the original dictionary.
    (Simplified change detection)
    """
    path = file_info.get("path", "Unknown Path")
    logger.debug(f"[_analyze_and_update_file] Analyzing: {path}")

    try:
        # Still need a copy to potentially modify
        output = copy.deepcopy(file_info)
        ext = os.path.splitext(path)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            logger.debug(f"[_analyze_and_update_file] Skipping non-audio file: {path}")
            return file_info # Return original if not audio

        logger.debug(f"[_analyze_and_update_file] Calling AnalysisEngine for: {path}")
        adv = AnalysisEngine.analyze_audio_features(path, max_duration=30.0)
        logger.debug(f"[_analyze_and_update_file] AnalysisEngine returned for {path}: adv = {adv}")

        # --- SIMPLIFIED CHANGE DETECTION ---
        # If analysis returned a valid, non-empty dictionary, update and return output
        if adv and isinstance(adv, dict): # Check if adv is a non-empty dictionary
            logger.debug(f"[_analyze_and_update_file] Analysis successful for {path}. Merging results into output dict.")
            # Update the output dictionary with all key-value pairs from adv.
            # This adds new keys and overwrites existing ones from the analysis results.
            output.update(adv)

            # We no longer rely on the complex 'changed' flag based on comparison.
            # We assume if analysis ran and gave results, we return the updated dict.
            logger.debug(f"[_analyze_and_update_file] Returning UPDATED dict for {path}")
            return output # Return the dictionary updated with analysis results
        else:
            # Analysis failed or returned empty/invalid data
            logger.warning(f"[_analyze_and_update_file] Analysis failed or returned no data for {path}. Returning ORIGINAL dict.")
            return file_info # Return the original dictionary if analysis yielded nothing

    except Exception as e:
        # Log error during the analysis/update process for this specific file
        logger.error(f"Error during analysis or update for {path}: {e}", exc_info=True)
        return file_info # Return original on any exception for this file


class AdvancedAnalysisWorker(QtCore.QThread):
    """
    A QThread implementing parallel audio analysis.

    Signals:
        progress(int processed, int total)
        finished(List[Dict[str, Any]] result_list)
        error(str message)
    """
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)
    error = QtCore.pyqtSignal(str)

    # Throttling intervals for progress updates
    PROGRESS_EVERY_N_FILES = 10
    PROGRESS_EVERY_SECS = 0.25

    def __init__(
        self,
        files: List[Dict[str, Any]],
        max_workers: Optional[int] = None,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._files = list(files)
        self._cancelled = False
        self._lock = threading.Lock()
        self._executor: Optional[_cf.ThreadPoolExecutor] = None

        # Determine max_workers: explicit > setting > default heuristic
        if max_workers is not None:
            self._max_workers = max_workers
        elif MAX_PARALLEL_ANALYSIS:
            self._max_workers = MAX_PARALLEL_ANALYSIS
        else:
            cpu = os.cpu_count() or 1
            # Use up to cpu+2 threads, cap at 8 for UI responsiveness
            self._max_workers = min(cpu + 2, 8)

    def run(self) -> None:
        total = len(self._files)
        if total == 0:
            self.finished.emit([])
            return

        processed = 0
        last_emit = time.monotonic()
        updated_map: Dict[str, Dict[str, Any]] = {}
        db_updates: List[Dict[str, Any]] = []

        logger.info(
            "AdvancedAnalysisWorker starting: %d files, %d workers",
            total,
            self._max_workers,
        )

        try:
            # Launch parallel analysis
            self._executor = _cf.ThreadPoolExecutor(max_workers=self._max_workers)
            futures = {
                self._executor.submit(_analyze_and_update_file, fi): fi
                for fi in self._files
            }

            for future in _cf.as_completed(futures):
                with self._lock:
                    if self._cancelled:
                        break
                processed += 1

                orig_info = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    logger.error(
                        "Future exception for %s: %s",
                        orig_info.get("path"),
                        e,
                        exc_info=True,
                    )
                    result = orig_info

                # Record updated or fallback
                updated_map[orig_info["path"]] = result
                # If features changed, queue for DB
                if result is not orig_info:
                    db_updates.append(result)

                # Throttled progress emission
                now = time.monotonic()
                if (
                    processed % self.PROGRESS_EVERY_N_FILES == 0
                    or now - last_emit >= self.PROGRESS_EVERY_SECS
                    or processed == total
                ):
                    self.progress.emit(processed, total)
                    last_emit = now

            # Save to DB if not cancelled
            if not self._cancelled and db_updates:
                try:
                    DatabaseManager.instance().save_file_records(db_updates)
                    logger.info("Saved %d updated records to DB.", len(db_updates))
                except Exception as e:
                    msg = f"Database write failed: {e}"
                    logger.error(msg, exc_info=True)
                    self.error.emit(msg)

            # Build the full-result list in original order
            full_results = [
                updated_map.get(fi["path"], fi)
                for fi in self._files
            ]

            if self._cancelled:
                logger.info(
                    "Analysis cancelled at %d/%d files.", processed, total
                )

            self.finished.emit(full_results)

        except Exception as exc:
            logger.critical(
                "Fatal error in analysis worker: %s", exc, exc_info=True
            )
            self.error.emit(str(exc))
            self.finished.emit(self._files)

        finally:
            # Always shutdown executor
            if self._executor:
                try:
                    # cancel_futures requires Python 3.9+
                    self._executor.shutdown(wait=False, cancel_futures=True)  # type: ignore
                except Exception:
                    self._executor.shutdown(wait=False)  # fallback
            # Ensure progress resets
            self.progress.emit(total, total)
            logger.info(
                "AdvancedAnalysisWorker exiting: processed=%d/%d, cancelled=%s",
                processed,
                total,
                self._cancelled,
            )
    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------
    def cancel(self) -> None:
        """
        Request cancellation: no new futures processed, current futures may or may not complete.
        """
        with self._lock:
            if self._cancelled:
                return
            self._cancelled = True
            logger.info("AdvancedAnalysisWorker cancellation requested.")
            if self._executor:
                try:
                    self._executor.shutdown(wait=False, cancel_futures=True)  # type: ignore
                except Exception:
                    self._executor.shutdown(wait=False)
