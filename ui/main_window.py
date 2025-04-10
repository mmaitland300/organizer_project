# Required Imports
import os
import shutil
import sys
from typing import List, Dict, Optional, Any
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl, pyqtSlot
from send2trash import send2trash

# Import models
from models.file_model import FileTableModel, FileFilterProxyModel
# Import file scanning and duplicate finder classes from core
from core.file_scanner import FileScanner, HashWorker
from core.duplicate_finder import DuplicateFinder
# Import utility functions and cache manager
from utils.helpers import (
    parse_multi_dim_tags,
    format_multi_dim_tags,
    validate_tag_dimension,
    normalize_tag,
    bytes_to_unit,
    format_duration,
    open_file_location,
    compute_hash,
    format_time,
    detect_key_from_filename,
    unify_detected_key
)
from utils.cache_manager import CacheManager
# Import configuration settings and constants
from config.settings import (
    MAX_HASH_FILE_SIZE,
    HASH_TIMEOUT_SECONDS,
    AUDIO_EXTENSIONS,
    KEY_REGEX,
    ENABLE_ADVANCED_AUDIO_ANALYSIS,
    ENABLE_WAVEFORM_PREVIEW,
    TinyTag,  # May be None if not available.
    librosa,
    plt,
    np,
    FigureCanvas
)

# -------------------------- Duplicate Manager Dialog --------------------------
class DuplicateManagerDialog(QtWidgets.QDialog):
    """
    Dialog to display and manage duplicate files with an option for waveform preview.
    """
    def __init__(self, duplicate_groups: List[List[Dict[str, Any]]], size_unit: str = "KB", use_recycle_bin: bool = True, parent: Optional[QtWidgets.QWidget] = None) -> None:
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

        self.btnViewWaveform = QtWidgets.QPushButton("View Waveform")
        self.btnViewWaveform.clicked.connect(self.viewWaveform)
        btn_layout.addWidget(self.btnViewWaveform)

        self.btnClose = QtWidgets.QPushButton("Close")
        self.btnClose.clicked.connect(self.accept)
        btn_layout.addWidget(self.btnClose)

        self.populateTree(duplicate_groups)

    def populateTree(self, duplicate_groups: List[List[Dict[str, Any]]]) -> None:
        self.tree.clear()
        for group_index, group in enumerate(duplicate_groups, start=1):
            parent_item = QtWidgets.QTreeWidgetItem(self.tree)
            parent_item.setText(0, f"Group {group_index} ({len(group)} files)")
            parent_item.setFlags(parent_item.flags() & ~QtCore.Qt.ItemIsSelectable)
            for info in group:
                child = QtWidgets.QTreeWidgetItem(parent_item)
                child.setText(0, info['path'])
                size_value = bytes_to_unit(info['size'], self.size_unit)
                child.setText(1, f"{size_value:.2f} {self.size_unit}")
                child.setText(2, info['mod_time'].strftime("%Y-%m-%d %H:%M:%S"))
                child.setText(3, info.get('hash', ''))
                child.setFlags(child.flags() | QtCore.Qt.ItemIsUserCheckable)
                child.setCheckState(0, QtCore.Qt.Unchecked)
        self.tree.expandAll()

    def selectAll(self) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Checked)

    def deselectAll(self) -> None:
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Unchecked)

    def deleteSelected(self) -> None:
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
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            parent = root.child(i)
            for j in range(1, parent.childCount()):
                parent.child(j).setCheckState(0, QtCore.Qt.Checked)
        self.deleteSelected()

    def openContainingFolder(self) -> None:
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
        
    def viewWaveform(self) -> None:
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

# -------------------------- Waveform Player Widget --------------------------
class WaveformPlayerWidget(QtWidgets.QWidget):
    """
    A widget to display a waveform via matplotlib and simultaneously play audio via QMediaPlayer.
    """
    def __init__(self, file_path: str, theme: str = "light", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.file_path = file_path
        self.theme = theme.lower()
        self.figure = None
        self.ax = None
        self.canvas = None
        self.cursor_line = None
        self.duration_ms = 0
        self.total_duration_secs = 0
        self.setup_ui()
        self.load_audio_and_plot()
        self.init_player()
        self.applyTheme(self.theme)

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.figure, self.ax = plt.subplots(figsize=(6, 3))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        slider_layout = QtWidgets.QHBoxLayout()
        self.currentTimeLabel = QtWidgets.QLabel("0:00")
        slider_layout.addWidget(self.currentTimeLabel)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        slider_layout.addWidget(self.slider)
        self.totalTimeLabel = QtWidgets.QLabel("0:00")
        slider_layout.addWidget(self.totalTimeLabel)
        layout.addLayout(slider_layout)
        controls_layout = QtWidgets.QHBoxLayout()
        self.playButton = QtWidgets.QPushButton("Play")
        self.playButton.clicked.connect(self.toggle_playback)
        controls_layout.addWidget(self.playButton)
        self.update_timer = QtCore.QTimer(self)
        self.update_timer.setInterval(100)
        self.update_timer.timeout.connect(self.update_cursor)
        layout.addLayout(controls_layout)
        self.canvas.mpl_connect("button_press_event", self.on_canvas_click)

    def load_audio_and_plot(self):
        try:
            y, sr = librosa.load(self.file_path, sr=None, mono=True)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Could not load audio:\n{e}")
            return
        desired_points = 1000
        factor = max(1, int(len(y) / desired_points))
        y_downsampled = y[::factor]
        times = np.linspace(0, len(y) / sr, num=len(y_downsampled))
        self.ax.clear()
        self.ax.plot(times, y_downsampled, color="gray")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Amplitude")
        self.ax.set_title("Waveform Player")
        self.duration_ms = int(len(y) / sr * 1000)
        self.total_duration_secs = len(y)/sr
        self.totalTimeLabel.setText(format_time(self.total_duration_secs))
        self.canvas.draw()
        self.totalTimeLabel.setText(format_time(self.total_duration_secs))

    def init_player(self):
        self.player = QMediaPlayer(self)
        url = QtCore.QUrl.fromLocalFile(os.path.abspath(self.file_path))
        media = QMediaContent(url)
        self.player.setMedia(media)
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.positionChanged.connect(self.on_position_changed)
        self.slider.setMinimum(0)
        self.slider.setMaximum(self.duration_ms)
        self.slider.sliderMoved.connect(self.on_slider_moved)

    def applyTheme(self, theme: str):
        if theme == "dark":
            self.figure.patch.set_facecolor("#2B2B2B")
            self.ax.set_facecolor("#3A3F4B")
            self.ax.spines["bottom"].set_color("white")
            self.ax.spines["top"].set_color("white")
            self.ax.spines["left"].set_color("white")
            self.ax.spines["right"].set_color("white")
            self.ax.xaxis.label.set_color("white")
            self.ax.yaxis.label.set_color("white")
            self.ax.title.set_color("white")
            self.ax.tick_params(axis='x', colors='white')
            self.ax.tick_params(axis='y', colors='white')
        else:
            self.figure.patch.set_facecolor("white")
            self.ax.set_facecolor("white")
            for spine in self.ax.spines.values():
                spine.set_color("black")
            self.ax.xaxis.label.set_color("black")
            self.ax.yaxis.label.set_color("black")
            self.ax.title.set_color("black")
            self.ax.tick_params(axis='x', colors='black')
            self.ax.tick_params(axis='y', colors='black')
        self.figure.tight_layout()
        self.canvas.draw()

    def toggle_playback(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.playButton.setText("Play")
            self.update_timer.stop()
        else:
            self.player.play()
            self.playButton.setText("Pause")
            self.update_timer.start()

    def on_duration_changed(self, duration):
        if duration > 0:
            self.slider.setMaximum(duration)
            self.totalTimeLabel.setText(format_time(duration / 1000.0))
            self.ax.set_xlim(0, duration / 1000.0)
            self.canvas.draw_idle()

    def on_position_changed(self, position):
        self.slider.setValue(position)
        current_sec = position / 1000.0
        self.currentTimeLabel.setText(format_time(current_sec))

    def on_slider_moved(self, pos):
        self.player.setPosition(pos)

    def update_cursor(self):
        pos_sec = self.player.position() / 1000.0
        if self.cursor_line is not None:
            self.cursor_line.remove()
        self.cursor_line = self.ax.axvline(pos_sec, color="red")
        self.canvas.draw_idle()

    def on_canvas_click(self, event):
        if event.xdata is not None and event.button == 1:
            new_pos_sec = max(0, event.xdata)
            new_pos_ms = int(new_pos_sec * 1000)
            self.player.setPosition(new_pos_ms)
            self.slider.setValue(new_pos_ms)
            self.update_cursor()

# -------------------------- Recommendations Dialog --------------------------
class RecommendationsDialog(QtWidgets.QDialog):
    """
    Dialog to display sample recommendations based on similar BPM or tags.
    """
    def __init__(self, recommendations: List[Dict[str, Any]], parent: Optional[QtWidgets.QWidget] = None) -> None:
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

# ------------------------- Multi-Dimensional Tag Editor Dialog --------------------------
class MultiDimTagEditorDialog(QtWidgets.QDialog):
    def __init__(self, tag_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Tags")
        self.resize(400, 300)
        if isinstance(tag_data, list):
            self.tag_data = {"general": tag_data}
        elif isinstance(tag_data, dict):
            self.tag_data = tag_data.copy()
        else:
            self.tag_data = {}
        main_layout = QtWidgets.QVBoxLayout(self)
        self.tableWidget = QtWidgets.QTableWidget()
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Dimension", "Tag"])
        self.tableWidget.horizontalHeader().setStretchLastSection(True)
        main_layout.addWidget(self.tableWidget)
        self.loadData()
        row_layout = QtWidgets.QHBoxLayout()
        self.dimensionEdit = QtWidgets.QLineEdit()
        self.dimensionEdit.setPlaceholderText("Dimension (e.g., genre, mood)")
        self.tagEdit = QtWidgets.QLineEdit()
        self.tagEdit.setPlaceholderText("Tag (e.g., ROCK)")
        row_layout.addWidget(self.dimensionEdit)
        row_layout.addWidget(self.tagEdit)
        main_layout.addLayout(row_layout)
        btnAdd = QtWidgets.QPushButton("Add Tag")
        btnAdd.clicked.connect(self.addTag)
        main_layout.addWidget(btnAdd)
        btnBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btnBox.accepted.connect(self.accept)
        btnBox.rejected.connect(self.reject)
        main_layout.addWidget(btnBox)

    def loadData(self):
        self.tableWidget.setRowCount(0)
        for dimension, tags in self.tag_data.items():
            for tag in tags:
                row = self.tableWidget.rowCount()
                self.tableWidget.insertRow(row)
                dim_item = QtWidgets.QTableWidgetItem(dimension.capitalize())
                tag_item = QtWidgets.QTableWidgetItem(tag)
                self.tableWidget.setItem(row, 0, dim_item)
                self.tableWidget.setItem(row, 1, tag_item)

    def addTag(self):
        dimension = self.dimensionEdit.text().strip().lower()
        tag = self.tagEdit.text().strip().upper()
        if not dimension or not tag:
            return
        row = self.tableWidget.rowCount()
        self.tableWidget.insertRow(row)
        dim_item = QtWidgets.QTableWidgetItem(dimension.capitalize())
        tag_item = QtWidgets.QTableWidgetItem(tag)
        self.tableWidget.setItem(row, 0, dim_item)
        self.tableWidget.setItem(row, 1, tag_item)
        self.dimensionEdit.clear()
        self.tagEdit.clear()

    def get_tags(self) -> dict:
        new_tags = {}
        for row in range(self.tableWidget.rowCount()):
            dim_item = self.tableWidget.item(row, 0)
            tag_item = self.tableWidget.item(row, 1)
            if dim_item and tag_item:
                dimension = dim_item.text().lower()
                tag = tag_item.text().upper()
                new_tags.setdefault(dimension, [])
                if tag not in new_tags[dimension]:
                    new_tags[dimension].append(tag)
        return new_tags

# -------------------------- Main Window --------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Musicians Organizer")
        self.resize(1000, 700)
        self.all_files_info = []
        self.all_files_count = 0
        self.all_files_size = 0
        self.size_unit = "KB"
        self.search_text = ""
        self.last_folder = ""
        self.cubase_folder = ""
        self.initUI()
        self.loadSettings()
        self.filterTimer = QtCore.QTimer(self)
        self.filterTimer.setSingleShot(True)
        self.filterTimer.timeout.connect(self.updateFilter)
        self.chkOnlyUnused = QtWidgets.QCheckBox("Show Only Unused Samples")
        self.chkOnlyUnused.setChecked(False)
        self.chkOnlyUnused.stateChanged.connect(self.onOnlyUnusedChanged)
        self.player = QMediaPlayer()

    def initUI(self) -> None:
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self.fileToolBar = QtWidgets.QToolBar("File Management")
        self.fileToolBar.setObjectName("fileToolBar")
        self.fileToolBar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.fileToolBar)
        actSelectFolder = QtWidgets.QAction("Select Folder", self)
        actSelectFolder.setToolTip("Select a folder to scan for music samples.")
        actSelectFolder.triggered.connect(self.selectFolder)
        self.fileToolBar.addAction(actSelectFolder)
        actFindDuplicates = QtWidgets.QAction("Find Duplicates", self)
        actFindDuplicates.setToolTip("Find duplicate files based on size/hash.")
        actFindDuplicates.triggered.connect(self.findDuplicates)
        self.fileToolBar.addAction(actFindDuplicates)
        actOpenFolder = QtWidgets.QAction("Open Folder", self)
        actOpenFolder.setToolTip("Open the folder of the selected file.")
        actOpenFolder.triggered.connect(self.openSelectedFileLocation)
        self.fileToolBar.addAction(actOpenFolder)
        actDeleteSelected = QtWidgets.QAction("Delete Selected", self)
        actDeleteSelected.setToolTip("Delete selected file(s).")
        actDeleteSelected.triggered.connect(self.deleteSelected)
        self.fileToolBar.addAction(actDeleteSelected)
        actSetCubase = QtWidgets.QAction("Set Cubase Folder", self)
        actSetCubase.setToolTip("Set or change the Cubase integration folder.")
        actSetCubase.triggered.connect(self.setCubaseFolder)
        self.fileToolBar.addAction(actSetCubase)
        leftExpSpacer = QtWidgets.QWidget(self)
        leftExpSpacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.fileToolBar.addWidget(leftExpSpacer)
        self.progressBar = QtWidgets.QProgressBar()
        self.progressBar.setValue(0)
        self.progressBar.setFixedWidth(200)
        progressAction = QtWidgets.QWidgetAction(self.fileToolBar)
        progressAction.setDefaultWidget(self.progressBar)
        self.cancelButton = QtWidgets.QPushButton("Cancel")
        self.cancelButton.setToolTip("Cancel current operation")
        self.cancelButton.setEnabled(False)
        self.cancelButton.clicked.connect(self.cancelCurrentOperation)
        self.fileToolBar.addWidget(self.cancelButton)
        self.fileToolBar.addAction(progressAction)
        rightExpSpacer = QtWidgets.QWidget(self)
        rightExpSpacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.fileToolBar.addWidget(rightExpSpacer)
        self.audioToolBar = QtWidgets.QToolBar("Audio Tools")
        self.audioToolBar.setObjectName("audioToolBar")
        self.audioToolBar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.audioToolBar)
        actPreview = QtWidgets.QAction("Preview", self)
        actPreview.setToolTip("Preview the selected audio file.")
        actPreview.triggered.connect(self.previewSelected)
        self.audioToolBar.addAction(actPreview)
        actStopPreview = QtWidgets.QAction("Stop", self)
        actStopPreview.setToolTip("Stop the audio preview.")
        actStopPreview.triggered.connect(self.stopPreview)
        self.audioToolBar.addAction(actStopPreview)
        actWaveform = QtWidgets.QAction("Waveform", self)
        actWaveform.setToolTip("View the waveform of the selected audio file.")
        actWaveform.triggered.connect(self.waveformPreview)
        self.audioToolBar.addAction(actWaveform)
        actIntegratedWaveform = QtWidgets.QAction("Waveform Player", self)
        actIntegratedWaveform.setToolTip("View waveform and playback sample")
        actIntegratedWaveform.triggered.connect(self.launchWaveformPlayer)
        self.audioToolBar.addAction(actIntegratedWaveform)
        spacer2 = QtWidgets.QWidget(self)
        spacer2.setFixedWidth(15)
        self.audioToolBar.addWidget(spacer2)
        actAutoTag = QtWidgets.QAction("Auto Tag", self)
        actAutoTag.setToolTip("Automatically tag files (BPM & Key detection).")
        actAutoTag.triggered.connect(self.autoTagFiles)
        self.audioToolBar.addAction(actAutoTag)
        actEditTags = QtWidgets.QAction("Edit Tags", self)
        actEditTags.setToolTip("Edit tags using the multi-dimensional tag editor.")
        actEditTags.triggered.connect(self.editTagsForSelectedFile)
        self.audioToolBar.addAction(actEditTags)
        actRecommend = QtWidgets.QAction("Recommend", self)
        actRecommend.setToolTip("Recommend similar samples based on BPM or tags.")
        actRecommend.triggered.connect(self.recommendSimilarSamples)
        self.audioToolBar.addAction(actRecommend)
        actSendToCubase = QtWidgets.QAction("Send to Cubase", self)
        actSendToCubase.setToolTip("Send selected file(s) to the configured Cubase folder.")
        actSendToCubase.triggered.connect(self.sendToCubase)
        self.audioToolBar.addAction(actSendToCubase)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
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
        self.setStatusBar(QtWidgets.QStatusBar())
        menuBar = self.menuBar()
        helpMenu = menuBar.addMenu("Help")
        helpAction = QtWidgets.QAction("Usage Help", self)
        helpAction.triggered.connect(self.showHelpDialog)
        helpMenu.addAction(helpAction)
        themeMenu = menuBar.addMenu("Theme")
        actLight = QtWidgets.QAction("Light Mode", self)
        actLight.triggered.connect(lambda: self.setTheme("light", save=True))
        themeMenu.addAction(actLight)
        actDark = QtWidgets.QAction("Dark Mode", self)
        actDark.triggered.connect(lambda: self.setTheme("dark", save=True))
        themeMenu.addAction(actDark)

    def editTagsForSelectedFile(self) -> None:
        selected_indexes = self.tableView.selectionModel().selectedRows()
        if not selected_indexes:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select a file to edit tags.")
            return
        source_index = self.proxyModel.mapToSource(selected_indexes[0])
        file_info = self.model.getFileAt(source_index.row())
        current_tags = file_info.get("tags", {})
        if isinstance(current_tags, list):
            current_tags = {"general": current_tags}
        dialog = MultiDimTagEditorDialog(current_tags, parent=self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            updated_tags = dialog.get_tags()
            file_info["tags"] = updated_tags
            self.model.dataChanged.emit(source_index, source_index, [QtCore.Qt.DisplayRole])

    def applyLightThemeStylesheet(self) -> None:
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ffffff;
                color: #000000;
            }
            QToolBar {
                background-color: #f0f0f0;
                spacing: 6px;
            }
            QToolBar QToolButton {
                background-color: #ffffff;
                color: #000000;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px 10px;
                margin: 3px;
            }
            QToolBar QToolButton:hover {
                background-color: #e0e0e0;
            }
            QLabel, QCheckBox, QRadioButton {
                color: #333333;
                font-size: 13px;
            }
            QLineEdit {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                color: #333333;
                border-radius: 4px;
                padding: 4px;
            }
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                color: #333333;
                border-radius: 4px;
                padding: 2px;
            }
            QTableView {
                background-color: #ffffff;
                alternate-background-color: #f9f9f9;
                gridline-color: #dddddd;
                color: #000000;
                font-size: 13px;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                color: #333333;
                border: 1px solid #cccccc;
                padding: 4px;
            }
            QProgressBar {
                background-color: #ffffff;
                border: 1px solid #cccccc;
                text-align: center;
                color: #333333;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
            }
            QStatusBar {
                background-color: #f0f0f0;
                border-top: 1px solid #cccccc;
            }
            QMenuBar {
                background-color: #f0f0f0;
                color: #333333;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 12px;
            }
            QMenuBar::item:selected {
                background-color: #4caf50;
            }
            QMenu {
                background-color: #ffffff;
                border: 1px solid #cccccc;
            }
            QMenu::item {
                padding: 4px 20px;
                color: #333333;
            }
            QMenu::item:selected {
                background-color: #4caf50;
            }
        """)

    def applyDarkThemeStylesheet(self) -> None:
        self.setStyleSheet("""
            QMainWindow {
                background-color: #282c34;
                color: #ffffff;
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
            QLabel, QCheckBox, QRadioButton {
                color: #abb2bf;
                font-size: 13px;
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

    def setTheme(self, theme: str, save: bool = True) -> None:
        self.theme = theme.lower()
        if self.theme == "dark":
            self.applyDarkThemeStylesheet()
        else:
            self.applyLightThemeStylesheet()
        if save:
            self.saveSettings()

    def showHelpDialog(self) -> None:
        help_text = (
            "Musicians Organizer \n\n"
            "1. Select Folder: Choose a directory with music samples.\n"
            "2. Filter: Type in the left panel to filter files by name.\n"
            "3. Edit Metadata: Double-click Duration, BPM, Key, or Tags in the table.\n"
            "4. Duplicates: Use the toolbar to find duplicate files using MD5 hashing.\n"
            "5. Preview Audio: Use the toolbar to preview or stop preview of audio file.\n"
            "6. Waveform: View waveform for audio files.\n"
            "7. Delete Selected: Click 'Delete Selected' on the toolbar to send files to recycle bin or delete permanently.\n"
            "8. Cubase Integration: Set Cubase folder and send files directly.\n"
            "9. Progress Bar: Scanning and duplicate detection run in background threads, ensuring the UI remains responsive.\n"
            "10. Sorting: Click on column headers to sort files by different attributes.\n"
            "11. Theme: Click the 'Theme' menu to switch between light and dark themes."
        )
        QtWidgets.QMessageBox.information(self, "Usage Help", help_text)

    def getSelectedFilePath(self):
        selection = self.tableView.selectionModel().selectedRows()
        if selection:
            index = selection[0]
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            if file_info:
                return file_info['path']
        return None

    def loadSettings(self) -> None:
        settings = QtCore.QSettings("MMSoftware", "MusiciansOrganizer")
        geometry = settings.value("windowGeometry")
        if geometry:
            self.restoreGeometry(geometry)
        state = settings.value("windowState")
        if state:
            self.restoreState(state)
        self.last_folder = settings.value("lastFolder", "")
        self.size_unit = settings.value("sizeUnit", "KB")
        self.comboSizeUnit.setCurrentText(self.size_unit)
        recycle_bin = settings.value("useRecycleBin", "true")
        self.chkRecycleBin.setChecked(recycle_bin.lower() == "true")
        self.cubase_folder = settings.value("cubaseFolder", "")
        self.theme = settings.value("theme", "light")
        self.setTheme(self.theme, save=False)

    def saveSettings(self) -> None:
        settings = QtCore.QSettings("MMSoftware", "MusiciansOrganizer")
        settings.setValue("windowGeometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("lastFolder", self.last_folder)
        settings.setValue("sizeUnit", self.size_unit)
        settings.setValue("useRecycleBin", "true" if self.chkRecycleBin.isChecked() else "false")
        settings.setValue("cubaseFolder", self.cubase_folder)
        settings.setValue("theme", self.theme)

    def closeEvent(self, event):
        self.saveSettings()
        event.accept()

    def selectFolder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.last_folder = folder
            self.scanner = FileScanner(folder, bpm_detection=self.chkBPM.isChecked())
            # Connect progress updates to the progress bar.
            self.scanner.progress.connect(lambda cur, tot: self.progressBar.setValue(int(cur / tot * 100)))
            # When scanning finishes, call onScanFinished.
            self.scanner.finished.connect(self.onScanFinished)
            # Clean up the reference to avoid lingering finished thread objects.
            self.scanner.finished.connect(lambda: setattr(self, "scanner", None))
            # Disable the cancel button when the scan operation finishes.
            self.scanner.finished.connect(lambda: self.cancelButton.setEnabled(False))
            # Enable the cancel button so the user can cancel the scanning.
            self.cancelButton.setEnabled(True)
            self.scanner.start()

    def onScanFinished(self, files):
        self.all_files_info = files
        self.model.updateData(files)
        total_size = sum(file['size'] for file in files)
        self.labelSummary.setText(f"Scanned {len(files)} files. Total size: {bytes_to_unit(total_size, self.size_unit):.2f} {self.size_unit}.")

    def findDuplicates(self):
        self.progressBar.setValue(0)
        self.duplicateFinder = DuplicateFinder(self.all_files_info)
        # Connect progress updates to update the progress bar.
        self.duplicateFinder.progress.connect(self.onDuplicateProgress)
        # When duplicate detection finishes, call onDuplicatesFound.
        self.duplicateFinder.finished.connect(self.onDuplicatesFound)
        # Clean up the reference to the duplicate finder thread when finished.
        self.duplicateFinder.finished.connect(lambda: setattr(self, "duplicateFinder", None))
        # Disable the cancel button when duplicate detection finishes.
        self.duplicateFinder.finished.connect(lambda: self.cancelButton.setEnabled(False))
        # Enable the cancel button for the duplicate detection operation.
        self.cancelButton.setEnabled(True)
        self.duplicateFinder.start()

    
    @QtCore.pyqtSlot(int, int)
    def onDuplicateProgress(self, current, total):
        """
        Slot to update the progress bar while duplicates are being found.
        """
        if total > 0:
            percent = int((current / total) * 100)
            self.progressBar.setValue(percent)
        else:
            self.progressBar.setValue(0)

    @QtCore.pyqtSlot(list)
    def onDuplicatesFound(self, duplicate_groups):
        """
        Called when the DuplicateFinder thread has finished. 
        Show the DuplicateManagerDialog if duplicates found, else show a message.
        """
        if duplicate_groups:
            dlg = DuplicateManagerDialog(
                duplicate_groups, 
                size_unit=self.size_unit,
                use_recycle_bin=self.chkRecycleBin.isChecked(),
                parent=self
            )
            dlg.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "Find Duplicates", "No duplicate files found.")

    def openSelectedFileLocation(self):
        path = self.getSelectedFilePath()
        if path:
            open_file_location(path)
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")

    def deleteSelected(self):
        """
        Delete the files that are selected in the table.
        This method confirms deletion with the user and then removes files
        from disk (using send2trash if the recycle bin option is enabled)
        and updates the model.
        """
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.information(self, "Delete Selected", "No files selected.")
            return

        confirm = QtWidgets.QMessageBox.question(
            self, "Confirm Deletion",
            f"Are you sure you want to delete {len(selection)} file(s)?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return

        errors = []
        indices_to_delete = []
        # Collect indices to be deleted
        for index in selection:
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            try:
                if self.chkRecycleBin.isChecked():
                    send2trash(file_info['path'])
                else:
                    os.remove(file_info['path'])
                indices_to_delete.append(source_index.row())
            except Exception as e:
                errors.append(f"Error deleting {file_info['path']}: {str(e)}")

        if errors:
            QtWidgets.QMessageBox.critical(self, "Deletion Errors", "\n".join(errors))
        else:
            QtWidgets.QMessageBox.information(self, "Delete Selected", "Selected files deleted successfully.")

        # Remove deleted files from self.all_files_info and update model.
        # To avoid index issues, remove indices in reverse order.
        for row in sorted(indices_to_delete, reverse=True):
            del self.all_files_info[row]
        self.model.updateData(self.all_files_info)

    def setCubaseFolder(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Cubase Folder")
        if folder:
            self.cubase_folder = folder

    def previewSelected(self):
        path = self.getSelectedFilePath()
        if path:
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            self.player.play()
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")

    def stopPreview(self):
        self.player.stop()

    def waveformPreview(self):
        path = self.getSelectedFilePath()
        if path:
            dialog = WaveformDialog(path, parent=self)
            dialog.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")

    def launchWaveformPlayer(self):
        path = self.getSelectedFilePath()
        if path:
            player_widget = WaveformPlayerWidget(path, theme=self.theme)
            player_dialog = QtWidgets.QDialog(self)
            player_dialog.setWindowTitle("Waveform Player")
            layout = QtWidgets.QVBoxLayout(player_dialog)
            layout.addWidget(player_widget)
            player_dialog.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")
    # Auto Tagging: Detect BPM and Key from filename
    def autoTagFiles(self) -> None:
        """
        Automatically tag files based on BPM and key detection.
        For each audio file in all_files_info, update its 'tags' field:
        - Add detected key (via detect_key_from_filename) into the 'key' dimension.
        - Classify BPM into ranges and add a tag in the 'bpm' dimension.
        Update the model after processing.
        """
        updated_count = 0
        for file_info in self.all_files_info:
            # Process only audio files by checking extension.
            ext = os.path.splitext(file_info['path'])[1].lower()
            if ext not in AUDIO_EXTENSIONS:
                continue
            # Auto-detect key if not set or marked as "N/A"
            detected_key = detect_key_from_filename(file_info['path'])
            if detected_key and (not file_info.get('key') or file_info.get('key') == "N/A"):
                file_info['key'] = detected_key
                tags = file_info.get('tags', {})
                if isinstance(tags, list):
                    tags = {"general": tags}
                tags.setdefault("key", [])
                if detected_key not in tags["key"]:
                    tags["key"].append(detected_key)
                file_info['tags'] = tags
                updated_count += 1

            # Classify BPM value into a tag if available
            bpm = file_info.get('bpm')
            if bpm is not None:
                if bpm < 90:
                    bpm_tag = "Slow"
                elif bpm <= 120:
                    bpm_tag = "Medium"
                else:
                    bpm_tag = "Fast"
                tags = file_info.get('tags', {})
                if isinstance(tags, list):
                    tags = {"general": tags}
                tags.setdefault("bpm", [])
                if bpm_tag not in tags["bpm"]:
                    tags["bpm"].append(bpm_tag)
                file_info['tags'] = tags
                updated_count += 1

        self.model.updateData(self.all_files_info)
        QtWidgets.QMessageBox.information(self, "Auto Tag",
                                        f"Auto-tagging applied to {updated_count} updates.")

    def recommendSimilarSamples(self):
        """
        Recommend samples similar to the currently selected file.
        Similarity is defined based on a close BPM value (within ±5) and/or matching key.
        This method collects files that meet the criteria and displays them
        in a RecommendationsDialog.
        """
        selected_indexes = self.tableView.selectionModel().selectedRows()
        if not selected_indexes:
            QtWidgets.QMessageBox.information(self, "No Selection", "Please select a file for recommendations.")
            return

        # Use the first selected file as the reference
        source_index = self.proxyModel.mapToSource(selected_indexes[0])
        ref_file = self.model.getFileAt(source_index.row())
        ref_bpm = ref_file.get('bpm')
        ref_key = ref_file.get('key')

        recommendations = []
        # Loop through all files to find similar ones
        for file_info in self.all_files_info:
            if file_info['path'] == ref_file['path']:
                continue
            similar = False
            # Compare BPM if available
            if ref_bpm is not None and file_info.get('bpm') is not None:
                if abs(file_info['bpm'] - ref_bpm) <= 5:
                    similar = True
            # Compare key if available
            if ref_key and file_info.get('key') == ref_key:
                similar = True
            if similar:
                recommendations.append(file_info)

        if recommendations:
            dlg = RecommendationsDialog(recommendations, parent=self)
            dlg.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "Recommend", "No similar samples found.")

    def sendToCubase(self):
        """
        Send selected file(s) to the configured Cubase folder.
        This is done by copying the selected files to the Cubase folder.
        """
        if not self.cubase_folder:
            QtWidgets.QMessageBox.warning(self, "Cubase Folder Not Set",
                                        "Please set the Cubase folder before sending files.")
            return
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.information(self, "No Selection",
                                            "Please select one or more files to send to Cubase.")
            return
        errors = []
        for index in selection:
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            if file_info:
                source_path = file_info['path']
                try:
                    shutil.copy(source_path, self.cubase_folder)
                except Exception as e:
                    errors.append(f"Failed to send {source_path}: {str(e)}")
        if errors:
            QtWidgets.QMessageBox.critical(self, "Send to Cubase Errors", "\n".join(errors))
        else:
            QtWidgets.QMessageBox.information(self, "Send to Cubase",
                                            "Selected files sent to Cubase folder successfully.")

    def onFilterTextChanged(self, text):
        self.search_text = text
        self.filterTimer.start(300)

    def updateFilter(self):
        self.proxyModel.setFilterFixedString(self.search_text)

    def onOnlyUnusedChanged(self, state):
        self.proxyModel.setOnlyUnused(state == QtCore.Qt.Checked)

    def onSizeUnitChanged(self, index):
        self.size_unit = self.comboSizeUnit.currentText()
        self.model.size_unit = self.size_unit
        self.model.updateData(self.all_files_info)

    def cancelCurrentOperation(self):
        # Cancel file scanning if active.
        if hasattr(self, 'scanner') and self.scanner is not None:
            self.scanner.cancel()
            QtWidgets.QMessageBox.information(self, "Operation Cancelled", "File scanning has been cancelled.")
            self.cancelButton.setEnabled(False)
        # Cancel duplicate detection if active.
        elif hasattr(self, 'duplicateFinder') and self.duplicateFinder is not None:
            self.duplicateFinder.cancel()
            QtWidgets.QMessageBox.information(self, "Operation Cancelled", "Duplicate detection has been cancelled.")
            self.cancelButton.setEnabled(False)
