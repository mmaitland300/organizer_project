# services/file_scanner.py
"""
FileScannerService – scans directories for files and basic metadata using os.scandir
for efficient enumeration. Batch‑writes metadata to the database for performance.
Hashing is deferred to DuplicateFinderService.
"""

import os
import datetime
import logging
from typing import List, Dict, Optional, Any, Generator

from PyQt5 import QtCore

from config.settings import (
    AUDIO_EXTENSIONS,
    ENABLE_ADVANCED_AUDIO_ANALYSIS,
    TinyTag,
    librosa,
)
from services.cache_manager import CacheManager
from services.database_manager import DatabaseManager

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def scan_file_paths(root_path: str) -> Generator[str, None, None]:
    """Recursively yield file paths using os.scandir."""
    with os.scandir(root_path) as it:
        for entry in it:
            if entry.is_dir(follow_symlinks=False):
                yield from scan_file_paths(entry.path)
            elif entry.is_file(follow_symlinks=False):
                yield entry.path


def _emit_progress(signal: QtCore.pyqtSignal, cur: int, total: int) -> None:
    if cur % 100 == 0 or cur >= total:
        signal.emit(cur, total)


class FileScannerService(QtCore.QThread):
    """
    Scans a directory recursively and extracts basic file metadata and optional BPM detection.
    
    Emits:
      - progress(current: int, total: int)
      - finished(files_info: List[Dict[str, Any]])
    """

    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)

    def __init__(
        self,
        root_path: str,
        bpm_detection: bool = True,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.root_path = root_path
        self.bpm_detection = bpm_detection
        self._cancelled = False
        self._cache = CacheManager()

    def run(self) -> None:  # noqa: D401 – imperative mood
        logger.info(f"Starting scan of {self.root_path}")
        # Enumerate all file paths efficiently
        file_paths = list(scan_file_paths(self.root_path))
        total_files = len(file_paths)
        files_info: List[Dict[str, Any]] = []
        processed = 0
        audio_exts = {e.lower() for e in AUDIO_EXTENSIONS}

        for full_path in file_paths:
            if self._cancelled:
                break
            try:
                stat = os.stat(full_path)
                size = stat.st_size
                mtime_ts = stat.st_mtime
                mtime_dt = datetime.datetime.fromtimestamp(mtime_ts)
                _, ext = os.path.splitext(full_path)
                ext = ext.lower()

                # Cache hit?
                if not self._cache.needs_update(full_path, mtime_ts, size):
                    cached = self._cache.get(full_path, mtime_ts, size)
                    if cached:
                        files_info.append(cached)
                        processed += 1
                        _emit_progress(self.progress, processed, total_files)
                        continue

                # DB record reuse
                existing = DatabaseManager.instance().get_file_record(full_path)
                if existing and existing.get("mod_time") == mtime_dt:
                    files_info.append(existing)
                    processed += 1
                    _emit_progress(self.progress, processed, total_files)
                    continue

                info: Dict[str, Any] = {
                    "path": full_path,
                    "size": size,
                    "mod_time": mtime_dt,
                    "duration": None,
                    "bpm": None,
                    "key": "N/A",
                    "used": False,
                    "tags": {"filetype": [ext]} if ext else {},
                }

                # Audio metadata via TinyTag
                if ext in audio_exts and TinyTag is not None:
                    try:
                        tag = TinyTag.get(full_path)
                        info["duration"] = tag.duration
                        info["samplerate"] = tag.samplerate
                        info["channels"] = tag.channels
                    except Exception as e:
                        logger.error(f"TinyTag failed for {full_path}: {e}")

                # BPM detection
                if (
                    ext in audio_exts
                    and self.bpm_detection
                    and ENABLE_ADVANCED_AUDIO_ANALYSIS
                    and librosa is not None
                ):
                    try:
                        y, sr = librosa.load(full_path, sr=None, duration=60.0, mono=True)
                        tempo = librosa.beat.tempo(y=y, sr=sr)
                        bpm_val = int(tempo[0]) if tempo.size > 0 else None
                        info["bpm"] = bpm_val
                        info.setdefault("tags", {}).setdefault("bpm", []).append(
                            str(bpm_val) if bpm_val else ""
                        )
                    except Exception as e:
                        logger.error(f"BPM error for {full_path}: {e}")

                files_info.append(info)
                self._cache.update(full_path, mtime_ts, size, info)

            except Exception as e:
                logger.error(f"Error scanning {full_path}: {e}")

            processed += 1
            _emit_progress(self.progress, processed, total_files)

        # log scan completion
        logger.info(f"Scan complete: {len(files_info)} files discovered")

        # Persist batch to DB
        if files_info:
            logger.debug(f"Batch-saving {len(files_info)} records to DB")
            DatabaseManager.instance().save_file_records(files_info)

        # Finalize
        self._cache.flush()
        self.progress.emit(total_files, total_files)
        self.finished.emit(files_info)

    def cancel(self) -> None:
        self._cancelled = True
        logger.info("FileScannerService cancelled.")
