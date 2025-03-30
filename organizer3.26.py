#!/usr/bin/env python3
"""
PC Organizer
A production-ready application to scan directories, display file details,
and help decide what can be removed.

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
"""

import sys
import os
import datetime
import hashlib
import subprocess
import platform
import time

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl
from send2trash import send2trash

# Attempt to import tinytag for audio metadata extraction.
try:
    from tinytag import TinyTag
except ImportError:
    print("Warning: tinytag module not found. Audio metadata extraction will be disabled.")
    TinyTag = None

# Constants for hash computation
MAX_HASH_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
HASH_TIMEOUT_SECONDS = 5  # 5 seconds

# Audio file extensions for metadata extraction and preview
AUDIO_EXTENSIONS = {".wav", ".aiff", ".flac", ".mp3", ".ogg"}


def format_duration(seconds):
    """Format a duration in seconds as mm:ss."""
    if seconds is None:
        return ""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def open_file_location(file_path):
    """Open the folder containing the given file."""
    folder = os.path.dirname(file_path)
    try:
        if platform.system() == "Windows":
            os.startfile(folder)
        elif platform.system() == "Darwin":
            subprocess.call(["open", folder])
        else:
            subprocess.call(["xdg-open", folder])
    except Exception as e:
        QtWidgets.QMessageBox.critical(None, "Error", f"Could not open folder:\n{str(e)}")


def compute_hash(file_path, block_size=65536, timeout_seconds=HASH_TIMEOUT_SECONDS,
                 max_hash_size=MAX_HASH_FILE_SIZE):
    """
    Computes the MD5 hash of a file.
    Skips files exceeding max_hash_size or if computation exceeds timeout.
    """
    try:
        file_size = os.path.getsize(file_path)
        if file_size > max_hash_size:
            print(f"Skipping hash for {file_path}: size {file_size} exceeds limit.")
            return None
        hash_md5 = hashlib.md5()
        start_time = time.monotonic()
        with open(file_path, "rb") as f:
            while True:
                if time.monotonic() - start_time > timeout_seconds:
                    print(f"Hash for {file_path} timed out.")
                    return None
                chunk = f.read(block_size)
                if not chunk:
                    break
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"Error computing hash for {file_path}: {e}")
        return None


class DuplicateFinder(QtCore.QThread):
    """
    Thread to find duplicate files by grouping by size and comparing MD5 hashes.
    Emits a list of duplicate groups.
    """
    finished = QtCore.pyqtSignal(list)

    def __init__(self, files_info, parent=None):
        super().__init__(parent)
        self.files_info = files_info

    def run(self):
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


class FileScanner(QtCore.QThread):
    """
    Thread to scan a directory recursively and extract file metadata.
    Emits progress and a list of file info dictionaries.
    """
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)

    def __init__(self, root_path, parent=None):
        super().__init__(parent)
        self.root_path = root_path

    def run(self):
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
                        'used': False       # Mark if the file has been used
                    }
                    ext = os.path.splitext(full_path)[1].lower()
                    if ext in AUDIO_EXTENSIONS and TinyTag is not None:
                        try:
                            tag = TinyTag.get(full_path)
                            file_info['duration'] = tag.duration
                            file_info['samplerate'] = tag.samplerate
                            file_info['channels'] = tag.channels
                        except Exception as e:
                            print(f"Error reading audio metadata for {full_path}: {e}")
                    files_info.append(file_info)
                except Exception as e:
                    print(f"Error scanning {full_path}: {e}")
                current_count += 1
                if current_count % 100 == 0:
                    self.progress.emit(current_count, total_files)
        self.finished.emit(files_info)


# ------------------ Model/View Components ------------------ #

class FileTableModel(QtCore.QAbstractTableModel):
    """
    Custom model to hold file data.
    Columns: File Path, Size, Modified Date, Duration, Used, Sample Rate, Channels.
    """
    COLUMN_HEADERS = ["File Path", "Size", "Modified Date", "Duration", "Used", "Sample Rate", "Channels"]

    def __init__(self, files=None, size_unit="KB", parent=None):
        super().__init__(parent)
        self._files = files if files is not None else []
        self.size_unit = size_unit

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._files)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return len(self.COLUMN_HEADERS)

    def data(self, index, role=QtCore.Qt.DisplayRole):
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
                return format_duration(file_info.get('duration'))
            elif col == 4:
                return ""  # Checkbox handled in CheckStateRole
            elif col == 5:
                return str(file_info.get('samplerate', ""))
            elif col == 6:
                return str(file_info.get('channels', ""))
        if role == QtCore.Qt.CheckStateRole and col == 4:
            return QtCore.Qt.Checked if file_info.get('used', False) else QtCore.Qt.Unchecked
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            if 0 <= section < len(self.COLUMN_HEADERS):
                return self.COLUMN_HEADERS[section]
        return None

    def flags(self, index):
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        base_flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        if index.column() == 4:
            return base_flags | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable
        return base_flags

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if not index.isValid():
            return False
        if index.column() == 4 and role == QtCore.Qt.CheckStateRole:
            self._files[index.row()]['used'] = (value == QtCore.Qt.Checked)
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def format_size(self, size_in_bytes):
        if self.size_unit == "KB":
            return f"{size_in_bytes / 1024:.2f} KB"
        elif self.size_unit == "MB":
            return f"{size_in_bytes / (1024 ** 2):.2f} MB"
        elif self.size_unit == "GB":
            return f"{size_in_bytes / (1024 ** 3):.2f} GB"
        else:
            return str(size_in_bytes)

    def updateData(self, files):
        self.beginResetModel()
        self._files = files
        self.endResetModel()

        

    def getFileAt(self, row):
        if 0 <= row < len(self._files):
            return self._files[row]
        return None


class FileFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Proxy model for filtering files by their path and optionally by "used" status.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setFilterKeyColumn(0)
        self.onlyUnused = False

    def setOnlyUnused(self, flag):
        self.onlyUnused = flag
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not super().filterAcceptsRow(source_row, source_parent):
            return False
        if self.onlyUnused:
            source_model = self.sourceModel()
            file_info = source_model.getFileAt(source_row)
            if file_info and file_info.get('used', False):
                return False
        return True

# ------------------ Duplicate Manager Dialog (unchanged) ------------------ #

class DuplicateManagerDialog(QtWidgets.QDialog):
    """
    Dialog to display and manage duplicate files.
    (Remains unchanged from the previous version.)
    """
    def __init__(self, duplicate_groups, size_unit="KB", use_recycle_bin=True, parent=None):
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

        self.btnClose = QtWidgets.QPushButton("Close")
        self.btnClose.clicked.connect(self.accept)
        btn_layout.addWidget(self.btnClose)

        self.populateTree(duplicate_groups)

    def bytesToUnit(self, size_in_bytes):
        if self.size_unit == "KB":
            return size_in_bytes / 1024
        elif self.size_unit == "MB":
            return size_in_bytes / (1024 ** 2)
        elif self.size_unit == "GB":
            return size_in_bytes / (1024 ** 3)
        else:
            return size_in_bytes

    def populateTree(self, duplicate_groups):
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

    def selectAll(self):
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Checked)

    def deselectAll(self):
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Unchecked)

    def deleteSelected(self):
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

    def keepOnlyFirst(self):
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(1, parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Checked)
        self.deleteSelected()

    def openContainingFolder(self):
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

# ------------------ Main Window with Model/View and Extended Features ------------------ #

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Musicians Organizer")
        self.resize(900, 600)

        self.all_files_info = []
        self.all_files_count = 0
        self.all_files_size = 0
        self.size_unit = "KB"
        self.search_text = ""
        self.last_folder = ""

        self.initUI()
        self.loadSettings()

        self.filterTimer = QtCore.QTimer(self)
        self.filterTimer.setSingleShot(True)
        self.filterTimer.timeout.connect(self.updateFilter)

        # New checkbox for "Show Only Unused Samples"
        self.chkOnlyUnused = QtWidgets.QCheckBox("Show Only Unused Samples")
        self.chkOnlyUnused.setChecked(False)
        self.chkOnlyUnused.stateChanged.connect(self.onOnlyUnusedChanged)
        self.filterLayout.addWidget(self.chkOnlyUnused)

        # Initialize QMediaPlayer for audio preview.
        self.player = QMediaPlayer()

    def initUI(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        # Top controls layout
        top_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(top_layout)

        self.btnSelect = QtWidgets.QPushButton("Select Folder to Scan")
        self.btnSelect.clicked.connect(self.selectFolder)
        top_layout.addWidget(self.btnSelect)

        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setValue(0)
        self.progressBar.setTextVisible(True)
        top_layout.addWidget(self.progressBar)

        self.btnFindDuplicates = QtWidgets.QPushButton("Find Duplicate Files")
        self.btnFindDuplicates.clicked.connect(self.findDuplicates)
        top_layout.addWidget(self.btnFindDuplicates)

        self.labelSummary = QtWidgets.QLabel("Summary: No folder scanned yet.")
        main_layout.addWidget(self.labelSummary)

        # Filter layout
        self.filterLayout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(self.filterLayout)

        lblFilter = QtWidgets.QLabel("Filter by Name:")
        self.filterLayout.addWidget(lblFilter)

        self.txtFilter = QtWidgets.QLineEdit()
        self.txtFilter.setPlaceholderText("Type to filter files...")
        self.txtFilter.textChanged.connect(self.onFilterTextChanged)
        self.filterLayout.addWidget(self.txtFilter)

        lblSizeUnit = QtWidgets.QLabel("Size Unit:")
        self.filterLayout.addWidget(lblSizeUnit)

        self.comboSizeUnit = QtWidgets.QComboBox()
        self.comboSizeUnit.addItems(["KB", "MB", "GB"])
        self.comboSizeUnit.currentIndexChanged.connect(self.onSizeUnitChanged)
        self.filterLayout.addWidget(self.comboSizeUnit)

        self.chkRecycleBin = QtWidgets.QCheckBox("Use Recycle Bin")
        self.chkRecycleBin.setChecked(True)
        self.filterLayout.addWidget(self.chkRecycleBin)

        # Create model and proxy model
        self.model = FileTableModel([], self.size_unit)
        self.proxyModel = FileFilterProxyModel()
        self.proxyModel.setSourceModel(self.model)

        # Create QTableView
        self.tableView = QtWidgets.QTableView()
        self.tableView.setModel(self.proxyModel)
        self.tableView.setSortingEnabled(True)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tableView.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Interactive)
        main_layout.addWidget(self.tableView)

        # Buttons layout for deletion and preview
        btn_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(btn_layout)

        self.btnDelete = QtWidgets.QPushButton("Delete Selected File(s)")
        self.btnDelete.clicked.connect(self.deleteSelected)
        btn_layout.addWidget(self.btnDelete)

        self.btnPreview = QtWidgets.QPushButton("Preview Selected File")
        self.btnPreview.clicked.connect(self.previewSelected)
        btn_layout.addWidget(self.btnPreview)

    # -------------------------- Settings Persistence --------------------------
    def loadSettings(self):
        settings = QtCore.QSettings("YourCompany", "PCOrganizer")
        self.restoreGeometry(settings.value("windowGeometry", b""))
        self.restoreState(settings.value("windowState", b""))
        self.last_folder = settings.value("lastFolder", "")
        self.size_unit = settings.value("sizeUnit", "KB")
        self.comboSizeUnit.setCurrentText(self.size_unit)
        recycle_bin = settings.value("useRecycleBin", "true")
        self.chkRecycleBin.setChecked(recycle_bin.lower() == "true")

    def saveSettings(self):
        settings = QtCore.QSettings("YourCompany", "PCOrganizer")
        settings.setValue("windowGeometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("lastFolder", self.last_folder)
        settings.setValue("sizeUnit", self.size_unit)
        settings.setValue("useRecycleBin", "true" if self.chkRecycleBin.isChecked() else "false")

    def closeEvent(self, event):
        self.saveSettings()
        event.accept()

    # -------------------------- Scanning Methods --------------------------
    def selectFolder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory", self.last_folder)
        if folder:
            self.last_folder = folder
            self.scanFiles(folder)

    def scanFiles(self, folder):
        self.labelSummary.setText(f"Scanning folder: {folder}")
        self.progressBar.setValue(0)
        self.all_files_info = []
        self.all_files_count = 0
        self.all_files_size = 0
        self.search_text = self.txtFilter.text().strip()

        self.scanner = FileScanner(folder)
        self.scanner.progress.connect(self.updateProgressBar)
        self.scanner.finished.connect(self.onScanFinished)
        self.scanner.start()

    def updateProgressBar(self, current, total):
        if total == 0:
            self.progressBar.setValue(0)
            return
        percent = int((current / total) * 100)
        self.progressBar.setValue(percent)

    def updateFilter(self):
        """Called by the filter timer after debouncing; updates the proxy model filter."""
        filter_text = self.txtFilter.text().strip()
        self.proxyModel.setFilterFixedString(filter_text)
        self.updateSummary()

    def onOnlyUnusedChanged(self, state):
        """Called when the 'Show Only Unused Samples' checkbox changes state."""
        self.proxyModel.setOnlyUnused(state == QtCore.Qt.Checked)
        self.updateSummary()

    def onScanFinished(self, files_info):
        self.all_files_info = files_info
        self.all_files_count = len(files_info)
        self.all_files_size = sum(item['size'] for item in files_info)
        self.model.updateData(files_info)
        self.updateSummary()
        self.progressBar.setValue(100)

    # -------------------------- Filtering Methods --------------------------
    def onFilterTextChanged(self, text):
        self.filterTimer.start(300)  # 300ms debounce
        self.proxyModel.setFilterFixedString(text)

    def onSizeUnitChanged(self, index):
        self.size_unit = self.comboSizeUnit.currentText()
        self.model.size_unit = self.size_unit
        self.model.layoutChanged.emit()
        self.updateSummary()

    def onOnlyUnusedChanged(self, state):
        self.proxyModel.setOnlyUnused(state == QtCore.Qt.Checked)
        self.updateSummary()

    def updateSummary(self):
        summary_text = (f"Scanned {self.all_files_count} files. "
                        f"Total Size: {self.bytesToUnit(self.all_files_size):.2f} {self.size_unit}")
        self.labelSummary.setText(summary_text)

    def bytesToUnit(self, size_in_bytes):
        if self.size_unit == "KB":
            return size_in_bytes / 1024
        elif self.size_unit == "MB":
            return size_in_bytes / (1024 ** 2)
        elif self.size_unit == "GB":
            return size_in_bytes / (1024 ** 3)
        else:
            return size_in_bytes

    # -------------------------- Deletion Methods --------------------------
    def deleteSelected(self):
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

    def attemptDeleteMultiple(self, file_infos):
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
    def findDuplicates(self):
        if not self.all_files_info:
            QtWidgets.QMessageBox.information(self, "No Files", "Please scan a folder first.")
            return
        self.duplicateFinder = DuplicateFinder(self.all_files_info)
        self.duplicateFinder.finished.connect(self.onDuplicatesFound)
        self.duplicateFinder.start()

    def onDuplicatesFound(self, duplicate_groups):
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

    # -------------------------- Audio Preview --------------------------
    def previewSelected(self):
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
        QtWidgets.QMessageBox.information(self, "Playing", f"Playing {os.path.basename(file_path)}.")

# -------------------------- Main -------------------------- #

def main():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
