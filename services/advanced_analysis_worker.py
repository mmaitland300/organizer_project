import os
import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import OrderedDict
from PyQt5 import QtCore
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.database_manager import DatabaseManager
from services.analysis_engine import AnalysisEngine
from config.settings import AUDIO_EXTENSIONS

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Helper function to run analysis for a single file (top-level for threading compatibility)
def _analyze_single_file(file_path: str) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Analyzes a single audio file using AnalysisEngine.

    Args:
        file_path: Path to the audio file.

    Returns:
        A tuple containing the file path and the dictionary of
        extracted features, or (file_path, None) if an error occurs.
    """
    try:
        adv_features = AnalysisEngine.analyze_audio_features(file_path, max_duration=60.0)
        return file_path, adv_features
    except Exception as e:
        logger.error(f"Error analyzing advanced features for {file_path}: {e}", exc_info=False)
        return file_path, None

class AdvancedAnalysisWorker(QtCore.QThread):
    """
    Worker thread that runs advanced DSP analysis on a list of files using
    a ThreadPoolExecutor for parallelism and responsive progress updates.

    Expects a list of file records (dictionaries) as input.
    For each file, it:
      - Filters for valid audio extensions.
      - Submits analysis tasks to a thread pool.
      - Merges results back into the file_info dict.
      - Stores each metric as its own tag dimension.
      - Batch-saves updated records to the database.

    Emits:
       progress(current: int, total: int)
       finished(updated_files: List[Dict[str, Any]])
    """
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)

    def __init__(self, files: List[Dict[str, Any]], parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        # Map file paths to their metadata dicts
        self.files_map: Dict[str, Dict[str, Any]] = {f['path']: f for f in files if 'path' in f}
        self._cancelled = False
        self.valid_audio_paths_to_process: List[str] = self._filter_valid_audio_paths()

    def _filter_valid_audio_paths(self) -> List[str]:
        """Filters the initial file list for valid audio files."""
        valid_paths = []
        audio_ext_set = {ext.lower() for ext in AUDIO_EXTENSIONS}
        for path, file_info in self.files_map.items():
            tags = file_info.get("tags", {})
            filetypes = tags.get("filetype", [])
            extension = filetypes[0] if filetypes else os.path.splitext(path)[1].lower()
            if extension in audio_ext_set:
                valid_paths.append(path)
            else:
                logger.debug(f"Skipping advanced analysis for non-audio file: {path}")
        return valid_paths

    def run(self) -> None:
        total = len(self.valid_audio_paths_to_process)
        if total == 0:
            logger.info("AdvancedAnalysisWorker: No valid audio files found to process.")
            self.finished.emit(list(self.files_map.values()))
            return

        logger.info(f"AdvancedAnalysisWorker: Analyzing {total} files in parallel.")
        updated_batch: List[Dict[str, Any]] = []
        processed = 0
        max_workers = min(os.cpu_count() or 1, 4)

        # ProcessPool replaced with ThreadPoolExecutor for mocking compatibility
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_analyze_single_file, path): path
                       for path in self.valid_audio_paths_to_process}
            for future in as_completed(futures):
                path = futures[future]
                if self._cancelled:
                    logger.info("AdvancedAnalysisWorker cancelled during processing.")
                    break
                try:
                    file_path, features = future.result()
                    if features and file_path == path:
                        info = self.files_map[path]
                        info.setdefault("tags", {})
                        # Merge new features
                        for name, val in features.items():
                            if name.lower() == "filetype":
                                continue
                            formatted = f"{val:.3f}" if isinstance(val, float) else str(val)
                            info["tags"][name] = [formatted]
                        # Preserve existing BPM tag
                        if "bpm" in info and info["bpm"] is not None:
                            info["tags"]["bpm"] = [str(info["bpm"])]
                        # Reorder tags
                        orig = info.get("tags", {})
                        if "filetype" in orig:
                            ordered = OrderedDict()
                            ordered["filetype"] = orig["filetype"]
                            for k, v in orig.items():
                                if k != "filetype": ordered[k] = v
                            info["tags"] = ordered
                        updated_batch.append(info)
                        logger.debug(f"Analyzed {path}")
                except Exception as e:
                    logger.error(f"Error processing {path}: {e}", exc_info=True)
                finally:
                    processed += 1
                    self.progress.emit(processed, total)

        if self._cancelled:
            self.finished.emit(list(self.files_map.values()))
            return

        # Batch save updated records
        if updated_batch:
            try:
                DatabaseManager.instance().save_file_records(updated_batch)
                logger.info(f"Saved {len(updated_batch)} records to DB.")
            except Exception as ex:
                logger.error(f"Batch save failed: {ex}", exc_info=True)
                self.finished.emit(list(self.files_map.values()))
                return

        self.finished.emit(list(self.files_map.values()))
        logger.info("AdvancedAnalysisWorker finished.")

    def cancel(self) -> None:
        """Request cancellation of processing."""
        logger.info("AdvancedAnalysisWorker cancellation requested.")
        self._cancelled = True
