"""
FileScannerService - a background service for scanning directories for files.

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
    ENABLE_ADVANCED_AUDIO_ANALYSIS,  # still used for BPM detection if desired
    TinyTag,
    librosa,
    np
)
from utils.helpers import compute_hash, detect_key_from_filename
from services.cache_manager import CacheManager
from services.database_manager import DatabaseManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class FileScannerService(QtCore.QThread):
    """
    Scans a directory recursively and extracts basic file metadata and optional BPM detection.
    
    Emits:
      - progress(current, total): progress of file scanning
      - finished(files_info): a list of file metadata dictionaries after scanning
    """
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)
    
    def __init__(self, root_path: str, bpm_detection: bool = True, parent: Optional[QtCore.QObject] = None) -> None:
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
        audio_exts = [ext.lower() for ext in AUDIO_EXTENSIONS]

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
                        "bpm": None,
                        "key": "N/A",
                        "used": False,
                        "tags": {"filetype": [extension]} if extension else {}
                    }

                    # Merge existing DB record if available
                    existing_record = DatabaseManager.instance().get_file_record(full_path)
                    if existing_record and existing_record.get("mod_time") == mod_time:
                        files_info.append(existing_record)
                        continue  # Skip further processing for unchanged files

                    # Process audio files for metadata and BPM if applicable:
                    if extension in audio_exts:
                        # --- BEGIN: Quick WAV Header Check ---
                        if extension == ".wav":
                            try:
                                with open(full_path, "rb") as f_obj:
                                    header = f_obj.read(4)
                                if header != b'RIFF':
                                    # Log the error
                                    logger.warning(f"Skipping advanced audio processing for file with invalid WAV header: {full_path}")
                                    # Mark the file as having an invalid header in its tags
                                    file_info.setdefault("tags", {})
                                    file_info["tags"]["invalid_audio"] = ["true"]
                                    # do not execute further audio processing (TinyTag or BPM detection) if desired
                                    # still add the file_info to the results so it shows up
                                    DatabaseManager.instance().save_file_record(file_info)
                                    files_info.append(file_info)
                                    current_count += 1
                                    if current_count % 100 == 0:
                                        self.progress.emit(current_count, total_files)
                                    # Skip further processing for this file and continue with next
                                    continue
                            except Exception as e:
                                logger.error(f"Error checking WAV header for {full_path}: {e}")
                                # In case of error in checking, you might choose to skip processing for this file too.
                                file_info.setdefault("tags", {})
                                file_info["tags"]["invalid_audio"] = ["true"]
                                DatabaseManager.instance().save_file_record(file_info)
                                files_info.append(file_info)
                                current_count += 1
                                if current_count % 100 == 0:
                                    self.progress.emit(current_count, total_files)
                                continue
                        # --- END: Quick WAV Header Check ---
                        if TinyTag is not None:
                            try:
                                tag = TinyTag.get(full_path)
                                file_info["duration"] = tag.duration
                                file_info["samplerate"] = tag.samplerate
                                file_info["channels"] = tag.channels
                            except Exception as e:
                                logger.error(f"Error reading audio metadata for {full_path}: {e}")

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
                                    # Save BPM as a tag dimension
                                    file_info["tags"].setdefault("bpm", [])
                                    file_info["tags"]["bpm"] = [str(new_bpm)]
                                    # Optionally, also set top-level BPM if desired:
                                    file_info["bpm"] = new_bpm
                                    logger.debug(f"BPM DETECTED for {full_path}: {new_bpm}")
                                else:
                                    logger.warning(f"No audio data for BPM detection: {full_path}")
                                    file_info["tags"].setdefault("bpm", [])
                                    file_info["tags"]["bpm"] = [""]
                            except Exception as e:
                                logger.error(f"Error computing BPM for {full_path}: {e}", exc_info=True)
                    
                    # Save / update the file record in the DB
                    DatabaseManager.instance().save_file_record(file_info)
                    files_info.append(file_info)

                except Exception as e:
                    logger.error(f"Error scanning {full_path}: {e}")

                current_count += 1
                if current_count % 100 == 0:
                    self.progress.emit(current_count, total_files)

        self.cache_manager.save_cache()
        self.progress.emit(total_files, total_files)
        self.finished.emit(files_info)
    
    def cancel(self) -> None:
        """Cancel the scanning process."""
        self._cancelled = True
        logger.info("File scanning cancelled.")
        self.cache_manager.save_cache()

