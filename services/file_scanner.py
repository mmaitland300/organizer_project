"""
FileScannerService – a background service for scanning directories for files.

This module implements the scanning logic in a QThread, reporting progress and handling cancellation.
"""

import os
import datetime
import logging
from typing import List, Dict, Optional, Any
from PyQt5 import QtCore
from config.settings import MAX_HASH_FILE_SIZE, HASH_TIMEOUT_SECONDS, AUDIO_EXTENSIONS, ENABLE_ADVANCED_AUDIO_ANALYSIS, TinyTag, librosa, np
from utils.helpers import compute_hash, detect_key_from_filename
from services.cache_manager import CacheManager
from services.database_manager import DatabaseManager

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

                    # Base metadata
                    file_info: Dict[str, Any] = {
                        'path': full_path,
                        'size': size,
                        'mod_time': mod_time,
                        'duration': None,
                        'bpm': None,
                        'key': "N/A",
                        'used': False,
                        'tags': {"filetype": [extension]} if extension else {}
                    }

                    # See if there's an existing DB record
                    existing_record = DatabaseManager.instance().get_file_record(full_path)
                    if existing_record:
                        # Merge DB data
                        file_info.update(existing_record)

                    # If it's an audio file, check BPM if user wants it.
                    if extension.lower() in [ext.lower() for ext in AUDIO_EXTENSIONS]:
                        # Attempt TinyTag read
                        if TinyTag is not None:
                            try:
                                tag = TinyTag.get(full_path)
                                file_info['duration'] = tag.duration
                                file_info['samplerate'] = tag.samplerate
                                file_info['channels'] = tag.channels
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
                                    file_info['bpm'] = new_bpm
                                    logger.debug(f"BPM DETECTED for {full_path}: {new_bpm}")
                                else:
                                    logger.warning(f"No audio data for BPM detection: {full_path}")
                                    file_info['bpm'] = None
                            except Exception as e:
                                logger.error(f"Error computing BPM for {full_path}: {e}", exc_info=True)
                                file_info['bpm'] = None

                    # Save updated record in DB
                    DatabaseManager.instance().save_file_record(file_info)

                    # Also keep in local list for immediate reference
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