"""
DuplicateFinderService – a background service for finding duplicate files.

It groups files by size and then by an MD5 hash (computed with timeout and file size limits).
"""

import os
import logging
from typing import List, Dict, Any, Optional
from PyQt5 import QtCore
from utils.helpers import compute_hash

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
    
    def __init__(self, files_info: List[Dict[str, Any]], parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.files_info = files_info
        self._cancelled = False
        
    def run(self) -> None:
        size_dict = {}
        for file_info in self.files_info:
            size = file_info.get('size')
            size_dict.setdefault(size, []).append(file_info)
        
        total_for_progress = len(self.files_info)
        current_count = 0
        duplicate_groups = []
        
        for group in size_dict.values():
            if self._cancelled:
                self.finished.emit([])
                return
            if len(group) > 1:
                hash_dict = {}
                for fi in group:
                    if self._cancelled:
                        self.finished.emit([])
                        return
                    if 'hash' not in fi or fi['hash'] is None:
                        fi['hash'] = compute_hash(fi['path'])
                    h = fi.get('hash')
                    if h:
                        hash_dict.setdefault(h, []).append(fi)
                    current_count += 1
                    if current_count % 5 == 0:
                        self.progress.emit(current_count, total_for_progress)
                for hash_group in hash_dict.values():
                    if len(hash_group) > 1:
                        duplicate_groups.append(hash_group)
            else:
                current_count += len(group)
                self.progress.emit(current_count, total_for_progress)
        self.finished.emit(duplicate_groups)
    
    def cancel(self) -> None:
        """Cancel duplicate detection."""
        self._cancelled = True
        logger.info("Duplicate detection cancelled.")