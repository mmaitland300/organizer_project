# Required Imports
import os
import datetime
import time
import threading
import logging
from PyQt5 import QtCore
from PyQt5.QtCore import QRunnable, pyqtSlot
from typing import Optional

from utils.helpers import compute_hash, bytes_to_unit, format_duration, detect_key_from_filename
from utils.cache_manager import CacheManager

from config.settings import MAX_HASH_FILE_SIZE, HASH_TIMEOUT_SECONDS, AUDIO_EXTENSIONS, ENABLE_ADVANCED_AUDIO_ANALYSIS
from config.settings import TinyTag, librosa, np

# Setup logger for this module
logger = logging.getLogger(__name__)

# Create a module-level cache_manager instance if needed
cache_manager = CacheManager()

# -------------------------- File Scanning --------------------------
class FileScanner(QtCore.QThread):
    """
    Thread to scan a directory recursively and extract file metadata,
    including advanced audio analysis.
    Emits progress and a list of file info dictionaries.
    """
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)

    def __init__(self, root_path: str, bpm_detection: bool = True, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.root_path = root_path
        self.bpm_detection = bpm_detection
        self._cancelled = False

    def run(self) -> None:
        total_files = 0
        for _, _, filenames in os.walk(self.root_path):
            total_files += len(filenames)
        files_info = []
        current_count = 0
        for dirpath, _, filenames in os.walk(self.root_path):
            # Before processing each directory, check for cancellation.
            if self._cancelled:
                self.finished.emit(files_info)  # Optionally return what was scanned so far.
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
                    
                    extension = os.path.splitext(f)[1][1:].upper() if os.path.splitext(f)[1] else ""
                    file_info = {
                        'path': full_path,
                        'size': size,
                        'mod_time': mod_time,
                        'duration': None,
                        'bpm': None,
                        'key': "N/A",
                        'used': False,
                        'tags': {"filetype": [extension]} if extension else {}
                    }

                    cached = cache_manager.get(full_path, mod_time_ts, size)
                    if cached:
                        file_info.update(cached)
                    else:
                        ext = os.path.splitext(full_path)[1].lower()
                        if ext in AUDIO_EXTENSIONS:
                            if TinyTag is not None:
                                try:
                                    tag = TinyTag.get(full_path)
                                    file_info['duration'] = tag.duration
                                    file_info['samplerate'] = tag.samplerate
                                    file_info['channels'] = tag.channels
                                except Exception as e:
                                    logger.error(f"Error reading audio metadata for {full_path}: {e}")
                            if ENABLE_ADVANCED_AUDIO_ANALYSIS and self.bpm_detection:
                                try:
                                    y, sr = librosa.load(full_path,
                                                          sr=None,
                                                          offset=0.0,
                                                          duration=60.0,
                                                          dtype=np.float32,
                                                          res_type='kaiser_best')
                                    if y is None or len(y) == 0:
                                        logger.warning(f"Warning: {full_path} produced no audio data.")
                                        file_info['bpm'] = None
                                    else:
                                        tempo = librosa.beat.tempo(y=y, sr=sr)
                                        file_info['bpm'] = round(float(tempo[0])) if tempo.size > 0 else None
                                except Exception as e:
                                    logger.error(f"Error computing BPM for {full_path}: {e}", exc_info=True)
                                    file_info['bpm'] = None
                        else:
                            file_info['bpm'] = None

                        file_info['key'] = detect_key_from_filename(full_path)
                        
                        cache_manager.update(full_path, mod_time_ts, size, {
                            'duration': file_info.get('duration'),
                            'bpm': file_info.get('bpm'),
                            'key': file_info.get('key'),
                            'samplerate': file_info.get('samplerate', None),
                            'channels': file_info.get('channels', None)
                        })
                    files_info.append(file_info)
                except Exception as e:
                    logger.error(f"Error scanning {full_path}: {e}")
                
                current_count += 1
                if current_count % 100 == 0:
                    self.progress.emit(current_count, total_files)
        cache_manager.save_cache()
        self.finished.emit(files_info)

    def cancel(self):
        """Allow cancellation of the scanning process."""
        self._cancelled = True

# -------------------------- Hash Worker --------------------------
class HashWorker(QRunnable):
    def __init__(self, file_info):
        super().__init__()
        self.file_info = file_info

    @pyqtSlot()
    def run(self):
        file_path = self.file_info['path']
        hash_result = compute_hash(file_path)
        self.file_info['hash'] = hash_result
