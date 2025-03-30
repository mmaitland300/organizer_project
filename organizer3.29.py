#!/usr/bin/env python3
"""
Musicians Organizer
An application for music producers and sound engineers to scan directories, display file details and help decide what can be removed.
Features:
  - Scanning with a progress bar (in a background thread)
  - Search/filter files by name via a QSortFilterProxyModel
  - Size unit toggle (KB, MB, GB)
  - Duplicate file detection and management with:
      • Detailed file metadata (path, size, modified date, MD5 hash)
      • Selective deletion (batch deletion with recycle bin support)
      • Open file location in OS file explorer
  - File size limit and timeout mechanism for hash computation
  - Recycle Bin integration for file deletion (via send2trash)
  - Persistence of user settings (window geometry, last folder, preferences)
  - Audio metadata extraction (duration, sample rate, channels) for music sample management
  - "Mark as Used" column and audio preview functionality for music producers
  - "Show Only Unused Samples" filter for music producers
  • Advanced audio analysis (BPM detection)
  • Advanced multi-dimensional tagging (editable Tags column + auto-tagging)
  • Smart sample recommendations based on similar BPM or tags
  • Enhanced visualization: waveform preview via an embedded matplotlib plot
  • Direct Cubase integration: set a Cubase folder and send samples there
  • Visual duplicate comparison with waveform preview in the Duplicate Manager
"""

import sys
import os
import datetime
import hashlib
import subprocess
import platform
import time
import shutil
import logging
import traceback
import warnings
import re
from typing import List, Any, Optional, Dict, Union

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl
from send2trash import send2trash

from organizer.utils import (
    bytes_to_unit,
    format_duration,
    open_file_location,
    compute_hash,
    unify_detected_key,
    detect_key_from_filename
)

warnings.filterwarnings("ignore", message="This function was moved to 'librosa.feature.rhythm.tempo'")
logger: logging.Logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


try:
    from tinytag import TinyTag
except ImportError:
    logger.warning("tinytag module not found. Audio metadata extraction will be disabled.")
    TinyTag = None

# Advanced audio analysis for BPM detection
try:
    import librosa
except ImportError:
    librosa = None

# Waveform preview dependencies: matplotlib and numpy
try:
    import matplotlib
    matplotlib.use("Qt5Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    import numpy as np
except ImportError:
    plt = None
    np = None
    FigureCanvas = None

# Global flags and constants
ENABLE_ADVANCED_AUDIO_ANALYSIS = (librosa is not None)
ENABLE_WAVEFORM_PREVIEW = (plt is not None and np is not None)
AUDIO_EXTENSIONS = {".wav", ".aiff", ".flac", ".mp3", ".ogg"}

KEY_REGEX = re.compile(
    r'(?:^|[^a-zA-Z])'                  # Start of string or non-alpha
    r'(?P<root>[A-G]'                   # Root letter
    r'(?:[#b]|-sharp|-flat)?'           # Optional #, b, -sharp, -flat
    r')'                                # End capture group for root
    r'(?:-|_| )?'                       # Optional dash/underscore/space
    r'(?P<quality>m(?:in(?:or)?)?|maj(?:or)?|minor|major)?'  # Optional chord quality
    r'(?:[^a-zA-Z]|$)',                 # Non-alpha or end of string
    flags=re.IGNORECASE
)


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
        """
        Initialize the FileScanner thread.
        
        Args:
            root_path (str): The directory to scan.
            bpm_detection (bool): Whether to perform BPM detection.
            parent (Optional[QtCore.QObject]): Parent object.
        """

        super().__init__(parent)
        self.root_path = root_path
        self.bpm_detection = bpm_detection

    def run(self) -> None:
        total_files = 0
        for _, _, filenames in os.walk(self.root_path):
            total_files += len(filenames)
        files_info = []
        current_count = 0
        for dirpath, _, filenames in os.walk(self.root_path):
            for f in filenames:
                raw_path = os.path.join(dirpath, f)
                full_path = os.path.normpath(os.path.abspath(raw_path))
                try:
                    stat = os.stat(full_path)
                    size = stat.st_size
                    mod_time = datetime.datetime.fromtimestamp(stat.st_mtime)
                    file_info = {
                        'path': full_path,
                        'size': size,
                        'mod_time': mod_time,
                        'duration': None,   # For audio files
                        'bpm': None,        # Advanced analysis: BPM
                        'key': "N/A",       # Placeholder for key detection
                        'used': False,      # Mark if file has been used
                        'tags': ""          # Custom tags (editable)
                    }
                    ext = os.path.splitext(full_path)[1].lower()
                    # Add default tag based on file extension
                    if ext:
                        file_info['tags'] = ext[1:].upper()

                    if ext in AUDIO_EXTENSIONS:
                        # Extract basic audio metadata with TinyTag if available
                        if TinyTag is not None:
                            try:
                                tag = TinyTag.get(full_path)
                                file_info['duration'] = tag.duration
                                file_info['samplerate'] = tag.samplerate
                                file_info['channels'] = tag.channels
                            except Exception as e:
                                logger.error(f"Error reading audio metadata for {full_path}: {e}")
                        # Perform BPM detection only if enabled
                        if ENABLE_ADVANCED_AUDIO_ANALYSIS and self.bpm_detection:
                            try:
                                logger.debug(f"Loading file {full_path} with explicit parameters")
                                y, sr = librosa.load(full_path,
                                                     sr=None,
                                                     offset=0.0,
                                                     duration=None,
                                                     dtype=np.float32,
                                                     res_type='kaiser_best')
                                if y is None or len(y) == 0:
                                    logger.warning(f"Warning: {full_path} produced no audio data.")
                                    file_info['bpm'] = None
                                else:
                                    # Use the deprecated alias with keyword arguments
                                    tempo = librosa.beat.tempo(y=y, sr=sr)
                                    file_info['bpm'] = round(float(tempo[0])) if tempo.size > 0 else None
                            except Exception as e:
                                logger.error(f"Error computing BPM for {full_path}: {e}", exc_info=True)
                                file_info['bpm'] = None
                    files_info.append(file_info)
                except Exception as e:
                    logger.error(f"Error scanning {full_path}: {e}")
                current_count += 1
                if current_count % 100 == 0:
                    self.progress.emit(current_count, total_files)
        self.finished.emit(files_info)

# -------------------------- File Table Model --------------------------
class FileTableModel(QtCore.QAbstractTableModel):
    """
    Custom model to hold file data.
    New Columns: File Path, Size, Modified Date, Duration, BPM, Key, Used, Tags, Sample Rate, Channels.
    """
    COLUMN_HEADERS = ["File Path", "Size", "Modified Date", "Duration", "BPM", "Key", "Used", "Tags", "Sample Rate", "Channels"]

    def __init__(self, files: Optional[List[Dict[str, Any]]] = None, size_unit: str = "KB", parent: Optional[QtCore.QObject] = None) -> None:
        """
        Initialize the FileTableModel.
        
        Args:
            files (Optional[List[Dict[str, Any]]]): List of file information dictionaries.
            size_unit (str): The size unit to display.
            parent (Optional[QtCore.QObject]): Parent object.
        """
        super().__init__(parent)
        self._files = files if files is not None else []
        self.size_unit = size_unit

    def rowCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        return len(self._files)

    def columnCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        return len(self.COLUMN_HEADERS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        file_info = self._files[index.row()]
        col = index.column()
        if role == QtCore.Qt.DisplayRole:
            if col == 0:
                return file_info['path']
            elif col == 1:
                return self.format_size(file_info['size'])
            elif col == 2:
                return file_info['mod_time'].strftime("%Y-%m-%d %H:%M:%S")
            elif col == 3:
                # Duration is stored as seconds; format for display.
                return format_duration(file_info.get('duration'))
            elif col == 4:
                return str(file_info.get('bpm', ""))
            elif col == 5:
                return file_info.get('key', "")
            elif col == 6:
                return ""  # Check state handled via CheckStateRole.
            elif col == 7:
                return file_info.get('tags', "")
            elif col == 8:
                return str(file_info.get('samplerate', ""))
            elif col == 9:
                return str(file_info.get('channels', ""))
        if role == QtCore.Qt.CheckStateRole and col == 6:
            return QtCore.Qt.Checked if file_info.get('used', False) else QtCore.Qt.Unchecked
        return None

    def headerData(self, section: int, orientation: QtCore.Qt.Orientation, role: int = QtCore.Qt.DisplayRole) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            if 0 <= section < len(self.COLUMN_HEADERS):
                return self.COLUMN_HEADERS[section]
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        """
        Modify flags to allow editing for Duration (3), BPM (4), Key (5), and Tags (7).
        """
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        base_flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        if index.column() == 6:
            # "Used" column: checkable and editable.
            return base_flags | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable
        elif index.column() in [3, 4, 5, 7]:
            # Enable in-place editing for Duration, BPM, Key, and Tags.
            return base_flags | QtCore.Qt.ItemIsEditable
        return base_flags


    def setData(self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.EditRole) -> bool:
        """
        Allow user edits for Duration, BPM, Key, and Tags.
        Duration must be entered as "mm:ss".
        BPM is expected to be a numeric value.
        Key is converted to uppercase.
        """
        if not index.isValid():
            return False
        file_info = self._files[index.row()]
        col = index.column()
        if role == QtCore.Qt.CheckStateRole and col == 6:
            file_info['used'] = (value == QtCore.Qt.Checked)
            self.dataChanged.emit(index, index, [role])
            return True
        if role == QtCore.Qt.EditRole:
            if col == 3:  # Duration column
                # Convert input "mm:ss" to seconds.
                new_duration = self._parse_duration(value)
                if new_duration is not None:
                    file_info['duration'] = new_duration
                else:
                    # Reject invalid duration formats.
                    return False
            elif col == 4:  # BPM column
                try:
                    file_info['bpm'] = int(value) if value.strip() else None
                except ValueError:
                    return False
            elif col == 5:  # Key column
                # Store key in uppercase for consistency.
                file_info['key'] = value.strip().upper() if value else ""
            elif col == 7:  # Tags column
                file_info['tags'] = value
            else:
                # Other columns are not editable.
                return False
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def _parse_duration(self, text: str) -> Optional[float]:
        """
        Helper function to parse a duration string formatted as "mm:ss" into total seconds.
        Returns None if the input is not valid.
        """
        try:
            parts = text.split(':')
            if len(parts) != 2:
                return None
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        except Exception:
            return None

    def format_size(self, size_in_bytes: Union[int, float]) -> str:
        """
        Format a size value into a string with the selected unit.
        """
        if self.size_unit == "KB":
            return f"{size_in_bytes / 1024:.2f} KB"
        elif self.size_unit == "MB":
            return f"{size_in_bytes / (1024 ** 2):.2f} MB"
        elif self.size_unit == "GB":
            return f"{size_in_bytes / (1024 ** 3):.2f} GB"
        else:
            return str(size_in_bytes)

    def updateData(self, files: List[Dict[str, Any]]) -> None:
        """
        Update the model's data.
        """
        self.beginResetModel()
        self._files = files
        self.endResetModel()

    def getFileAt(self, row: int) -> Optional[Dict[str, Any]]:
        """
        Return the file info dictionary at the specified row.
        """
        if 0 <= row < len(self._files):
            return self._files[row]
        return None

# -------------------------- Filter Proxy Model --------------------------
class FileFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Proxy model for filtering files by their path, tags, and optionally by "used" status.
    """
    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        """
        Initialize the FileFilterProxyModel.
        """
        super().__init__(parent)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setFilterKeyColumn(0)
        self.onlyUnused = False

    def setOnlyUnused(self, flag: bool) -> None:
        """
        Enable or disable filtering for only unused files.
        
        Args:
            flag (bool): If True, only show unused files.
        """
        self.onlyUnused = flag
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QtCore.QModelIndex) -> bool:
        """
        Determine whether a given row should be accepted by the filter.
        """
        if not super().filterAcceptsRow(source_row, source_parent):
            return False
        if self.onlyUnused:
            source_model = self.sourceModel()
            file_info = source_model.getFileAt(source_row)
            if file_info and file_info.get('used', False):
                return False
        return True

# -------------------------- Duplicate Manager Dialog --------------------------
class DuplicateManagerDialog(QtWidgets.QDialog):
    """
    Dialog to display and manage duplicate files with an added option for waveform preview.
    """
    def __init__(self, duplicate_groups: List[List[Dict[str, Any]]], size_unit: str = "KB", use_recycle_bin: bool = True, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """
        Initialize the DuplicateManagerDialog.
        
        Args:
            duplicate_groups (List[List[Dict[str, Any]]]): Groups of duplicate file info.
            size_unit (str): The size unit for display.
            use_recycle_bin (bool): Whether to use the recycle bin for deletions.
            parent (Optional[QtWidgets.QWidget]): Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Duplicate Files Manager")
        self.resize(900, 500)
        self.size_unit = size_unit
        self.use_recycle_bin = use_recycle_bin

        main_layout = QtWidgets.QVBoxLayout(self)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["File Path", "Size", "Modified Date", "MD5 Hash"])
        self.tree.setSortingEnabled(True)
        self.tree.header().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        main_layout.addWidget(self.tree)

        btn_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(btn_layout)

        self.btnSelectAll = QtWidgets.QPushButton("Select All")
        self.btnSelectAll.clicked.connect(self.selectAll)
        btn_layout.addWidget(self.btnSelectAll)

        self.btnDeselectAll = QtWidgets.QPushButton("Deselect All")
        self.btnDeselectAll.clicked.connect(self.deselectAll)
        btn_layout.addWidget(self.btnDeselectAll)

        self.btnDeleteSelected = QtWidgets.QPushButton("Delete Selected")
        self.btnDeleteSelected.clicked.connect(self.deleteSelected)
        btn_layout.addWidget(self.btnDeleteSelected)

        self.btnKeepOnlyFirst = QtWidgets.QPushButton("Keep Only First")
        self.btnKeepOnlyFirst.clicked.connect(self.keepOnlyFirst)
        btn_layout.addWidget(self.btnKeepOnlyFirst)

        self.btnOpenFolder = QtWidgets.QPushButton("Open Containing Folder")
        self.btnOpenFolder.clicked.connect(self.openContainingFolder)
        btn_layout.addWidget(self.btnOpenFolder)

        # New button for waveform preview of a duplicate file
        self.btnViewWaveform = QtWidgets.QPushButton("View Waveform")
        self.btnViewWaveform.clicked.connect(self.viewWaveform)
        btn_layout.addWidget(self.btnViewWaveform)

        self.btnClose = QtWidgets.QPushButton("Close")
        self.btnClose.clicked.connect(self.accept)
        btn_layout.addWidget(self.btnClose)

        self.populateTree(duplicate_groups)


    def populateTree(self, duplicate_groups: List[List[Dict[str, Any]]]) -> None:
        """
        Populate the tree widget with duplicate file groups.
        """
        self.tree.clear()
        for group_index, group in enumerate(duplicate_groups, start=1):
            parent_item = QtWidgets.QTreeWidgetItem(self.tree)
            parent_item.setText(0, f"Group {group_index} ({len(group)} files)")
            parent_item.setFlags(parent_item.flags() & ~QtCore.Qt.ItemIsSelectable)
            for info in group:
                child = QtWidgets.QTreeWidgetItem(parent_item)
                child.setText(0, info['path'])
                size_value = self.bytesToUnit(info['size'])
                child.setText(1, f"{size_value:.2f} {self.size_unit}")
                child.setText(2, info['mod_time'].strftime("%Y-%m-%d %H:%M:%S"))
                child.setText(3, info.get('hash', ''))
                child.setFlags(child.flags() | QtCore.Qt.ItemIsUserCheckable)
                child.setCheckState(0, QtCore.Qt.Unchecked)
        self.tree.expandAll()

    def selectAll(self) -> None:
        """
        Select all duplicate file entries.
        """
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Checked)

    def deselectAll(self) -> None:
        """
        Deselect all duplicate file entries.
        """
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Unchecked)

    def deleteSelected(self) -> None:
        """
        Delete the selected duplicate files.
        """
        items_to_delete = []
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == QtCore.Qt.Checked:
                    items_to_delete.append((parent, child))
        if not items_to_delete:
            QtWidgets.QMessageBox.information(self, "No Selection", "No files selected for deletion.")
            return

        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete {len(items_to_delete)} file(s)?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return

        errors = []
        for parent, child in items_to_delete:
            file_path = child.text(0)
            try:
                if self.use_recycle_bin:
                    send2trash(file_path)
                else:
                    os.remove(file_path)
            except Exception as e:
                errors.append(f"Error deleting {file_path}: {str(e)}")
            else:
                parent.removeChild(child)
        if errors:
            QtWidgets.QMessageBox.critical(self, "Deletion Errors", "\n".join(errors))
        else:
            QtWidgets.QMessageBox.information(self, "Deletion", "Selected files deleted successfully.")

        for i in reversed(range(root.childCount())):
            parent = root.child(i)
            if parent.childCount() == 0:
                root.removeChild(parent)

    def keepOnlyFirst(self) -> None:
        """
        Keep only the first file in each duplicate group.
        """
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(1, parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Checked)
        self.deleteSelected()

    def openContainingFolder(self) -> None:
        """
        Open the containing folder of the selected file.
        """
        selected_items = self.tree.selectedItems()
        file_path = None
        for item in selected_items:
            if item.parent() is not None:
                file_path = item.text(0)
                break
        if not file_path:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select a file entry first.")
            return
        open_file_location(file_path)
        
    def bytesToUnit(self, size_in_bytes: Union[int, float]) -> float:
        """
        Convert file size using the global bytes_to_unit utility.
        """
        return bytes_to_unit(size_in_bytes, self.size_unit)

    def viewWaveform(self) -> None:
        """
        Display the waveform preview for the selected duplicate file.
        """
        # Get selected file and open waveform preview if audio file
        selected_items = self.tree.selectedItems()
        file_path = None
        for item in selected_items:
            if item.parent() is not None:
                file_path = item.text(0)
                break
        if not file_path:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select an audio file entry first.")
            return
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            QtWidgets.QMessageBox.information(self, "Not Audio", "Selected file is not an audio file.")
            return
        if ENABLE_WAVEFORM_PREVIEW:
            dialog = WaveformDialog(file_path, parent=self)
            dialog.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "Feature Unavailable", "Waveform preview is not available (missing dependencies).")

# -------------------------- Waveform Preview Dialog --------------------------
class WaveformDialog(QtWidgets.QDialog):
    """
    Dialog to display a waveform preview of an audio file using matplotlib embedded in Qt.
    """
    def __init__(self, file_path: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """
        Initialize the WaveformDialog.
        
        Args:
            file_path (str): The path to the audio file.
            parent (Optional[QtWidgets.QWidget]): Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle(f"Waveform Preview: {os.path.basename(file_path)}")
        self.resize(800, 400)
        layout = QtWidgets.QVBoxLayout(self)
        self.file_path = file_path

        if ENABLE_WAVEFORM_PREVIEW:
            self.figure = plt.figure()
            self.canvas = FigureCanvas(self.figure)
            layout.addWidget(self.canvas)
            self.plot_waveform()
        else:
            label = QtWidgets.QLabel("Waveform preview is not available due to missing dependencies.")
            layout.addWidget(label)

    def plot_waveform(self) -> None:
        """
        Plot the waveform of the audio file.
        """
        try:
            y, sr = librosa.load(self.file_path, sr=None, mono=True)
            times = np.linspace(0, len(y)/sr, num=len(y))
            ax = self.figure.add_subplot(111)
            ax.clear()
            ax.plot(times, y)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            ax.set_title("Waveform")
            self.canvas.draw()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Could not load waveform: {e}")

# -------------------------- Recommendations Dialog --------------------------
class RecommendationsDialog(QtWidgets.QDialog):
    """
    Dialog to display smart sample recommendations based on similar BPM or tags.
    """
    def __init__(self, recommendations: List[Dict[str, Any]], parent: Optional[QtWidgets.QWidget] = None) -> None:
        """
        Initialize the RecommendationsDialog.
        
        Args:
            recommendations (List[Dict[str, Any]]): List of recommended file info.
            parent (Optional[QtWidgets.QWidget]): Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("Recommended Similar Samples")
        self.resize(800, 400)
        layout = QtWidgets.QVBoxLayout(self)

        self.tableView = QtWidgets.QTableView()
        self.model = FileTableModel(recommendations, size_unit="KB")
        self.tableView.setModel(self.model)
        self.tableView.setSortingEnabled(True)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.tableView)

        btn_close = QtWidgets.QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

# -------------------------- Main Window --------------------------
class MainWindow(QtWidgets.QMainWindow):
    """
    Main application window.
    """
    def __init__(self) -> None:
        """
        Initialize the MainWindow and set up the UI and settings.
        """
        super().__init__()
        self.setWindowTitle("Musicians Organizer")
        self.resize(1000, 700)

        self.all_files_info = []
        self.all_files_count = 0
        self.all_files_size = 0
        self.size_unit = "KB"
        self.search_text = ""
        self.last_folder = ""
        self.cubase_folder = ""  # For Direct Cubase Integration

        self.initUI()
        self.loadSettings()

        self.filterTimer = QtCore.QTimer(self)
        self.filterTimer.setSingleShot(True)
        self.filterTimer.timeout.connect(self.updateFilter)

        # New checkbox for "Show Only Unused Samples"
        self.chkOnlyUnused = QtWidgets.QCheckBox("Show Only Unused Samples")
        self.chkOnlyUnused.setChecked(False)
        self.chkOnlyUnused.stateChanged.connect(self.onOnlyUnusedChanged)

        # Initialize QMediaPlayer for audio preview.
        self.player = QMediaPlayer()

    def initUI(self) -> None:
        """
        Create a modern, dark-themed UI with two separate toolbars and a centered progress bar:
        1) File Management – for scanning, duplicates, deletion, Cubase folder, etc.
        2) Audio Tools – for preview, stop, waveform, auto-tag, recommendations, Cubase sending.
        
        """
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ------------------- First Toolbar: File Management -------------------
        self.fileToolBar = QtWidgets.QToolBar("File Management")
        self.fileToolBar.setObjectName("fileToolBar")  # For state saving
        self.fileToolBar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.fileToolBar)

        # Action: Select Folder
        actSelectFolder = QtWidgets.QAction("Select Folder", self)
        actSelectFolder.setToolTip("Select a folder to scan for music samples.")
        actSelectFolder.triggered.connect(self.selectFolder)
        self.fileToolBar.addAction(actSelectFolder)

        # Action: Find Duplicates
        actFindDuplicates = QtWidgets.QAction("Find Duplicates", self)
        actFindDuplicates.setToolTip("Find duplicate files based on size/hash.")
        actFindDuplicates.triggered.connect(self.findDuplicates)
        self.fileToolBar.addAction(actFindDuplicates)

        # Action: Open Folder
        actOpenFolder = QtWidgets.QAction("Open Folder", self)
        actOpenFolder.setToolTip("Open the folder of the selected file.")
        actOpenFolder.triggered.connect(lambda: open_file_location(self.getSelectedFilePath()))
        self.fileToolBar.addAction(actOpenFolder)

        # Action: Delete Selected
        actDeleteSelected = QtWidgets.QAction("Delete Selected", self)
        actDeleteSelected.setToolTip("Delete selected file(s).")
        actDeleteSelected.triggered.connect(self.deleteSelected)
        self.fileToolBar.addAction(actDeleteSelected)

        # Action: Set Cubase Folder
        actSetCubase = QtWidgets.QAction("Set Cubase Folder", self)
        actSetCubase.setToolTip("Set or change the Cubase integration folder.")
        actSetCubase.triggered.connect(self.setCubaseFolder)
        self.fileToolBar.addAction(actSetCubase)

        # Left expanding spacer to push the progress bar to the center
        leftExpSpacer = QtWidgets.QWidget(self)
        leftExpSpacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.fileToolBar.addWidget(leftExpSpacer)

        # Progress Bar (centered by having leftExpSpacer + rightExpSpacer)
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setValue(0)
        self.progressBar.setFixedWidth(200)  # Adjust width as desired
        progressAction = QtWidgets.QWidgetAction(self.fileToolBar)
        progressAction.setDefaultWidget(self.progressBar)
        self.fileToolBar.addAction(progressAction)

        # Right expanding spacer
        rightExpSpacer = QtWidgets.QWidget(self)
        rightExpSpacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.fileToolBar.addWidget(rightExpSpacer)

        # ------------------- Second Toolbar: Audio Tools -------------------
        self.audioToolBar = QtWidgets.QToolBar("Audio Tools")
        self.audioToolBar.setObjectName("audioToolBar")  # For state saving
        self.audioToolBar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.audioToolBar)

        # Action: Preview
        actPreview = QtWidgets.QAction("Preview", self)
        actPreview.setToolTip("Preview the selected audio file.")
        actPreview.triggered.connect(self.previewSelected)
        self.audioToolBar.addAction(actPreview)

        # Action: Stop Preview
        actStopPreview = QtWidgets.QAction("Stop", self)
        actStopPreview.setToolTip("Stop the audio preview.")
        actStopPreview.triggered.connect(self.stopPreview)
        self.audioToolBar.addAction(actStopPreview)

        # Action: Waveform
        actWaveform = QtWidgets.QAction("Waveform", self)
        actWaveform.setToolTip("View the waveform of the selected audio file.")
        actWaveform.triggered.connect(self.waveformPreview)
        self.audioToolBar.addAction(actWaveform)

        # Optional: small spacer for aesthetics
        spacer2 = QtWidgets.QWidget(self)
        spacer2.setFixedWidth(15)
        self.audioToolBar.addWidget(spacer2)

        # Action: Auto Tag Files
        actAutoTag = QtWidgets.QAction("Auto Tag", self)
        actAutoTag.setToolTip("Automatically tag files (BPM & Key detection).")
        actAutoTag.triggered.connect(self.autoTagFiles)
        self.audioToolBar.addAction(actAutoTag)

        # Action: Recommend Samples
        actRecommend = QtWidgets.QAction("Recommend", self)
        actRecommend.setToolTip("Recommend similar samples based on BPM or tags.")
        actRecommend.triggered.connect(self.recommendSimilarSamples)
        self.audioToolBar.addAction(actRecommend)

        # Action: Send to Cubase
        actSendToCubase = QtWidgets.QAction("Send to Cubase", self)
        actSendToCubase.setToolTip("Send selected file(s) to the configured Cubase folder.")
        actSendToCubase.triggered.connect(self.sendToCubase)
        self.audioToolBar.addAction(actSendToCubase)

        # ------------------- Main Splitter -------------------
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        # Left Panel: Filter and options
        left_panel = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(10)

        lblFilter = QtWidgets.QLabel("Filter by Name:")
        self.txtFilter = QtWidgets.QLineEdit()
        self.txtFilter.setPlaceholderText("Type to filter files...")
        self.txtFilter.textChanged.connect(self.onFilterTextChanged)
        left_layout.addWidget(lblFilter)
        left_layout.addWidget(self.txtFilter)

        # BPM Detection: moved to left panel
        self.chkBPM = QtWidgets.QCheckBox("BPM Detection")
        self.chkBPM.setChecked(False)
        left_layout.addWidget(self.chkBPM)

        self.chkOnlyUnused = QtWidgets.QCheckBox("Show Only Unused Samples")
        self.chkOnlyUnused.setChecked(False)
        self.chkOnlyUnused.stateChanged.connect(self.onOnlyUnusedChanged)
        left_layout.addWidget(self.chkOnlyUnused)

        sizeUnitLayout = QtWidgets.QHBoxLayout()
        lblSizeUnit = QtWidgets.QLabel("Size Unit:")
        self.comboSizeUnit = QtWidgets.QComboBox()
        self.comboSizeUnit.addItems(["KB", "MB", "GB"])
        self.comboSizeUnit.currentIndexChanged.connect(self.onSizeUnitChanged)
        sizeUnitLayout.addWidget(lblSizeUnit)
        sizeUnitLayout.addWidget(self.comboSizeUnit)
        left_layout.addLayout(sizeUnitLayout)

        self.chkRecycleBin = QtWidgets.QCheckBox("Use Recycle Bin")
        self.chkRecycleBin.setChecked(True)
        left_layout.addWidget(self.chkRecycleBin)

        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # Right Panel: Table and summary label
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(5)

        self.model = FileTableModel([], self.size_unit)
        self.proxyModel = FileFilterProxyModel()
        self.proxyModel.setSourceModel(self.model)

        self.tableView = QtWidgets.QTableView()
        self.tableView.setModel(self.proxyModel)
        self.tableView.setSortingEnabled(True)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        right_layout.addWidget(self.tableView)

        self.labelSummary = QtWidgets.QLabel("Scanned 0 files. Total size: 0 KB.")
        right_layout.addWidget(self.labelSummary)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        main_layout.addWidget(splitter)

        # ------------------- Status Bar -------------------
        self.setStatusBar(QtWidgets.QStatusBar())

        # ------------------- Dark Theme -------------------
        self.applyDarkThemeStylesheet()

        # ------------------- Help Menu -------------------
        menuBar = self.menuBar()
        helpMenu = menuBar.addMenu("Help")
        helpAction = QtWidgets.QAction("Usage Help", self)
        helpAction.triggered.connect(self.showHelpDialog)
        helpMenu.addAction(helpAction)



    def applyDarkThemeStylesheet(self) -> None:
        """
        Apply a modern, dark theme with minimal wasted space.
        Colors are easy on the eyes with contrasting highlights.
        """
        self.setStyleSheet("""
            QMainWindow {
                background-color: #282c34;
            }
            QToolBar {
                background-color: #21252b;
                spacing: 6px;
            }
            QToolBar QToolButton {
                background-color: #3a3f4b;
                color: #abb2bf;
                border: 1px solid #3a3f4b;
                border-radius: 4px;
                padding: 4px 10px;
                margin: 3px;
            }
            QToolBar QToolButton:hover {
                background-color: #4b5263;
            }
            /* Labels, checkboxes, combos, etc. */
            QLabel, QCheckBox, QRadioButton {
                color: #abb2bf;
                font-size: 13px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QLineEdit {
                background-color: #3a3f4b;
                border: 1px solid #4b5263;
                color: #abb2bf;
                border-radius: 4px;
                padding: 4px;
            }
            QComboBox {
                background-color: #3a3f4b;
                border: 1px solid #4b5263;
                color: #abb2bf;
                border-radius: 4px;
                padding: 2px;
            }
            QTableView {
                background-color: #3a3f4b;
                alternate-background-color: #333842;
                gridline-color: #4b5263;
                color: #ffffff;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #21252b;
                color: #61afef;
                border: 1px solid #3a3f4b;
                padding: 4px;
            }
            QProgressBar {
                background-color: #3a3f4b;
                border: 1px solid #4b5263;
                text-align: center;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #98c379;
            }
            QStatusBar {
                background-color: #21252b;
                border-top: 1px solid #3a3f4b;
            }
            QMenuBar {
                background-color: #21252b;
                color: #abb2bf;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 12px;
            }
            QMenuBar::item:selected {
                background-color: #61afef;
            }
            QMenu {
                background-color: #21252b;
                border: 1px solid #3a3f4b;
            }
            QMenu::item {
                padding: 4px 20px;
                color: #abb2bf;
            }
            QMenu::item:selected {
                background-color: #61afef;
            }
        """)

    def showHelpDialog(self) -> None:
        """
        Display a help dialog with usage instructions.
        """
        help_text = (
            "Musicians Organizer (Dark Theme)\n\n"
            "1. Select Folder: Choose a directory with music samples.\n"
            "2. Filter: Type in the left panel to filter files by name.\n"
            "3. Edit Metadata: Double-click Duration, BPM, Key, or Tags in the table.\n"
            "4. Duplicates: Use the toolbar to find duplicate files.\n"
            "5. Preview Audio: Use the toolbar to preview or stop preview.\n"
            "6. Waveform: View waveform for audio files.\n"
            "7. Delete Selected: Click 'Delete Selected' on the toolbar.\n"
            "8. Progress: Watch the progress bar in the status bar.\n"
        )
        QtWidgets.QMessageBox.information(self, "Usage Help", help_text)


    def getSelectedFilePath(self):
        """Utility to return the path of the first selected file."""
        selection = self.tableView.selectionModel().selectedRows()
        if selection:
            index = selection[0]
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            if file_info:
                return file_info['path']
        return None

    # -------------------------- Settings Persistence --------------------------
    def loadSettings(self) -> None:
        """
        Load persisted user settings.
        """
        settings = QtCore.QSettings("YourCompany", "MusiciansOrganizer")
        self.restoreGeometry(settings.value("windowGeometry", b""))
        self.restoreState(settings.value("windowState", b""))
        self.last_folder = settings.value("lastFolder", "")
        self.size_unit = settings.value("sizeUnit", "KB")
        self.comboSizeUnit.setCurrentText(self.size_unit)
        recycle_bin = settings.value("useRecycleBin", "true")
        self.chkRecycleBin.setChecked(recycle_bin.lower() == "true")
        self.cubase_folder = settings.value("cubaseFolder", "")

    def saveSettings(self) -> None:
        """
        Save current user settings.
        """
        settings = QtCore.QSettings("YourCompany", "MusiciansOrganizer")
        settings.setValue("windowGeometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("lastFolder", self.last_folder)
        settings.setValue("sizeUnit", self.size_unit)
        settings.setValue("useRecycleBin", "true" if self.chkRecycleBin.isChecked() else "false")
        settings.setValue("cubaseFolder", self.cubase_folder)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """
        Handle the close event by saving settings.
        """
        self.saveSettings()
        event.accept()

    # -------------------------- Scanning Methods --------------------------
    def selectFolder(self) -> None:
        """
        Open a dialog to select a folder and initiate scanning.
        """
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory", self.last_folder)
        if folder:
            self.last_folder = folder
            self.scanFiles(folder)

    def scanFiles(self, folder: str) -> None:
        """
        Start scanning the selected folder for files.
        
        Args:
            folder (str): The folder to scan.
        """
        self.labelSummary.setText(f"Scanning folder: {folder}")
        self.progressBar.setValue(0)
        self.all_files_info = []
        self.all_files_count = 0
        self.all_files_size = 0
        self.search_text = self.txtFilter.text().strip()

        # Retrieve the BPM detection flag from the checkbox:
        bpm_detection_enabled = self.chkBPM.isChecked()
        self.scanner = FileScanner(folder, bpm_detection=bpm_detection_enabled)
        self.scanner.progress.connect(self.updateProgressBar)
        self.scanner.finished.connect(self.onScanFinished)
        self.scanner.start()

    def updateProgressBar(self, current: int, total: int) -> None:
        """
        Update the progress bar during scanning.
        
        Args:
            current (int): Current file count processed.
            total (int): Total files to process.
        """
        if total == 0:
            self.progressBar.setValue(0)
            return
        percent = int((current / total) * 100)
        self.progressBar.setValue(percent)

    def updateFilter(self) -> None:
        """
        Update the file filter based on user input.
       
        Called by the filter timer after debouncing; updates the proxy model filter.
        """
        filter_text = self.txtFilter.text().strip()
        self.proxyModel.setFilterFixedString(filter_text)
        self.updateSummary()

    def onOnlyUnusedChanged(self, state: int) -> None:
        """
        Handle the change event for filtering only unused files.
        
        Args:
            state (int): The new state of the checkbox.
        """
        self.proxyModel.setOnlyUnused(state == QtCore.Qt.Checked)
        self.updateSummary()

    def onScanFinished(self, files_info: List[Dict[str, Any]]) -> None:
        """
        Handle completion of the scanning process.
        
        Args:
            files_info (List[Dict[str, Any]]): List of file metadata dictionaries.
        """
        self.all_files_info = files_info
        self.all_files_count = len(files_info)
        self.all_files_size = sum(item['size'] for item in files_info)
        self.model.updateData(files_info)
        self.updateSummary()
        self.progressBar.setValue(100)

    # -------------------------- Filtering Methods --------------------------
    def onFilterTextChanged(self, text: str) -> None:
        """
        Update filtering when the text in the filter field changes.
        
        Args:
            text (str): The new filter text.
        """
        self.filterTimer.start(300)  # 300ms debounce
        self.proxyModel.setFilterFixedString(text)

    def onSizeUnitChanged(self, index: int) -> None:
        """
        Update the size unit for display.
        
        Args:
            index (int): The index of the selected unit.
        """
        self.size_unit = self.comboSizeUnit.currentText()
        self.model.size_unit = self.size_unit
        self.model.layoutChanged.emit()
        self.updateSummary()

    def updateSummary(self) -> None:
        """
        Update the summary label with current scan statistics.
        """
        summary_text = (f"Scanned {self.all_files_count} files. "
                        f"Total Size: {self.bytesToUnit(self.all_files_size):.2f} {self.size_unit}")
        self.labelSummary.setText(summary_text)

    def bytesToUnit(self, size_in_bytes: Union[int, float]) -> float:
        """
        Convert bytes to the selected unit using the helper function.
        
        Args:
            size_in_bytes (int or float): The size in bytes.
        
        Returns:
            float: The converted size.
        """
        return bytes_to_unit(size_in_bytes, self.size_unit)

    # -------------------------- Deletion Methods --------------------------
    def deleteSelected(self) -> None:
        """
        Delete the files currently selected in the table.
        """
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select file(s) to delete.")
            return
        selected_file_infos = []
        for index in reversed(selection):
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            if file_info:
                selected_file_infos.append(file_info)
        if not selected_file_infos:
            return
        self.attemptDeleteMultiple(selected_file_infos)

    def attemptDeleteMultiple(self, file_infos: List[Dict[str, Any]]) -> None:
        """
        Attempt to delete multiple files and update the model accordingly.
        
        Args:
            file_infos (List[Dict[str, Any]]): The files to delete.
        """
        file_paths = [info['path'] for info in file_infos]
        paths_display = "\n".join(file_paths)
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete the following {len(file_paths)} file(s)?\n\n{paths_display}",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        errors = []
        for info in file_infos:
            file_path = info['path']
            try:
                if self.chkRecycleBin.isChecked():
                    send2trash(file_path)
                else:
                    os.remove(file_path)
                self.all_files_info = [f for f in self.all_files_info if f['path'] != file_path]
            except Exception as e:
                errors.append(f"Error deleting {file_path}: {str(e)}")
        self.all_files_count = len(self.all_files_info)
        self.all_files_size = sum(item['size'] for item in self.all_files_info)
        self.model.updateData(self.all_files_info)
        self.updateSummary()
        if errors:
            QtWidgets.QMessageBox.critical(self, "Deletion Errors", "\n".join(errors))
        else:
            QtWidgets.QMessageBox.information(self, "Deleted", "Selected files deleted successfully.")

    # -------------------------- Duplicate Detection Methods --------------------------
    def findDuplicates(self) -> None:
        """
        Initiate the process to find duplicate files.
        """
        if not self.all_files_info:
            QtWidgets.QMessageBox.information(self, "No Files", "Please scan a folder first.")
            return
        # Correctly reference the nested DuplicateFinder class.
        self.duplicateFinder = MainWindow.DuplicateFinder(self.all_files_info)
        self.duplicateFinder.finished.connect(self.onDuplicatesFound)
        self.duplicateFinder.start()

    def onDuplicatesFound(self, duplicate_groups: List[List[Dict[str, Any]]]) -> None:
        """
        Handle the results of the duplicate detection process.
        
        Args:
            duplicate_groups (List[List[Dict[str, Any]]]): Groups of duplicate files.
        """
        if not duplicate_groups:
            QtWidgets.QMessageBox.information(self, "No Duplicates", "No duplicate files were found.")
        else:
            dialog = DuplicateManagerDialog(
                duplicate_groups,
                size_unit=self.size_unit,
                use_recycle_bin=self.chkRecycleBin.isChecked(),
                parent=self
            )
            dialog.exec_()

    class DuplicateFinder(QtCore.QThread):
        """
        Thread to find duplicate files by grouping by size and comparing MD5 hashes.
        Emits a list of duplicate groups.
        """
        finished = QtCore.pyqtSignal(list)

        def __init__(self, files_info: List[Dict[str, Any]], parent: Optional[QtCore.QObject] = None) -> None:
            """
            Initialize the DuplicateFinder.
            
            Args:
                files_info (List[Dict[str, Any]]): List of file metadata dictionaries.
                parent (Optional[QtCore.QObject]): Parent object.
            """
            super().__init__(parent)
            self.files_info = files_info

        def run(self) -> None:
            """
            Execute the duplicate detection algorithm.
            """
            size_dict = {}
            for info in self.files_info:
                size = info['size']
                size_dict.setdefault(size, []).append(info)
            duplicate_groups = []
            for size, files in size_dict.items():
                if len(files) < 2:
                    continue
                hash_dict = {}
                for info in files:
                    file_hash = compute_hash(info['path'])
                    if file_hash is None:
                        continue
                    info['hash'] = file_hash
                    hash_dict.setdefault(file_hash, []).append(info)
                for file_hash, group in hash_dict.items():
                    if len(group) > 1:
                        duplicate_groups.append(group)
            self.finished.emit(duplicate_groups)

    # -------------------------- Audio Preview --------------------------
    def previewSelected(self) -> None:
        """
        Preview the selected file using the media player.
        """
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select a file to preview.")
            return
        index = selection[0]
        source_index = self.proxyModel.mapToSource(index)
        file_info = self.model.getFileAt(source_index.row())
        if not file_info:
            return
        file_path = file_info['path']
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            QtWidgets.QMessageBox.information(self, "Not Audio", "Selected file is not an audio file.")
            return
        url = QUrl.fromLocalFile(file_path)
        media = QMediaContent(url)
        self.player.setMedia(media)
        self.player.setVolume(50)
        self.player.play()

    # New function: Stop Audio Preview.
    def stopPreview(self) -> None:
        """
        Stop the media preview.
        """
        self.player.stop()

    # New function: Waveform preview for selected file.
    def waveformPreview(self) -> None:
        """
        Launch the waveform preview for the selected file.
        """
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select a file for waveform preview.")
            return
        index = selection[0]
        source_index = self.proxyModel.mapToSource(index)
        file_info = self.model.getFileAt(source_index.row())
        if not file_info:
            return
        file_path = file_info['path']
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            QtWidgets.QMessageBox.information(self, "Not Audio", "Selected file is not an audio file.")
            return
        if ENABLE_WAVEFORM_PREVIEW:
            dialog = WaveformDialog(file_path, parent=self)
            dialog.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "Feature Unavailable", "Waveform preview is not available (missing dependencies).")

    # New function: Direct Cubase Integration - Send to Cubase.
    def sendToCubase(self) -> None:
        """
        Send the selected files to the configured Cubase folder.
        """
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select file(s) to send to Cubase.")
            return
        if not self.cubase_folder or not os.path.isdir(self.cubase_folder):
            QtWidgets.QMessageBox.information(self, "Cubase Folder Not Set", "Please set a valid Cubase folder using 'Set Cubase Folder'.")
            return
        for index in selection:
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            if file_info:
                dest_path = os.path.join(self.cubase_folder, os.path.basename(file_info['path']))
                try:
                    shutil.copy2(file_info['path'], dest_path)
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", f"Could not send {file_info['path']} to Cubase: {e}")
                    return
        QtWidgets.QMessageBox.information(self, "Sent", "Selected file(s) have been sent to Cubase.")

    # New function: Smart Sample Recommendations.
    def recommendSimilarSamples(self) -> None:
        """
        Recommend similar samples based on BPM and tags.
        """
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select a sample to base recommendations on.")
            return
        index = selection[0]
        source_index = self.proxyModel.mapToSource(index)
        selected_file = self.model.getFileAt(source_index.row())
        if not selected_file:
            return
        recommendations = []
        tolerance = 5  # BPM tolerance
        selected_bpm = selected_file.get('bpm')
        # Process tags: trim whitespace and convert to uppercase for consistency.
        selected_tags = set(tag.strip().upper() for tag in selected_file.get('tags', "").split(",") if tag.strip())
        for info in self.all_files_info:
            if info['path'] == selected_file['path']:
                continue
            similar = False
            if selected_bpm and info.get('bpm'):
                if abs(selected_bpm - info['bpm']) <= tolerance:
                    similar = True
            if not similar and selected_tags:
                file_tags = set(tag.strip().upper() for tag in info.get('tags', "").split(",") if tag.strip())
                if selected_tags.intersection(file_tags):
                    similar = True
            if similar:
                recommendations.append(info)
        if recommendations:
            dialog = RecommendationsDialog(recommendations, parent=self)
            dialog.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "No Recommendations", "No similar samples found.")

    # New function: Auto Tag Files based on BPM.
    def autoTagFiles(self) -> None:
        """
        Automatically tag files based on BPM and detect musical key from filename.
        """
        # BPM-based tagging (existing logic)
        for info in self.all_files_info:
            bpm = info.get('bpm')
            if bpm:
                if bpm > 120:
                    tag = "FAST"
                elif bpm < 90:
                    tag = "SLOW"
                else:
                    tag = "MEDIUM"
                # Merge with existing tags
                current_tags = info.get('tags', "")
                tags_set = set(tag_str.strip().upper() for tag_str in current_tags.split(",") if tag_str.strip())
                tags_set.add(tag.upper())
                info['tags'] = ", ".join(sorted(tags_set))

        # New: Key detection via regex
        for info in self.all_files_info:
            # If user hasn't already set the key or it's "N/A", try auto-detect:
            if not info.get('key') or info['key'].upper() == "N/A":
                detected_key = detect_key_from_filename(info['path'])
                if detected_key:
                    info['key'] = detected_key

        # Finally, refresh the table to reflect updated info
        self.model.updateData(self.all_files_info)
        QtWidgets.QMessageBox.information(self, "Auto Tagging", "Files have been auto-tagged (BPM + Key).")

    # New function: Set Cubase Folder.
    def setCubaseFolder(self) -> None:
        """
        Open a dialog to set the Cubase folder.
        """
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Cubase Folder", self.cubase_folder or self.last_folder)
        if folder:
            self.cubase_folder = folder
            QtWidgets.QMessageBox.information(self, "Cubase Folder Set", f"Cubase folder set to: {folder}")

# -------------------------- Main --------------------------
def main() -> None:
    """
    Entry point of the application.
    """
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()