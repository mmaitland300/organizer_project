"""
FileScannerService – a background service for scanning directories for files.

This module implements the scanning logic in a QThread, reporting progress and handling cancellation.
"""

import os
import datetime
import logging
from typing import List, Dict, Optional, Any

from PyQt5 import QtCore
from config.settings import (
    MAX_HASH_FILE_SIZE,
    HASH_TIMEOUT_SECONDS,
    AUDIO_EXTENSIONS,
    ENABLE_ADVANCED_AUDIO_ANALYSIS,
    TinyTag,
    librosa,
    np
)
from utils.helpers import compute_hash, detect_key_from_filename
from services.cache_manager import CacheManager
from services.database_manager import DatabaseManager
from services.analysis_engine import AnalysisEngine

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class FileScannerService(QtCore.QThread):
    """
    Scans a directory recursively and extracts file metadata and audio analysis.

    Emits:
      - progress(current, total): progress of file scanning
      - finished(files_info): a list of file metadata dictionaries after scanning
    """
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)

    def __init__(
        self,
        root_path: str,
        bpm_detection: bool = True,
        parent: Optional[QtCore.QObject] = None
    ) -> None:
        super().__init__(parent)
        self.root_path = root_path
        self.bpm_detection = bpm_detection
        self._cancelled = False
        self.cache_manager = CacheManager()

    def run(self) -> None:
        total_files = 0
        for _, _, filenames in os.walk(self.root_path):
            total_files += len(filenames)

        files_info: List[Dict[str, Any]] = []
        current_count = 0

        for dirpath, _, filenames in os.walk(self.root_path):
            if self._cancelled:
                self.finished.emit(files_info)
                return

            for f in filenames:
                if self._cancelled:
                    self.finished.emit(files_info)
                    return

                raw_path = os.path.join(dirpath, f)
                full_path = os.path.normpath(os.path.abspath(raw_path))

                try:
                    # Basic file stats
                    stat = os.stat(full_path)
                    size = stat.st_size
                    mod_time_ts = stat.st_mtime
                    mod_time = datetime.datetime.fromtimestamp(mod_time_ts)

                    extension = os.path.splitext(f)[1].lower()

                    # Base metadata structure
                    file_info: Dict[str, Any] = {
                        "path": full_path,
                        "size": size,
                        "mod_time": mod_time,
                        "duration": None,
                        "key": "N/A",     # if you detect musical key from file name or code
                        "used": False,
                        "tags": {"filetype": [extension]} if extension else {}
                    }

                    # Pull existing record from DB (if any)
                    existing_record = DatabaseManager.instance().get_file_record(full_path)
                    if existing_record:
                        file_info.update(existing_record)

                    # If it's an audio file, gather audio metadata
                    if extension in AUDIO_EXTENSIONS:
                        # Use TinyTag for duration, samplerate, etc.
                        if TinyTag is not None:
                            try:
                                tag = TinyTag.get(full_path)
                                file_info["duration"] = tag.duration
                                file_info["samplerate"] = tag.samplerate
                                file_info["channels"] = tag.channels
                            except Exception as e:
                                logger.error(f"Error reading audio metadata for {full_path}: {e}")

                        # BPM detection if user requests it
                        if self.bpm_detection and ENABLE_ADVANCED_AUDIO_ANALYSIS and librosa is not None:
                            try:
                                y, sr = librosa.load(
                                    full_path,
                                    sr=None,
                                    offset=0.0,
                                    duration=60.0,
                                    dtype=np.float32,
                                    res_type='kaiser_best'
                                )
                                if y is not None and len(y) > 0:
                                    tempo = librosa.beat.tempo(y=y, sr=sr)
                                    new_bpm = round(float(tempo[0])) if tempo.size > 0 else None
                                    if new_bpm is not None:
                                        # Store BPM in tags as its own dimension
                                        file_info["tags"].setdefault("bpm", [])
                                        file_info["tags"]["bpm"] = [str(new_bpm)]
                                        logger.debug(f"BPM DETECTED for {full_path}: {new_bpm}")
                                else:
                                    logger.warning(f"No audio data for BPM detection: {full_path}")
                            except Exception as e:
                                logger.error(f"Error computing BPM for {full_path}: {e}", exc_info=True)

                        # Advanced DSP from analysis_engine
                        adv_features = AnalysisEngine.analyze_audio_features(full_path, max_duration=60.0)
                        # For each metric (brightness, loudness_rms, stereo_width, etc.),
                        # store them as separate dimensions in tags
                        for metric_name, metric_val in adv_features.items():
                            file_info["tags"].setdefault(metric_name, [])
                            # Convert numeric to string so it appears as a 'tag'
                            file_info["tags"][metric_name] = [f"{metric_val:.3f}"]

                    # Save / update DB record
                    DatabaseManager.instance().save_file_record(file_info)

                    # Also add to local result list
                    files_info.append(file_info)

                except Exception as e:
                    logger.error(f"Error scanning {full_path}: {e}")

                current_count += 1
                if current_count % 100 == 0:
                    self.progress.emit(current_count, total_files)

        # After scanning
        self.cache_manager.save_cache()
        self.progress.emit(total_files, total_files)
        self.finished.emit(files_info)

    def cancel(self) -> None:
        """Cancel the scanning process."""
        self._cancelled = True
        logger.info("File scanning cancelled.")
        self.cache_manager.save_cache()
