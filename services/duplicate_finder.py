"""
DuplicateFinderService – a background service for finding duplicate files.

It groups files by size and then by an MD5 hash (computed with timeout and file size limits).
"""
from __future__ import annotations
import os

import logging
from typing import List, Dict, Any, Optional
from PyQt5 import QtCore
from utils.helpers import compute_hash  # Fallback for rare synchronous call
from .hash_worker import HashWorker

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class DuplicateFinderService(QtCore.QThread):
    """
    Finds duplicate files using file size grouping and MD5 hashing.

    Emits:
      - progress(current, total): progress of the hashing operation
      - finished(duplicate_groups): list of duplicate file groups
    """
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)

    def __init__(
        self,
        files_info: List[Dict[str, Any]],
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.files_info = files_info
        self._cancelled = False
        self._hash_worker: Optional[HashWorker] = None

    def run(self) -> None:  # noqa: D401 – imperative mood
        # 1. Offload MD5 computation for missing hashes
        need_hash = [fi for fi in self.files_info if not fi.get("hash")]
        total_files = len(self.files_info)

        if need_hash and not self._cancelled:
            self._hash_worker = HashWorker(need_hash)
            self._hash_worker.progress.connect(self.progress.emit)

            # Block until hashing completes
            loop = QtCore.QEventLoop()
            self._hash_worker.finished.connect(lambda _: loop.quit())
            self._hash_worker.start()
            loop.exec_()
            # HashWorker populates fi["hash"] in place

        if self._cancelled:
            self.finished.emit([])
            return

        # 2. Group by size then by hash
        size_map: Dict[int, List[Dict[str, Any]]] = {}
        for fi in self.files_info:
            size_map.setdefault(fi["size"], []).append(fi)

        duplicate_groups: List[List[Dict[str, Any]]] = []
        processed = 0
        for group in size_map.values():
            if self._cancelled:
                self.finished.emit([])
                return
            if len(group) < 2:
                processed += len(group)
                continue

            hash_map: Dict[str, List[Dict[str, Any]]] = {}
            for fi in group:
                if not fi.get("hash"):
                    fi["hash"] = compute_hash(fi["path"])
                if fi.get("hash"):
                    hash_map.setdefault(fi["hash"], []).append(fi)
                processed += 1
                if processed % 5 == 0:
                    self.progress.emit(processed, total_files)

            for dup in hash_map.values():
                if len(dup) > 1:
                    duplicate_groups.append(dup)

        # Finalize
        self.progress.emit(total_files, total_files)
        self.finished.emit(duplicate_groups)

    def cancel(self) -> None:
        """Cancel duplicate detection gracefully."""
        self._cancelled = True
        if self._hash_worker and self._hash_worker.isRunning():
            self._hash_worker.cancel()
        logger.info("Duplicate detection cancelled.")