# services/hash_worker.py

"""
HashWorker - dedicated QThread for computing MD5 hashes in the background.

Receives a list of file-info dictionaries, computes the hash (using helpers.compute_hash)
only when missing, and emits granular progress. Designed to be attached to longer‑running
services like DuplicateFinderService or a future FileScanner stage.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional

from PyQt5 import QtCore

from utils.helpers import compute_hash

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class HashWorker(QtCore.QThread):
    """Background thread that computes MD5 hashes for many files."""

    #: progress(current, total)
    progress = QtCore.pyqtSignal(int, int)
    #: finished(updated_files)
    finished = QtCore.pyqtSignal(list)

    def __init__(
        self,
        files_info: List[Dict[str, Any]],
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._files = files_info
        self._cancelled = False

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    def cancel(self) -> None:
        """Request cancellation (best‑effort)."""
        self._cancelled = True

    # ---------------------------------------------------------------------
    # QThread implementation
    # ---------------------------------------------------------------------
    def run(self) -> None:  # noqa: D401 – imperative mood OK
        total = len(self._files)
        processed = 0
        updated: List[Dict[str, Any]] = []

        for fi in self._files:
            if self._cancelled:
                logger.info("HashWorker cancelled – returning partial results (%s/%s)", processed, total)
                break

            # Compute hash only if missing or None
            if fi.get("hash") in (None, ""):
                fi["hash"] = compute_hash(fi["path"])
            updated.append(fi)
            processed += 1

            # Emit every 5 items or at the end to limit signal spam.
            if processed % 5 == 0 or processed == total:
                self.progress.emit(processed, total)

        self.finished.emit(updated)
