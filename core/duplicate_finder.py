# File: core/duplicate_finder.py

import os
from PyQt5 import QtCore
from typing import List, Dict, Any, Optional
from utils.helpers import compute_hash

class DuplicateFinder(QtCore.QThread):
    """
    QThread to find duplicates among a list of file info dictionaries.
    Emits progress signals so that the UI can remain responsive.
    """
    progress = QtCore.pyqtSignal(int, int)       # (current, total)
    finished = QtCore.pyqtSignal(list)           # emits duplicate_groups list

    def __init__(self, files_info: List[Dict[str, Any]], parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.files_info = files_info
        self._cancelled = False

    def run(self):
        """
        Locate duplicate files by size, then by hash, emitting progress signals.
        Finally emit finished with the duplicate groups.
        """
        # 1) Group files by size
        size_dict = {}
        for file_info in self.files_info:
            size = file_info['size']
            size_dict.setdefault(size, []).append(file_info)

        # Track progress across all files we process in hashing
        # Count how many files we will potentially hash
        total_for_progress = len(self.files_info)
        current_count = 0
        duplicate_groups = []
        
        # 2) For each group with more than 1 file, group by MD5
        for group in size_dict.values():
            if self._cancelled:
                self.finished.emit([]) 
                return
            if len(group) > 1:
                hash_dict = {}
                for fi in group:
                    if self._cancelled:
                        self.finished.emit([])  # Early return if cancelled.
                        return
                    if 'hash' not in fi or fi['hash'] is None:
                        fi['hash'] = compute_hash(fi['path'])
                    h = fi['hash']
                    if h:
                        hash_dict.setdefault(h, []).append(fi)
                    current_count += 1
                    if current_count % 5 == 0:
                        self.progress.emit(current_count, total_for_progress)
                for hash_group in hash_dict.values():
                    if len(hash_group) > 1:
                        duplicate_groups.append(hash_group)
            else:
                # small optimization if group size=1 we do no hashing
                current_count += len(group)
                self.progress.emit(current_count, total_for_progress)
        self.finished.emit(duplicate_groups)

    def cancel(self):
        """Set cancellation flag for duplicate detection."""
        self._cancelled = True
