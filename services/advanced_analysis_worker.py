# services/advanced_analysis_worker.py
"""
Parallel AdvancedAnalysisWorker for Musicians Organizer.

Uses ProcessPoolExecutor context manager and a multiprocessing Event for
cancellation. Emits progress before processing results for better UI update.
Adjusted manager shutdown timing.
"""
# --- (Keep all imports and the _analyze_file_process_worker function as before) ---
from __future__ import annotations
import concurrent.futures as _cf
import logging
import os
import threading
import time
import math
import copy
from typing import Any, Dict, List, Optional
from multiprocessing import Manager, Event as MPEvent
import traceback

from services.database_manager import DatabaseManager
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from services.database_manager import DatabaseManager

from PyQt5 import QtCore, QtWidgets
from services.analysis_engine import AnalysisEngine

try:
    from config.settings import AUDIO_EXTENSIONS, ALL_FEATURE_KEYS
except ImportError:
    AUDIO_EXTENSIONS = {".wav", ".aiff", ".flac", ".mp3", ".ogg"}
    ALL_FEATURE_KEYS: List[str] = []

logger = logging.getLogger(__name__)

def _analyze_file_process_worker(file_info: Dict[str, Any], cancel_event: MPEvent) -> Optional[Dict[str, Any]]: # type: ignore
    # --- (Worker function code remains identical to the previous version) ---
    path = file_info.get("path", "Unknown Path")
    try:
        if cancel_event.is_set(): return None # Check 1

        ext = os.path.splitext(path)[1].lower()
        if ext not in AUDIO_EXTENSIONS: return None

        # Pass cancel_event down - relies on AnalysisEngine implementing checks
        adv = AnalysisEngine.analyze_audio_features(path, cancel_event=cancel_event) # max_duration uses default from engine

        if cancel_event.is_set(): return None # Check 2 (after analysis call returns)

        if adv and isinstance(adv, dict) and adv: # Check if results are meaningful
            output = None; changed = False
            for key, value in adv.items():
                 # Only copy/update if key is relevant and value changed
                # Ensure file_info is checked for key presence robustly
                # Check if the key exists in the original dict before comparing
                original_value = file_info.get(key, object()) # Use a sentinel default
                if value != original_value:
                    if output is None: output = copy.deepcopy(file_info)
                    output[key] = value
                    changed = True

            if changed and output is not None: return output # Return updated dict
            else: return None # No change needed
        else: return None # Analysis failed or no data

    except Exception as e:
        tb_str = traceback.format_exc()
        print(f"[Worker Process Error] {path}: {e}\nTraceback:\n{tb_str}")
        return None

class AdvancedAnalysisWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int, int)
    # Rename custom signal to avoid conflict with QThread.finished
    analysisComplete = QtCore.pyqtSignal(list)
    error = QtCore.pyqtSignal(str)
    PROCESS_EVENTS_EVERY_N_FILES = 5

    def __init__(
        self, files: List[Dict[str, Any]], db_manager: "DatabaseManager",
        parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)
        self._files_orig = list(files); self._cancelled = False
        self._lock = threading.Lock(); self.db_manager = db_manager
        self._mp_manager = Manager(); self.cancel_event = self._mp_manager.Event()
        cpu_count = os.cpu_count() or 1
        default_workers = max(1, cpu_count - 1)
        self._max_workers = min(default_workers, 8)
        logger.info(f"AdvWorker init: max_workers={self._max_workers}")

    def run(self) -> None:
        total = len(self._files_orig)
        if total == 0: self.finished.emit([]); return
        processed = 0; self.cancel_event.clear()
        results_map: Dict[str, Dict[str, Any]] = {fi["path"]: fi for fi in self._files_orig}
        db_updates: List[Dict[str, Any]] = []
        logger.info(f"Starting analysis: {total} files, {self._max_workers} workers")
        run_cancelled = False

        try:
            with _cf.ProcessPoolExecutor(max_workers=self._max_workers) as executor:
                futures_map = {
                    executor.submit(_analyze_file_process_worker, fi, self.cancel_event): fi["path"]
                    for fi in self._files_orig
                }

                for future in _cf.as_completed(futures_map):
                    with self._lock:
                        if self._cancelled:
                            logger.info("Cancellation detected, breaking results loop.")
                            run_cancelled = True; break

                    processed += 1
                    orig_path = futures_map[future]
                    self.progress.emit(processed, total) # Emit progress BEFORE result

                    # *** Process events AFTER EVERY future is processed ***
                    QtWidgets.QApplication.processEvents()
                    # Re-check cancellation immediately after processing events
                    with self._lock:
                        if self._cancelled:
                            logger.info("Cancellation detected after processEvents, breaking loop.")
                            run_cancelled = True; break
                    # *** End Process Events Change ***
                    try:
                        updated_dict = future.result()
                        if updated_dict:
                            results_map[orig_path] = updated_dict
                            db_updates.append(updated_dict)
                    except _cf.process.BrokenProcessPool as bpe:
                         logger.error(f"Process Pool broke: {bpe}", exc_info=True); self.error.emit("Analysis process pool failed.")
                         with self._lock: self._cancelled = True; run_cancelled = True
                         break
                    except Exception as e: logger.error(f"Future exception for {orig_path}: {e}", exc_info=True)

            logger.info("Finished processing results loop.")
            logger.info("Process pool context exited (shutdown called).")

            if not run_cancelled and db_updates:
                logger.info(f"Saving {len(db_updates)} updated records...")
                try:
                    self.db_manager.save_file_records(db_updates)
                    logger.info("DB save complete.")
                except Exception as e: logger.error(f"DB write failed: {e}", exc_info=True); self.error.emit(f"DB write fail: {e}")

            final_results = [results_map.get(fi["path"], fi) for fi in self._files_orig]
            with self._lock: is_cancelled = self._cancelled
            logger.info(f"Analysis run finished - {'Cancelled' if is_cancelled else 'Completed normally'}.")
            self.analysisComplete.emit(final_results) # Emit renamed data signal

        except Exception as exc:
            logger.critical(f"Fatal error in worker run: {exc}", exc_info=True)
            self.error.emit(f"Analysis Worker Error: {exc}")
            self.finished.emit(self._files_orig)
        finally:
             final_processed = processed # Capture final count
             # --- Shutdown manager BEFORE final logs/signal ---
             logger.info("Shutting down multiprocessing manager...")
             try: self._mp_manager.shutdown()
             except Exception as manager_exc: logger.error(f"Error shutting down mp manager: {manager_exc}", exc_info=True)
             logger.info("Multiprocessing manager shut down.")
             # --- Emit final progress AFTER manager shutdown ---
             self.progress.emit(final_processed, total)
             logger.info("AdvancedAnalysisWorker run method finished completely.") # Last log before exit

    def cancel(self) -> None:
        # --- (Cancel method remains identical to previous version) ---
        logger.info("AdvancedAnalysisWorker cancellation requested.")
        with self._lock:
            if self._cancelled: return
            self._cancelled = True
            cancel_event_exists = hasattr(self, 'cancel_event') and self.cancel_event
        if cancel_event_exists:
             logger.info("Setting multiprocessing cancel event.")
             try: self.cancel_event.set()
             except Exception as e: logger.error(f"Failed to set cancel event: {e}", exc_info=True)
        else: logger.warning("Cancel called but cancel_event does not exist or is None.")
        logger.info("Cancellation flag set and event set (if possible).")