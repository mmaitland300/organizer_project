# FILE: ui/main_window.py

import logging
import os
import shutil

# Import Enum if ControllerState is used (it is)
from enum import Enum  # Ensure this is imported
from typing import Any, Dict, List, Optional

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QDialog, QListWidget, QVBoxLayout, QDialogButtonBox, QAbstractItemView, QTableWidget, QTableWidgetItem, QHeaderView
from PyQt5.QtCore import QUrl, pyqtSlot
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtWidgets import QMessageBox
from send2trash import send2trash

from config.settings import AUDIO_EXTENSIONS  # Keep for checks if needed

# Models, Services, Utils, Config, Dialogs, Controllers...
from models.file_model import FileFilterProxyModel, FileTableModel
from services.auto_tagger import AutoTagService
from services.database_manager import DatabaseManager

# Import Controllers and State Enum
from ui.controllers import (
    AnalysisController,
    ControllerState,
    DuplicatesController,
    ScanController,
)

# Import dialogs used
from ui.dialogs.feature_view_dialog import FeatureViewDialog # Import the new dialog
from ui.dialogs.duplicate_manager_dialog import DuplicateManagerDialog
from ui.dialogs.multi_dim_tag_editor_dialog import MultiDimTagEditorDialog
from ui.dialogs.waveform_dialog import WaveformDialog

from ui.dialogs.waveform_player_widget import WaveformPlayerWidget
from utils.helpers import bytes_to_unit, open_file_location

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# --- New Similarity Results Dialog ---
class SimilarityResultsDialog(QDialog):
    """
    A simple dialog to display similarity search results.
    Shows file path and distance in a table.
    """
    def __init__(self, results: List[Dict[str, Any]], reference_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Files Similar to: {os.path.basename(reference_path)}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(300)

        layout = QVBoxLayout(self)

        self.tableWidget = QTableWidget()
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Distance", "File Path"])
        self.tableWidget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableWidget.setEditTriggers(QAbstractItemView.NoEditTriggers) # Read-only
        # Allow sorting by distance
        self.tableWidget.setSortingEnabled(True)

        self.tableWidget.setRowCount(len(results))
        for row, result in enumerate(results):
            # Distance Item (Numerical, for sorting)
            distance_item = QTableWidgetItem()
            # Store distance as float data, display formatted string
            distance_val = result.get('distance', float('inf'))
            distance_item.setData(QtCore.Qt.DisplayRole, f"{distance_val:.4f}")
            # Ensure it sorts numerically if needed (though string sort might be okay for floats)
            # distance_item.setData(QtCore.Qt.UserRole, distance_val) # Alternative for custom sorting

            # Path Item
            path_item = QTableWidgetItem(result.get('path', 'N/A'))

            self.tableWidget.setItem(row, 0, distance_item)
            self.tableWidget.setItem(row, 1, path_item)

        # Resize columns after populating
        self.tableWidget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tableWidget.resizeColumnToContents(0)
        # Initial sort by distance ascending
        self.tableWidget.sortByColumn(0, QtCore.Qt.AscendingOrder)
        layout.addWidget(self.tableWidget)

        # Standard OK button
        buttonBox = QDialogButtonBox(QDialogButtonBox.Ok)
        buttonBox.accepted.connect(self.accept)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

# --- New Worker Thread for Statistics ---
class StatsWorker(QtCore.QThread):
    """Worker thread to calculate feature statistics in the background."""
    finished = QtCore.pyqtSignal(bool, str) # Signal: success(bool), message(str)
    # No progress signal needed for now, could be added if stats calc is chunked

    def __init__(self, parent=None):
        super().__init__(parent)
        # Ensure DatabaseManager is imported correctly
        from services.database_manager import DatabaseManager
        self.db_manager = DatabaseManager.instance()

    def run(self):
        """Performs the statistics calculation."""
        logger.info("StatsWorker thread run() method entered.")
        message = "Statistics updated successfully."
        success = False
        stats = None # Initialize stats variable

        try:
            # --- ADD try...except specifically around the DB call ---
            try:
                logger.info("StatsWorker: Calling get_feature_statistics(refresh=True)...")
                stats = self.db_manager.get_feature_statistics(refresh=True)
                logger.info("StatsWorker: get_feature_statistics call completed.")
            except Exception as db_error:
                logger.error(f"StatsWorker: CRITICAL ERROR during get_feature_statistics call: {db_error}", exc_info=True)
                message = f"Error calling database for statistics: {db_error}"
                success = False
                # Set stats to None ensure subsequent check fails gracefully
                stats = None
            # --- END specific try...except ---

            # Check the result *after* the call attempt
            if stats is not None:
                 success = True
                 logger.info("StatsWorker: Statistics calculation successful.")
            elif not message.startswith("Error calling database"): # Avoid overwriting DB error message
                 message = "Statistics calculation failed or returned no data."
                 logger.error(message)
                 success = False # Ensure success is False if stats is None

        except Exception as e:
            # Catch any other unexpected errors in the worker logic
            message = f"Unexpected error within StatsWorker run method: {e}"
            logger.error(message, exc_info=True)
            success = False
        finally:
            # This finally block should now always be reached unless the thread is forcibly killed
            logger.info(f"StatsWorker thread run() finished. Emitting finished signal (success={success}).")
            self.finished.emit(success, message)

class MainWindow(QtWidgets.QMainWindow):
    """
    Main window for Musicians Organizer. Integrates controllers for background
    tasks and provides enhanced filtering capabilities.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Musicians Organizer")
        self.resize(1000, 700)
        self.all_files_info: List[Dict[str, Any]] = []
        self.size_unit: str = "KB"
        self.last_folder: str = ""
        self.cubase_folder: str = ""
        self.theme: str = "light"  # Initialize theme attribute

        # --- Controllers ---
        self.scan_ctrl = ScanController(self)
        self.dup_ctrl = DuplicatesController(self)
        self.anal_ctrl = AnalysisController(self)
        self.stats_worker: Optional[StatsWorker] = None

        # --- ADD Explicit State Flag ---
        self._is_calculating_stats: bool = False
        # --- END State Flag ---

        # --- Media Player ---
        self.player = QMediaPlayer(self)

        # --- Initialize UI Elements (Models will be created in initUI) ---
        self.model: Optional[FileTableModel] = None
        self.proxyModel: Optional[FileFilterProxyModel] = None
        # Add placeholders for UI elements created in initUI for type hinting if desired
        self.comboKeyFilter: Optional[QtWidgets.QComboBox] = None
        self.spinBpmMin: Optional[QtWidgets.QSpinBox] = None
        self.spinBpmMax: Optional[QtWidgets.QSpinBox] = None
        self.txtTagTextFilter: Optional[QtWidgets.QLineEdit] = None
        self.txtFilter: Optional[QtWidgets.QLineEdit] = None
        self.tableView: Optional[QtWidgets.QTableView] = None
        self.chkOnlyUnused: Optional[QtWidgets.QCheckBox] = None
        self.comboSizeUnit: Optional[QtWidgets.QComboBox] = None
        self.chkRecycleBin: Optional[QtWidgets.QCheckBox] = None
        self.labelSummary: Optional[QtWidgets.QLabel] = None
        self.progressBar: Optional[QtWidgets.QProgressBar] = None

        # --- Debounce Timers ---
        # Timer for filename filter
        self.nameFilterTimer = QtCore.QTimer(self)
        self.nameFilterTimer.setSingleShot(True)
        self.nameFilterTimer.setInterval(300)  # 300ms delay

        # Timer for tag text filter
        self.tagFilterTimer = QtCore.QTimer(self)
        self.tagFilterTimer.setSingleShot(True)
        self.tagFilterTimer.setInterval(300)  # 300ms delay

        # --- Setup UI ---
        self.initUI()
        ## --- Connect Media Player Signals ---
        self.player.stateChanged.connect(self.on_player_state_changed)
        # --- Connect Controller Signals ---
        self._connect_controller_signals()

        # --- Load Settings ---
        self.loadSettings()

    def initUI(self) -> None:
        """Creates and lays out the UI widgets."""
        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Toolbars ---
        # File Management Toolbar
        self.fileToolBar = QtWidgets.QToolBar("File Management", self)
        self.fileToolBar.setObjectName("fileToolBar")
        self.fileToolBar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.fileToolBar)

        # Define actions (ensure objectName is set for state handling)
        self.actSelectFolder = QtWidgets.QAction("Select Folder", self)
        self.actSelectFolder.setObjectName("actSelectFolder")
        self.actSelectFolder.setToolTip("Select a folder to scan for music samples.")
        self.actSelectFolder.triggered.connect(self.selectFolder)
        self.fileToolBar.addAction(self.actSelectFolder)

        self.actFindDuplicates = QtWidgets.QAction("Find Duplicates", self)
        self.actFindDuplicates.setObjectName("actFindDuplicates")
        self.actFindDuplicates.setToolTip("Find duplicate files based on size/hash.")
        self.actFindDuplicates.triggered.connect(self.findDuplicates)
        self.fileToolBar.addAction(self.actFindDuplicates)

        # ... (Add other file toolbar actions: Open Folder, Delete Selected, Set Cubase) ...
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
        leftExpSpacer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        self.fileToolBar.addWidget(leftExpSpacer)

        self.progressBar = QtWidgets.QProgressBar(self)
        self.progressBar.setValue(0)
        self.progressBar.setFixedWidth(200)
        progressAction = QtWidgets.QWidgetAction(self.fileToolBar)
        progressAction.setDefaultWidget(self.progressBar)
        self.fileToolBar.addAction(progressAction)

        rightExpSpacer = QtWidgets.QWidget(self)
        rightExpSpacer.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        self.fileToolBar.addWidget(rightExpSpacer)

        # Audio Tools Toolbar
        self.audioToolBar = QtWidgets.QToolBar("Audio Tools", self)
        self.audioToolBar.setObjectName("audioToolBar")
        self.audioToolBar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.audioToolBar)

        # Define actions (ensure objectName is set for state handling)
        actPreview = QtWidgets.QAction("Preview", self)
        actPreview.setToolTip("Preview the selected audio file.")
        actPreview.triggered.connect(self.previewSelected)
        self.audioToolBar.addAction(actPreview)

        self.actStopPreview = QtWidgets.QAction("Stop", self)
        self.actStopPreview.setObjectName("actStopPreview")  # Set object name
        self.actStopPreview.setToolTip(
            "Stop audio playback or cancel active operation."
        )
        self.actStopPreview.triggered.connect(self.stopPreview)
        self.audioToolBar.addAction(self.actStopPreview)

        # ... (Add other audio toolbar actions: Waveform, WaveformPlayer, Auto Tag, Edit Tags) ...
        actWaveform = QtWidgets.QAction("Waveform", self)
        actWaveform.setToolTip("View the waveform of the selected audio file.")
        actWaveform.triggered.connect(self.waveformPreview)
        self.audioToolBar.addAction(actWaveform)

        actWaveformPlayer = QtWidgets.QAction("Waveform Player", self)
        actWaveformPlayer.setToolTip("Launch waveform player with integrated playback.")
        actWaveformPlayer.triggered.connect(self.launchWaveformPlayer)
        self.audioToolBar.addAction(actWaveformPlayer)

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

        self.actAnalyzeLibrary = QtWidgets.QAction("Analyze Library", self)
        self.actAnalyzeLibrary.setObjectName("actAnalyzeLibrary")
        self.actAnalyzeLibrary.setToolTip(
            "Perform advanced audio analysis on the library."
        )
        self.actAnalyzeLibrary.triggered.connect(self.runAdvancedAnalysis)
        self.audioToolBar.addAction(self.actAnalyzeLibrary)

        # --- Add View Features Action ---
        self.actViewFeatures = QtWidgets.QAction("View Features", self)
        self.actViewFeatures.setObjectName("actViewFeatures")
        self.actViewFeatures.setToolTip("View detailed audio features for the selected file.")
        self.actViewFeatures.triggered.connect(self.viewSelectedFileFeatures)
        self.audioToolBar.addAction(self.actViewFeatures)
        # --- End View Features Action ---

        # ... (Add Recommend, Send to Cubase actions) ...
        self.actRecommend = QtWidgets.QAction("Recommend", self)
        self.actRecommend.setObjectName("actRecommend")
        self.actRecommend.setToolTip("Recommend similar samples based on BPM or tags.")
        self.actRecommend.triggered.connect(self.recommendSimilarSamples)
        self.audioToolBar.addAction(self.actRecommend)

        actSendToCubase = QtWidgets.QAction("Send to Cubase", self)
        actSendToCubase.setToolTip("Send selected file(s) to the Cubase folder.")
        actSendToCubase.triggered.connect(self.sendToCubase)
        self.audioToolBar.addAction(actSendToCubase)

        # --- Layout Setup ---
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        left_panel = QtWidgets.QWidget(self)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(10)

        # --- Filter Controls ---
        # Filename Filter
        lblFilter = QtWidgets.QLabel("Filter by Name:", self)
        self.txtFilter = QtWidgets.QLineEdit(self)
        self.txtFilter.setPlaceholderText("Type to filter files...")
        left_layout.addWidget(lblFilter)
        left_layout.addWidget(self.txtFilter)

        # Key Filter (New)
        lblKeyFilter = QtWidgets.QLabel("Filter by Key:", self)
        self.comboKeyFilter = QtWidgets.QComboBox(self)
        keys = [
            "Any",
            "C",
            "Cm",
            "C#",
            "C#m",
            "Db",
            "Dbm",
            "D",
            "Dm",
            "D#",
            "D#m",
            "Eb",
            "Ebm",
            "E",
            "Em",
            "F",
            "Fm",
            "F#",
            "F#m",
            "Gb",
            "Gbm",
            "G",
            "Gm",
            "G#",
            "G#m",
            "Ab",
            "Abm",
            "A",
            "Am",
            "A#",
            "A#m",
            "Bb",
            "Bbm",
            "B",
            "Bm",
            "N/A",
        ]
        self.comboKeyFilter.addItems(keys)
        left_layout.addWidget(lblKeyFilter)
        left_layout.addWidget(self.comboKeyFilter)

        # BPM Filter (New)
        lblBpmFilter = QtWidgets.QLabel("Filter by BPM Range:", self)
        bpm_layout = QtWidgets.QHBoxLayout()
        self.spinBpmMin = QtWidgets.QSpinBox(self)
        self.spinBpmMin.setRange(0, 500)
        self.spinBpmMin.setSuffix(" Min")
        self.spinBpmMin.setSpecialValueText("Any Min")
        self.spinBpmMax = QtWidgets.QSpinBox(self)
        self.spinBpmMax.setRange(0, 500)
        self.spinBpmMax.setSuffix(" Max")
        self.spinBpmMax.setSpecialValueText("Any Max")
        bpm_layout.addWidget(self.spinBpmMin)
        bpm_layout.addWidget(self.spinBpmMax)
        left_layout.addWidget(lblBpmFilter)
        left_layout.addLayout(bpm_layout)

        # Tag Text Filter (New)
        lblTagTextFilter = QtWidgets.QLabel("Filter by Tag Text:", self)
        self.txtTagTextFilter = QtWidgets.QLineEdit(self)
        self.txtTagTextFilter.setPlaceholderText("e.g., KICK, BRIGHT, LOOP...")
        left_layout.addWidget(lblTagTextFilter)
        left_layout.addWidget(self.txtTagTextFilter)

        # Separator
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setFrameShadow(QtWidgets.QFrame.Sunken)
        left_layout.addWidget(line)

        self.chkOnlyUnused = QtWidgets.QCheckBox("Show Only Unused Samples", self)
        self.chkOnlyUnused.setChecked(False)
        left_layout.addWidget(self.chkOnlyUnused)

        sizeUnitLayout = QtWidgets.QHBoxLayout()
        lblSizeUnit = QtWidgets.QLabel("Size Unit:", self)
        self.comboSizeUnit = QtWidgets.QComboBox(self)
        self.comboSizeUnit.addItems(["KB", "MB", "GB"])
        sizeUnitLayout.addWidget(lblSizeUnit)
        sizeUnitLayout.addWidget(self.comboSizeUnit)
        left_layout.addLayout(sizeUnitLayout)

        self.chkRecycleBin = QtWidgets.QCheckBox("Use Recycle Bin (on Delete)", self)
        self.chkRecycleBin.setChecked(True)
        left_layout.addWidget(self.chkRecycleBin)
        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # --- Right Panel (Table View) ---
        right_panel = QtWidgets.QWidget(self)
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(5)

        # Create models here
        self.model = FileTableModel([], self.size_unit)
        self.proxyModel = FileFilterProxyModel(self)  # Use updated proxy model
        self.proxyModel.setSourceModel(self.model)

        self.tableView = QtWidgets.QTableView(self)
        self.tableView.setModel(self.proxyModel)
        self.tableView.setSortingEnabled(True)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        # Ensure selection changes re-evaluate action states (e.g. View Features button)
        self.tableView.selectionModel().selectionChanged.connect(
            lambda selected, deselected: self._update_ui_state()
        )
        self.tableView.verticalHeader().setVisible(False)
        self.tableView.horizontalHeader().setStretchLastSection(True)
        # self.tableView.resizeColumnsToContents() # Resize after data load?

        right_layout.addWidget(self.tableView)
        self.labelSummary = QtWidgets.QLabel("Scanned 0 files.", self)
        right_layout.addWidget(self.labelSummary)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        main_layout.addWidget(splitter)

        # --- Status Bar and Menu Bar ---
        self.setStatusBar(QtWidgets.QStatusBar(self))
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

        # --- Connect Filter UI Signals ---
        self.txtFilter.textChanged.connect(self._start_name_filter_timer)
        self.chkOnlyUnused.stateChanged.connect(self.on_unused_filter_changed)
        self.comboSizeUnit.currentIndexChanged.connect(self.on_size_unit_changed)
        self.comboKeyFilter.currentIndexChanged.connect(self.on_key_filter_changed)
        self.spinBpmMin.valueChanged.connect(self.on_bpm_filter_changed)
        self.spinBpmMax.valueChanged.connect(self.on_bpm_filter_changed)
        self.txtTagTextFilter.textChanged.connect(self._start_tag_text_filter_timer)

        # --- Connect Debounce Timers ---
        self.nameFilterTimer.timeout.connect(self.on_name_filter_apply)
        self.tagFilterTimer.timeout.connect(self.on_tag_text_filter_apply)

        # Initial UI state update
        self._update_ui_state()

    def _connect_controller_signals(self) -> None:
        """Connects signals from controller instances to MainWindow slots."""
        # Scan Controller
        self.scan_ctrl.started.connect(lambda: self.on_task_started("Scan"))
        self.scan_ctrl.progress.connect(
            self.on_scan_progress
        )  # Use specific progress slot
        self.scan_ctrl.finished.connect(self.onScanFinished)
        self.scan_ctrl.error.connect(self.on_task_error)
        self.scan_ctrl.stateChanged.connect(self.on_controller_state_changed)

        # Duplicates Controller
        self.dup_ctrl.started.connect(lambda: self.on_task_started("Duplicates"))
        self.dup_ctrl.progress.connect(
            self.on_duplicate_progress
        )  # Use specific progress slot
        self.dup_ctrl.finished.connect(self.onDuplicatesFound)
        self.dup_ctrl.error.connect(self.on_task_error)
        self.dup_ctrl.stateChanged.connect(self.on_controller_state_changed)

        # Analysis Controller
        self.anal_ctrl.started.connect(lambda: self.on_task_started("Analysis"))
        self.anal_ctrl.progress.connect(
            self.on_advanced_analysis_progress
        )  # Use specific progress slot
        self.anal_ctrl.finished.connect(self.onAdvancedAnalysisFinished)
        self.anal_ctrl.error.connect(self.on_task_error)
        self.anal_ctrl.stateChanged.connect(self.on_controller_state_changed)

    # --- Action Slots ---

    def selectFolder(self) -> None:
        """Handles the 'Select Folder' action, delegating to ScanController."""
        if self.scan_ctrl.state != ControllerState.Idle:
            logger.warning("ScanController is busy, cannot start new scan.")
            return

        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select Folder Containing Audio Samples",
            self.last_folder or os.path.expanduser("~"),
        )
        if folder:
            self.last_folder = folder
            logger.info(f"Starting scan for folder: {folder}")
            self.statusBar().showMessage(f"Starting scan for {folder}...")
            self.scan_ctrl.start_scan(folder)

    def findDuplicates(self) -> None:
        """Handles the 'Find Duplicates' action, delegating to DuplicatesController."""
        if self.dup_ctrl.state != ControllerState.Idle:
            logger.warning("DuplicatesController is busy.")
            return
        if not self.all_files_info:
            QMessageBox.information(
                self,
                "Find Duplicates",
                "No file information available. Please scan a folder first.",
            )
            return

        logger.info("Starting duplicate detection...")
        self.statusBar().showMessage("Finding duplicates...")
        self.dup_ctrl.start_detection(list(self.all_files_info))

    def runAdvancedAnalysis(self) -> None:
        """Handles the 'Analyze Library' action, delegating to AnalysisController."""
        if self.anal_ctrl.state != ControllerState.Idle:
            logger.warning("AnalysisController is busy.")
            return
        if not self.all_files_info:
            QMessageBox.information(
                self,
                "Analyze Library",
                "No file information available. Please scan a folder first.",
            )
            return

        logger.info("Starting advanced library analysis...")
        self.statusBar().showMessage("Running advanced analysis...")
        self.anal_ctrl.start_analysis(list(self.all_files_info))

    def stopPreview(self) -> None:
        """
        Stops audio playback and attempts to cancel active background controller task.
        """
        logger.info("Stop action triggered.")
        # Stop audio player
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.stop()
            logger.debug("Audio playback stopped.")

        # Cancel active controllers
        cancelled_task = False
        if self.scan_ctrl.state == ControllerState.Running:
            self.scan_ctrl.cancel()
            cancelled_task = True
        if self.dup_ctrl.state == ControllerState.Running:
            self.dup_ctrl.cancel()
            cancelled_task = True
        if self.anal_ctrl.state == ControllerState.Running:
            self.anal_ctrl.cancel()
            cancelled_task = True

        if cancelled_task:
            self.statusBar().showMessage(
                "Attempting to cancel background task...", 3000
            )
        else:
            self.statusBar().showMessage(
                "Stop requested (no background task running).", 3000
            )

    def openSelectedFileLocation(self) -> None:
        path = self.getSelectedFilePath()
        if path:
            open_file_location(path)
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")

    def deleteSelected(self) -> None:
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.information(
                self, "Delete Selected", "No files selected."
            )
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete {len(selection)} file(s)?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if confirm != QtWidgets.QMessageBox.Yes:
            return

        errors = []
        db_ids_to_delete_model = []  # Store source model row indices
        paths_to_delete_fs = []
        file_infos_to_remove_mem = []

        # Collect files to delete
        for index in selection:
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            if file_info and "path" in file_info:
                db_ids_to_delete_model.append(source_index.row())
                paths_to_delete_fs.append(file_info["path"])
                file_infos_to_remove_mem.append(
                    file_info
                )  # Reference for removal from self.all_files_info
            else:
                logger.warning(
                    f"Could not get file info for selected proxy row {index.row()}"
                )

        # Delete from filesystem and DB
        db = DatabaseManager.instance()
        for path in paths_to_delete_fs:
            try:
                if self.chkRecycleBin.isChecked():
                    send2trash(path)
                else:
                    os.remove(path)
                # Remove from DB only after successful FS deletion
                db.delete_file_record(path)
            except Exception as e:
                errors.append(f"Error deleting {path}: {str(e)}")
                # If FS delete failed, don't remove from memory/model later
                # Need to find the corresponding file_info to prevent its removal
                for info in list(
                    file_infos_to_remove_mem
                ):  # Iterate copy for safe removal
                    if info["path"] == path:
                        file_infos_to_remove_mem.remove(info)
                        # Find corresponding model index and remove from that list too? More complex.
                        # Simplest is just not removing from memory if FS delete failed.

        if errors:
            QtWidgets.QMessageBox.critical(self, "Deletion Errors", "\n".join(errors))
        else:
            QtWidgets.QMessageBox.information(
                self,
                "Delete Selected",
                f"{len(paths_to_delete_fs) - len(errors)} files deleted successfully.",
            )

        # Update in-memory list (self.all_files_info)
        # This is safer than deleting by index if errors occurred
        original_paths = {info["path"] for info in self.all_files_info}
        successfully_deleted_paths = set(paths_to_delete_fs) - {
            err.split(": ")[0].replace("Error deleting ", "") for err in errors
        }  # Extract paths from error messages
        self.all_files_info = [
            info
            for info in self.all_files_info
            if info["path"] not in successfully_deleted_paths
        ]

        # Update the model (more efficient than deleting rows one by one)
        self.model.updateData(self.all_files_info)
        self.updateSummaryLabel()  # Update summary after deletion

    def setCubaseFolder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Cubase Folder"
        )
        if folder:
            self.cubase_folder = folder
            self.saveSettings()  # Save immediately
            QtWidgets.QMessageBox.information(
                self, "Cubase Folder", f"Cubase folder set to: {folder}"
            )

    def previewSelected(self) -> None:
        path = self.getSelectedFilePath()
        if path:
            if path.lower().endswith(tuple(AUDIO_EXTENSIONS)):
                self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
                self.player.play()
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Preview", "Cannot preview non-audio file."
                )
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")

    # stopPreview implemented above

    def waveformPreview(self) -> None:
        path = self.getSelectedFilePath()
        if path and path.lower().endswith(tuple(AUDIO_EXTENSIONS)):
            dialog = WaveformDialog(path, parent=self)
            dialog.exec_()
        elif path:
            QtWidgets.QMessageBox.warning(
                self, "Waveform", "Cannot show waveform for non-audio file."
            )
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")

    def launchWaveformPlayer(self) -> None:
        path = self.getSelectedFilePath()
        if path and path.lower().endswith(tuple(AUDIO_EXTENSIONS)):
            player_widget = WaveformPlayerWidget(path, theme=self.theme, parent=self)
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("Waveform Player")
            layout = QtWidgets.QVBoxLayout(dialog)
            layout.addWidget(player_widget)
            dialog.exec_()
        elif path:
            QtWidgets.QMessageBox.warning(
                self, "Waveform Player", "Cannot play non-audio file."
            )
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")

    def autoTagFiles(self) -> None:
        """Applies auto-tagging (currently key from filename) to all loaded files."""
        if not self.all_files_info:
            QtWidgets.QMessageBox.information(
                self, "Auto Tag", "No files loaded to tag."
            )
            return

        logger.info("Starting auto-tagging...")
        # Apply tagging directly to the in-memory list
        updated_count = 0
        db = DatabaseManager.instance()
        files_to_save = []
        for file_info in self.all_files_info:
            original_key = file_info.get("key")
            # Apply auto-tagging logic (only key for now)
            file_info = AutoTagService.auto_tag(file_info)
            if file_info.get("key") != original_key:
                updated_count += 1
                files_to_save.append(file_info)  # Mark for DB save only if changed

        if updated_count > 0:
            logger.info(
                f"Auto-tagging updated key for {updated_count} files. Saving to DB."
            )
            # Save only changed records to DB
            db.save_file_records(files_to_save)
            # Update the model to reflect changes visually
            self.model.updateData(self.all_files_info)  # Full update to refresh view
            QtWidgets.QMessageBox.information(
                self,
                "Auto Tag",
                f"Auto-tagging updated keys for {updated_count} files.",
            )
        else:
            QtWidgets.QMessageBox.information(
                self, "Auto Tag", "Auto-tagging completed. No keys were changed."
            )
        logger.info("Auto-tagging finished.")

    def recommendSimilarSamples(self) -> None:
        """
        Finds and displays files similar to the selected file using the scaled
        similarity search in DatabaseManager.
        """
        logger.debug("Recommend action triggered.")
        selected_proxy_indexes = self.tableView.selectionModel().selectedRows()

        # 1. Validate Selection
        if not selected_proxy_indexes:
            QMessageBox.information(self, "Recommend Similar", "Please select a reference file first.")
            return
        if len(selected_proxy_indexes) > 1:
            QMessageBox.information(self, "Recommend Similar", "Please select only one reference file.")
            return

        # 2. Get Reference File Info and ID
        proxy_index = selected_proxy_indexes[0]
        source_index = self.proxyModel.mapToSource(proxy_index)
        if not source_index.isValid():
            logger.error("Cannot get recommendations: Invalid source index from proxy.")
            QMessageBox.warning(self, "Recommend Similar", "Could not identify the selected file.")
            return

        file_info = self.model.getFileAt(source_index.row())
        if not file_info:
            logger.error(f"Cannot get recommendations: No file info found for source row {source_index.row()}")
            QMessageBox.warning(self, "Recommend Similar", "Could not retrieve data for the selected file.")
            return

        reference_id = file_info.get("db_id")
        reference_path = file_info.get("path", "Unknown File") # For dialog title

        if reference_id is None:
            logger.error(f"Cannot get recommendations: File '{reference_path}' does not have a database ID.")
            QMessageBox.critical(self, "Recommend Similar", "Selected file is missing a database ID.")
            return

        # 3. Call Backend Similarity Search
        num_results_to_fetch = 20 # Fetch slightly more, display maybe 15? Or just fetch desired N.
        logger.info(f"Finding files similar to ID {reference_id} ('{os.path.basename(reference_path)}').")
        self.statusBar().showMessage(f"Finding files similar to {os.path.basename(reference_path)}...")
        try:
            # Ensure stats are loaded/calculated (find_similar_files handles this internally now)
            # db_manager.get_feature_statistics() # No longer needed to call explicitly here

            db_manager = DatabaseManager.instance()
            similar_files = db_manager.find_similar_files(
                reference_file_id=reference_id,
                num_results=num_results_to_fetch
            )
        except Exception as e:
            logger.error(f"An error occurred during similarity search for ID {reference_id}: {e}", exc_info=True)
            QMessageBox.critical(self, "Recommendation Error", f"Failed to perform similarity search:\n{e}")
            self.statusBar().showMessage("Recommendation error.", 5000)
            return # Stop execution here

        self.statusBar().showMessage("Similarity search complete.", 5000)

        # 4. Display Results or No Results Message
        if not similar_files:
            logger.info(f"No similar files found for ID {reference_id}.")
            QMessageBox.information(self, "Recommend Similar", "No similar files found based on current analysis data.")
        else:
            logger.info(f"Found {len(similar_files)} similar files for ID {reference_id}. Displaying results.")
            # Create and show the results dialog
            dialog = SimilarityResultsDialog(similar_files, reference_path, parent=self)
            dialog.exec_() # Show as modal dialog

    @pyqtSlot()
    def viewSelectedFileFeatures(self) -> None:
        """
        Shows a dialog displaying detailed audio features for the selected file.
        """
        logger.debug("View Features action triggered.")
        selected_proxy_indexes = self.tableView.selectionModel().selectedRows()

        # 1. Validate Selection
        if not selected_proxy_indexes:
            QMessageBox.information(self, "View Features", "Please select a file first.")
            return
        if len(selected_proxy_indexes) > 1:
            QMessageBox.information(self, "View Features", "Please select only one file to view its features.")
            return

        # 2. Get File Info
        proxy_index = selected_proxy_indexes[0]
        source_index = self.proxyModel.mapToSource(proxy_index)
        if not source_index.isValid():
            logger.error("Cannot view features: Invalid source index from proxy.")
            QMessageBox.warning(self, "View Features", "Could not identify the selected file.")
            return

        file_info = self.model.getFileAt(source_index.row())
        if not file_info:
            logger.error(f"Cannot view features: No file info found for source row {source_index.row()}")
            QMessageBox.warning(self, "View Features", "Could not retrieve data for the selected file.")
            return

        # 3. Check if features likely exist (e.g., check one feature)
        # This assumes analysis has been run. A better check might be needed.
        if file_info.get('brightness') is None and file_info.get('loudness_rms') is None:
             reply = QMessageBox.question(self, "View Features",
                                          "Audio features may not have been calculated for this file yet "
                                          "(run 'Analyze Library').\n\nDo you want to view available data anyway?",
                                          QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
             if reply == QMessageBox.No:
                  return


        # 4. Create and Show Dialog
        logger.info(f"Displaying features for: {file_info.get('path')}")
        try:
            dialog = FeatureViewDialog(file_info, self)
            dialog.exec_() # Show modal dialog
        except Exception as e:
             logger.error(f"Failed to create or show FeatureViewDialog: {e}", exc_info=True)
             QMessageBox.critical(self, "Error", "Could not display the feature view dialog.")

    def sendToCubase(self) -> None:
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.warning(self, "Send to Cubase", "No file selected.")
            return
        if not self.cubase_folder or not os.path.isdir(self.cubase_folder):
            QtWidgets.QMessageBox.critical(
                self,
                "Send to Cubase",
                f"Cubase folder not set or invalid:\n{self.cubase_folder}",
            )
            return

        copied_count = 0
        errors = []
        for index in selection:
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            if file_info and "path" in file_info:
                try:
                    dest_path = os.path.join(
                        self.cubase_folder, os.path.basename(file_info["path"])
                    )
                    shutil.copy2(
                        file_info["path"], dest_path
                    )  # copy2 preserves metadata
                    copied_count += 1
                except Exception as e:
                    errors.append(
                        f"Failed to send {os.path.basename(file_info['path'])}: {e}"
                    )

        if errors:
            QtWidgets.QMessageBox.critical(
                self, "Send Error", f"Errors occurred:\n" + "\n".join(errors)
            )
        if copied_count > 0:
            QtWidgets.QMessageBox.information(
                self,
                "Send to Cubase",
                f"{copied_count} file(s) sent to Cubase successfully.",
            )

    # --- Filter Signal Handler Slots ---

    def _start_name_filter_timer(self) -> None:
        """Restarts the debounce timer for the name filter."""
        self.nameFilterTimer.start()

    def _start_tag_text_filter_timer(self) -> None:
        """Restarts the debounce timer for the tag text filter."""
        self.tagFilterTimer.start()

    @pyqtSlot()
    def on_name_filter_apply(self) -> None:
        """Applies the name filter text to the proxy model."""
        filter_text = self.txtFilter.text()
        logger.debug(f"Applying name filter: '{filter_text}'")
        self.proxyModel.set_filter_name(filter_text)

    @pyqtSlot()
    def on_tag_text_filter_apply(self) -> None:
        """Applies the tag text filter to the proxy model."""
        filter_text = self.txtTagTextFilter.text()
        logger.debug(f"Applying tag text filter: '{filter_text}'")
        self.proxyModel.set_filter_tag_text(filter_text)

    @pyqtSlot()
    def on_key_filter_changed(self) -> None:
        """Applies the selected key filter to the proxy model."""
        key_text = self.comboKeyFilter.currentText()
        logger.debug(f"Applying key filter: {key_text}")
        self.proxyModel.set_filter_key(key_text)

    @pyqtSlot()
    def on_bpm_filter_changed(self) -> None:
        """Applies the selected BPM range filter to the proxy model."""
        min_bpm = self.spinBpmMin.value()
        max_bpm = self.spinBpmMax.value()
        logger.debug(f"Applying BPM filter: Min={min_bpm}, Max={max_bpm}")
        self.proxyModel.set_filter_bpm_range(min_bpm, max_bpm)

    @pyqtSlot(int)
    def on_unused_filter_changed(self, state: int) -> None:
        """Applies the 'unused only' filter."""
        is_enabled = state == QtCore.Qt.Checked
        logger.debug(f"Setting unused filter enabled: {is_enabled}")
        self.proxyModel.set_filter_unused(is_enabled)

    @pyqtSlot()
    def on_size_unit_changed(self) -> None:
        """Updates the size unit used by the table model."""
        self.size_unit = self.comboSizeUnit.currentText()
        self.model.size_unit = self.size_unit
        self.model.layoutChanged.emit()
        logger.debug(f"Size unit changed to: {self.size_unit}")
        self.updateSummaryLabel()

    # --- Controller Signal Handler Slots ---

    @pyqtSlot(str)
    def on_task_started(self, task_name: str) -> None:
        """Generic slot called when any controller task starts."""
        logger.info(f"{task_name} task started.")
        self.progressBar.setValue(0)
        self.statusBar().showMessage(
            f"{task_name} started..."
        )  # Give specific feedback

    # Modify on_controller_state_changed to log WHICH controller changed
    @pyqtSlot(object)
    def on_controller_state_changed(self, state: ControllerState) -> None:
        """Handles state changes from Scan, Duplicates, Analysis controllers."""
        sender_controller = self.sender() # Get the controller that emitted the signal
        controller_name = sender_controller.__class__.__name__ if sender_controller else "Unknown Controller"
        logger.debug(f"on_controller_state_changed received for {controller_name}: New State={state}") # Log sender and state
        self._update_ui_state()

    @pyqtSlot(QMediaPlayer.State)  # Connected to QMediaPlayer.stateChanged
    def on_player_state_changed(self, state: QMediaPlayer.State) -> None:
        """Handles state changes from the QMediaPlayer."""
        # Argument 'state' (QMediaPlayer.State) is available if needed
        logger.debug(f"Player state changed: {state}")
        self._update_ui_state()  # Call common UI update logic

    @pyqtSlot(str)
    def on_task_error(self, message: str) -> None:
        """Generic slot to display errors from controllers."""
        logger.error(f"Controller Error: {message}")
        QMessageBox.critical(self, "Error", message)
        # Also reset progress bar and potentially re-enable buttons via state change
        self.progressBar.setValue(0)
        self.statusBar().showMessage("An error occurred.", 5000)
        self._update_ui_state()  # NEW - Correct call to helper

    @pyqtSlot(int, int)
    def on_scan_progress(self, current: int, total: int) -> None:
        """Handles progress signal from ScanController."""
        if total > 0:
            percent = int((current / total) * 100)
            self.progressBar.setValue(percent)
            self.statusBar().showMessage(f"Scanning: {current}/{total}")
        else:
            self.progressBar.setValue(0)
            self.statusBar().showMessage(f"Scanning...")  # Initial message

    @pyqtSlot(int, int)
    def on_duplicate_progress(self, current: int, total: int) -> None:
        """Handles progress signal from DuplicatesController."""
        if total > 0:
            percent = int((current / total) * 100)
            self.progressBar.setValue(percent)
            self.statusBar().showMessage(f"Finding duplicates: {current}/{total}")
        else:
            self.progressBar.setValue(0)
            self.statusBar().showMessage(f"Finding duplicates...")

    @pyqtSlot(int, int)
    def on_advanced_analysis_progress(self, current: int, total: int) -> None:
        """Handles progress signal from AnalysisController."""
        if total > 0:
            percent = int((current / total) * 100)
            self.progressBar.setValue(percent)
            self.statusBar().showMessage(
                f"Advanced analysis: {current} of {total} files processed."
            )
        else:
            self.progressBar.setValue(0)
            self.statusBar().showMessage(f"Advanced analysis...")

    @pyqtSlot(list)
    def onScanFinished(self, files: List[Dict[str, Any]]) -> None:
        """Handles finished signal from ScanController."""
        logger.info(f"Scan finished signal received. Found {len(files)} entries.")
        self.progressBar.setValue(100)
        self.all_files_info = files
        self.model.updateData(self.all_files_info)
        self.updateSummaryLabel()

        self.statusBar().showMessage("Scan complete.", 5000)
        self.tableView.resizeColumnsToContents()
        self._update_ui_state()

    @pyqtSlot(list)
    def onDuplicatesFound(self, duplicate_groups: List[List[Dict[str, Any]]]) -> None:
        """Handles finished signal from DuplicatesController."""
        logger.info(f"Duplicate search finished. Found {len(duplicate_groups)} groups.")
        self.progressBar.setValue(100)
        # State is updated via stateChanged signal
        if duplicate_groups:
            dlg = DuplicateManagerDialog(
                duplicate_groups,
                size_unit=self.size_unit,
                use_recycle_bin=self.chkRecycleBin.isChecked(),
                parent=self,
            )
            dlg.exec_()
            # After deletion, data might be stale. Trigger a rescan of the last folder.
            # Check if last_folder is valid before rescanning
            if self.last_folder and os.path.isdir(self.last_folder):
                logger.info("Rescanning after duplicate deletion...")
                # Ensure scan controller is idle before starting
                if self.scan_ctrl.state == ControllerState.Idle:
                    self.scan_ctrl.start_scan(self.last_folder)
                else:
                    logger.warning(
                        "Cannot rescan after duplicates, scan controller is busy."
                    )
                    QMessageBox.information(
                        self,
                        "Rescan Needed",
                        "Duplicate deletion complete. Please rescan the folder manually to update the list.",
                    )
            else:
                # If no valid last folder, just update summary based on potentially reduced all_files_info
                QMessageBox.information(
                    self,
                    "Rescan Recommended",
                    "Duplicate deletion complete. Please rescan the folder manually to update the list.",
                )

        else:
            QMessageBox.information(
                self, "Find Duplicates", "No duplicate files found."
            )

        self.statusBar().showMessage("Duplicate search complete.", 5000)

    @pyqtSlot(list)
    def onAdvancedAnalysisFinished(self, updated_files: List[Dict[str, Any]]) -> None:
        """Handles finished signal from AnalysisController."""
        logger.info("Advanced analysis finished signal received.")
        # --- Update UI based on analysis results ---
        self.progressBar.setValue(100)
        self.all_files_info = updated_files
        self.model.updateData(self.all_files_info)
        self.updateSummaryLabel()
        # --- End UI Update ---
        self.statusBar().showMessage("Analysis complete. Starting statistics update...")
        # Check flag AND worker state before starting new one
        if self._is_calculating_stats:
             logger.warning("Statistics calculation flag is already set. Skipping new trigger.")
             # If the flag is set but the worker somehow died, reset the flag and UI state
             if self.stats_worker is None or not self.stats_worker.isRunning():
                  logger.warning("Resetting stale statistics calculation flag.")
                  self._is_calculating_stats = False
                  self._update_ui_state()
             return
        # Also check worker just in case flag/worker state mismatch
        if self.stats_worker and self.stats_worker.isRunning():
             logger.warning("StatsWorker object exists and is running. Skipping new trigger.")
             return
        logger.info("Creating and starting StatsWorker thread for statistics refresh.")

        self.stats_worker = StatsWorker(self)
        # Prevent double‐triggering
        if self._is_calculating_stats or (self.stats_worker and self.stats_worker.isRunning()):
            return
        
        # 1. Set the flag
        self._is_calculating_stats = True
        logger.debug("_is_calculating_stats set to True.")
        # 2. Update UI so recommendation button immediately disables
        self._update_ui_state()

        # 3. Create and connect worker
        self.stats_worker = StatsWorker(self)
        self.stats_worker.finished.connect(self.onStatsWorkerFinished)

        # 4. Start it
        self.stats_worker.start()


    def updateSummaryLabel(self) -> None:
        """Updates the summary label at the bottom."""
        count = len(self.all_files_info)
        if count == 0:
            self.labelSummary.setText("No files loaded.")
            return
        try:
            # Ensure 'size' key exists and is numeric
            total_size = sum(
                f.get("size", 0)
                for f in self.all_files_info
                if isinstance(f.get("size"), (int, float))
            )
            converted_size = bytes_to_unit(total_size, self.size_unit)
            self.labelSummary.setText(
                f"{count} files ({self.proxyModel.rowCount()} visible). "
                f"Total size: {converted_size:.2f} {self.size_unit}."
            )
        except Exception as e:
            logger.error(f"Error calculating summary: {e}")
            self.labelSummary.setText(f"{count} files.")

    def getSelectedFilePath(self) -> Optional[str]:
        """Gets the file path of the first selected row."""
        # Use proxy model indices
        selected_proxy_indexes = self.tableView.selectionModel().selectedRows()
        if selected_proxy_indexes:
            proxy_index = selected_proxy_indexes[0]
            # Map proxy index to source model index
            source_index = self.proxyModel.mapToSource(proxy_index)
            # Get data from source model
            if source_index.isValid():
                file_info = self.model.getFileAt(source_index.row())
                if file_info and "path" in file_info:
                    return file_info["path"]
                else:
                    logger.warning(
                        f"Could not get file info for source row {source_index.row()}"
                    )
            else:
                logger.warning(
                    f"Invalid source index mapped from proxy row {proxy_index.row()}"
                )

        return None

    def editTagsForSelectedFile(self) -> None:
        """Opens the tag editor for the selected file."""
        selected_proxy_indexes = self.tableView.selectionModel().selectedRows()
        if not selected_proxy_indexes:
            QtWidgets.QMessageBox.information(
                self, "No Selection", "Please select a file to edit tags."
            )
            return
        # Ensure only one row is selected for editing
        if len(selected_proxy_indexes) > 1:
            QtWidgets.QMessageBox.information(
                self, "Multiple Selection", "Please select only one file to edit tags."
            )
            return

        proxy_index = selected_proxy_indexes[0]
        source_index = self.proxyModel.mapToSource(proxy_index)
        if not source_index.isValid():
            logger.error("Cannot edit tags: Invalid source index.")
            return

        file_info = self.model.getFileAt(source_index.row())
        if not file_info:
            logger.error(
                f"Cannot edit tags: No file info found for row {source_index.row()}"
            )
            return

        current_tags = file_info.get("tags", {})
        # Ensure current_tags is a dict for the editor
        if not isinstance(current_tags, dict):
            logger.warning(
                f"Tags for {file_info.get('path')} are not a dict, attempting conversion."
            )
            current_tags = (
                {"general": current_tags} if isinstance(current_tags, list) else {}
            )

        dialog = MultiDimTagEditorDialog(
            current_tags, parent=self
        )  # Pass copy? No, editor makes its own copy
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            updated_tags = dialog.get_tags()
            # Check if tags actually changed before saving/updating
            if updated_tags != file_info.get("tags"):
                logger.info(f"Tags updated for {file_info.get('path')}")
                file_info["tags"] = updated_tags
                # Update the specific cell in the model for visual feedback
                tags_col_index = FileTableModel.COLUMN_HEADERS.index("Tags")
                model_index_for_tags = self.model.index(
                    source_index.row(), tags_col_index
                )
                self.model.dataChanged.emit(
                    model_index_for_tags, model_index_for_tags, [QtCore.Qt.DisplayRole]
                )
                # Save the entire record to the database
                try:
                    DatabaseManager.instance().save_file_record(file_info)
                except Exception as e:
                    logger.error(
                        f"Failed to save updated tags to DB for {file_info.get('path')}: {e}"
                    )
                    QMessageBox.critical(
                        self, "Database Error", "Failed to save updated tags."
                    )
            else:
                logger.info("Tag editing cancelled or no changes made.")

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
        self.comboSizeUnit.setCurrentText(self.size_unit)  # Set after combo created
        recycle_bin = settings.value("useRecycleBin", "true")
        self.chkRecycleBin.setChecked(recycle_bin.lower() == "true")
        self.cubase_folder = settings.value("cubaseFolder", "")
        theme_setting = settings.value("theme", "light")
        self.setTheme(theme_setting, save=False)  # Apply theme after UI init

    def saveSettings(self) -> None:
        settings = QtCore.QSettings("MMSoftware", "MusiciansOrganizer")
        settings.setValue("windowGeometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        settings.setValue("lastFolder", self.last_folder)
        settings.setValue("sizeUnit", self.size_unit)
        settings.setValue(
            "useRecycleBin", "true" if self.chkRecycleBin.isChecked() else "false"
        )
        settings.setValue("cubaseFolder", self.cubase_folder)
        settings.setValue("theme", self.theme)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        # Optional: Check if any controllers are busy and warn user?
        is_busy = (
            self.scan_ctrl.state != ControllerState.Idle
            or self.dup_ctrl.state != ControllerState.Idle
            or self.anal_ctrl.state != ControllerState.Idle
        )
        if is_busy:
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "A background task is still running. Are you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                event.ignore()
                return
            else:
                # Try to cancel tasks before closing
                self.stopPreview()  # Attempt cancellation

        self.saveSettings()
        logger.info("Exiting application.")
        # Explicitly delete controllers to potentially help with thread cleanup? Usually parent handles it.
        # del self.scan_ctrl
        # del self.dup_ctrl
        # del self.anal_ctrl
        event.accept()

    # --- UI State Update Logic ---
    def _update_ui_state(self) -> None:
        """Helper method to update UI element enabled/disabled states."""
        logger.debug("--- _update_ui_state ENTERED ---") # Log entry clearly
        # Log controller states explicitly *before* calculating busy state
        scan_state = self.scan_ctrl.state
        dup_state = self.dup_ctrl.state
        anal_state = self.anal_ctrl.state
        logger.debug(f"Current Controller States: Scan={scan_state}, Dup={dup_state}, Anal={anal_state}")
        logger.debug(f"Current Stats Flag: _is_calculating_stats={self._is_calculating_stats}") # Log flag state
        is_scan_busy = self.scan_ctrl.state != ControllerState.Idle
        is_dup_busy  = self.dup_ctrl.state  != ControllerState.Idle
        is_anal_busy = self.anal_ctrl.state != ControllerState.Idle
        # STATS‐LEVEL BUSY: only blocks recommendation
        is_stats_busy = self._is_calculating_stats

        # CONTROLLER‐LEVEL BUSY: blocks most UI
        is_controller_busy = is_scan_busy or is_dup_busy or is_anal_busy


        # Determine overall busy state
        is_controller_busy = is_scan_busy or is_dup_busy or is_anal_busy
        is_stats_busy      = self._is_calculating_stats

        # Log file info count (useful for checking 'can_operate_on_data')
        file_count = len(self.all_files_info) if self.all_files_info else 0
        logger.debug(f"File count for UI state checks: {file_count}")

        # Check player state and selection state
        is_player_active = self.player.state() == QMediaPlayer.PlayingState
        is_selection = self.tableView.selectionModel().hasSelection()
        is_single_selection = len(self.tableView.selectionModel().selectedRows()) == 1

        # --- Define conditions for enabling actions ---
        # only controller busy blocks these:
        can_operate_on_data          = (not is_controller_busy) and bool(self.all_files_info)
        can_operate_on_selection     = (not is_controller_busy) and is_selection
        can_operate_on_single_select = (not is_controller_busy) and is_single_selection

        # --- Get Action References ---
        # (Ensure these getattr/findChild calls correctly find your actions)
        select_folder_action = getattr(self, "actSelectFolder", None)
        find_duplicates_action = getattr(self, "actFindDuplicates", None)
        analyze_library_action = getattr(self, "actAnalyzeLibrary", None)
        stop_action = getattr(self, "actStopPreview", None)
        recommend_action = getattr(self, "actRecommend", self.findChild(QtWidgets.QAction, "Recommend"))
        view_features_action = getattr(self, "actViewFeatures", None)
        delete_action = self.findChild(QtWidgets.QAction, "actDeleteSelected") # Adjust name if needed
        edit_tags_action = self.findChild(QtWidgets.QAction, "actEditTags") # Adjust name if needed
        preview_action = self.findChild(QtWidgets.QAction, "actPreview") # Adjust name if needed
        send_cubase_action = self.findChild(QtWidgets.QAction, "actSendToCubase") # Adjust name if needed
        # Add others like actWaveform, actWaveformPlayer if needed

        # --- Set Enabled States ---
        select_folder_action.setEnabled(not is_controller_busy)
        find_duplicates_action.setEnabled(not is_controller_busy and bool(self.all_files_info))
        analyze_library_action.setEnabled(not is_controller_busy and bool(self.all_files_info))

        if delete_action: delete_action.setEnabled(can_operate_on_selection)
        if preview_action: preview_action.setEnabled(can_operate_on_selection)
        if send_cubase_action: send_cubase_action.setEnabled(can_operate_on_selection and bool(self.cubase_folder))
        if edit_tags_action: edit_tags_action.setEnabled(can_operate_on_single_selection)
        recommend_action.setEnabled(
            (not is_controller_busy)
            and (not is_stats_busy)
            and is_single_selection
            )

        # Handle View Features tooltip update (incorporate previous fix)
        if view_features_action:
            view_features_action.setEnabled(can_operate_on_single_select)
            tooltip = "View detailed audio features for the selected file."
            if is_single_selection:
                # Check if features exist for tooltip modification
                try: # Add try-except for safety during state update
                    selected_proxy_indexes = self.tableView.selectionModel().selectedRows()
                    if selected_proxy_indexes: # Check if selection still valid
                        proxy_index = selected_proxy_indexes[0]
                        source_index = self.proxyModel.mapToSource(proxy_index)
                        if source_index.isValid():
                            file_info = self.model.getFileAt(source_index.row())
                            if file_info and file_info.get('brightness') is None and \
                               file_info.get('loudness_rms') is None and file_info.get('mfcc1_mean') is None:
                                tooltip += "\n(Run 'Analyze Library' to calculate features)"
                except Exception as e:
                     logger.warning(f"Error checking feature existence for tooltip: {e}")
            view_features_action.setToolTip(tooltip)


        # Stop Button State (unchanged)
        is_task_cancellable = (
            self.scan_ctrl.state == ControllerState.Running
            or self.dup_ctrl.state == ControllerState.Running
            or self.anal_ctrl.state == ControllerState.Running
        )
        if stop_action:
            stop_action.setEnabled(is_task_cancellable or is_player_active)

        # --- Status Bar Update (refined logic from previous step) ---
        status = "Ready."
        timeout = 3000
        if is_scan_busy: status, timeout = "Scanning folder...", 0
        elif is_dup_busy: status, timeout = "Finding duplicates...", 0
        elif is_anal_busy: status, timeout = "Analyzing library...", 0
        elif is_stats_busy: status, timeout = "Updating feature statistics...", 0 # Uses the flag now
        elif is_player_active: status, timeout = "Playing preview...", 0

        current_message = self.statusBar().currentMessage()
        is_new_temporary = timeout > 0
        is_current_permanent = not any([is_scan_busy, is_dup_busy, is_anal_busy, is_stats_busy, is_player_active]) and current_message == "Ready." # Rough check for permanent state
        # Avoid replacing a permanent 'busy' message with temporary 'Ready.'
        if not (status == "Ready." and is_new_temporary and not is_current_permanent):
              # Only update if message is different or it's a temporary message
             if status != current_message or timeout > 0:
                 self.statusBar().showMessage(status, timeout)
        elif is_current_permanent and status == "Ready." and timeout > 0:
             # If already showing permanent 'Ready.', don't flash it temporarily
             pass

    # --- Theme and Help Methods ---
    def setTheme(self, theme: str, save: bool = True) -> None:
        self.theme = theme.lower()
        if self.theme == "dark":
            self.applyDarkThemeStylesheet()
        else:
            self.applyLightThemeStylesheet()
        if save:
            self.saveSettings()

    # onStatsWorkerFinished (incorporating flag and previous robustness)
    @pyqtSlot(bool, str)
    def onStatsWorkerFinished(self, success: bool, message: str):
        """Handles the finished signal from the StatsWorker thread."""
        logger.info(f"StatsWorker finished signal received: Success={success}, Msg='{message}'")
        try:
            # Process results and show messages
            if success:
                self.statusBar().showMessage("Statistics update complete.", 5000)
            else:
                self.statusBar().showMessage("Statistics update failed.", 5000)
                QMessageBox.warning(self, "Statistics Update Error", message)
        except Exception as e:
            logger.error(f"Error processing StatsWorker result message: {e}", exc_info=True)
        finally:
            # This block executes reliably
            logger.debug("Executing finally block in onStatsWorkerFinished.")
            # --- CLEAR State Flag ---
            self._is_calculating_stats = False
            logger.debug("_is_calculating_stats set to False.")
            # --- END State Flag ---
            self.stats_worker = None # Clean up worker reference
            logger.debug("Set self.stats_worker = None.")
            # Update the UI state AFTER clearing the flag
            self._update_ui_state()
            logger.debug("Called _update_ui_state from onStatsWorkerFinished finally block.")

    def applyLightThemeStylesheet(self) -> None:
        # Stylesheet content from previous response
        self.setStyleSheet(
            """
            QMainWindow { background-color: #ffffff; color: #000000; }
            QToolBar { background-color: #f0f0f0; spacing: 6px; border-bottom: 1px solid #cccccc;}
            QToolBar QToolButton { background-color: transparent; color: #000000;
                 border: none; padding: 4px 10px; margin: 1px; }
            QToolBar QToolButton:hover { background-color: #e0e0e0; border-radius: 3px;}
            QToolBar QToolButton:pressed { background-color: #cccccc; }
            QToolBar::separator { height: 16px; background: #cccccc; width: 1px; margin: 4px 4px; }
            QLabel, QCheckBox, QRadioButton { color: #333333; font-size: 13px; }
            QLineEdit { background-color: #ffffff; border: 1px solid #cccccc;
                color: #333333; border-radius: 4px; padding: 4px; }
            QComboBox { background-color: #ffffff; border: 1px solid #cccccc;
                color: #333333; border-radius: 4px; padding: 4px; min-height: 1.5em;}
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-down-arrow-16.png); } /* Adjust path if needed */
            QSpinBox { background-color: #ffffff; border: 1px solid #cccccc; padding: 3px;
                color: #333333; border-radius: 4px;}
            QTableView { background-color: #ffffff; alternate-background-color: #f9f9f9;
                gridline-color: #dddddd; color: #000000; font-size: 13px; border: 1px solid #cccccc;}
            QHeaderView::section { background-color: #f0f0f0; color: #333333;
                border: none; border-bottom: 1px solid #cccccc; padding: 4px; }
            QProgressBar { background-color: #ffffff; border: 1px solid #cccccc; border-radius: 4px;
                text-align: center; color: #333333; }
            QProgressBar::chunk { background-color: #4caf50; border-radius: 3px;}
            QStatusBar { background-color: #f0f0f0; border-top: 1px solid #cccccc; color: #333333; }
            QMenuBar { background-color: #f0f0f0; color: #333333; border-bottom: 1px solid #cccccc;}
            QMenuBar::item { background: transparent; padding: 4px 12px; }
            QMenuBar::item:selected { background-color: #e0e0e0; }
            QMenu { background-color: #ffffff; border: 1px solid #cccccc; }
            QMenu::item { padding: 4px 20px; color: #333333; }
            QMenu::item:selected { background-color: #e0e0e0; }
            QSplitter::handle { background-color: #f0f0f0; }
            QSplitter::handle:horizontal { width: 1px; }
            QSplitter::handle:vertical { height: 1px; }
        """
        )

    def applyDarkThemeStylesheet(self) -> None:
        # Stylesheet content from previous response
        self.setStyleSheet(
            """
            QMainWindow { background-color: #282c34; color: #abb2bf; }
            QToolBar { background-color: #21252b; spacing: 6px; border-bottom: 1px solid #3a3f4b;}
            QToolBar QToolButton { background-color: transparent; color: #abb2bf;
                 border: none; padding: 4px 10px; margin: 1px; }
            QToolBar QToolButton:hover { background-color: #3a3f4b; border-radius: 3px; }
            QToolBar QToolButton:pressed { background-color: #4b5263; }
            QToolBar::separator { height: 16px; background: #3a3f4b; width: 1px; margin: 4px 4px; }
            QLabel, QCheckBox, QRadioButton { color: #abb2bf; font-size: 13px; }
            QCheckBox::indicator { width: 13px; height: 13px; } /* Optional: Adjust checkbox size */
            QCheckBox::indicator:unchecked { border: 1px solid #5c6370; background-color: #3a3f4b; border-radius: 3px;}
            QCheckBox::indicator:checked { border: 1px solid #61afef; background-color: #61afef; image: url(:/qt-project.org/styles/commonstyle/images/checkbox-checked-16.png); } /* Adjust path/image */
            QLineEdit { background-color: #3a3f4b; border: 1px solid #4b5263;
                color: #abb2bf; border-radius: 4px; padding: 4px; }
            QComboBox { background-color: #3a3f4b; border: 1px solid #4b5263;
                color: #abb2bf; border-radius: 4px; padding: 4px; min-height: 1.5em;}
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-down-arrow-16.png); } /* Adjust path if needed */
            QComboBox QAbstractItemView { background-color: #3a3f4b; border: 1px solid #4b5263; selection-background-color: #61afef; color: #abb2bf; }
            QSpinBox { background-color: #3a3f4b; border: 1px solid #4b5263; padding: 3px;
                color: #abb2bf; border-radius: 4px;}
            QTableView { background-color: #282c34; alternate-background-color: #2c313a;
                gridline-color: #4b5263; color: #abb2bf; font-size: 13px; border: 1px solid #4b5263;}
            QHeaderView::section { background-color: #21252b; color: #61afef;
                 border: none; border-bottom: 1px solid #3a3f4b; padding: 4px; }
            QProgressBar { background-color: #3a3f4b; border: 1px solid #4b5263; border-radius: 4px;
                text-align: center; color: #ffffff; }
            QProgressBar::chunk { background-color: #98c379; border-radius: 3px;}
            QStatusBar { background-color: #21252b; border-top: 1px solid #3a3f4b; color: #abb2bf; }
            QMenuBar { background-color: #21252b; color: #abb2bf; border-bottom: 1px solid #3a3f4b;}
            QMenuBar::item { background: transparent; padding: 4px 12px; }
            QMenuBar::item:selected { background-color: #61afef; color: #21252b;}
            QMenu { background-color: #21252b; border: 1px solid #3a3f4b; }
            QMenu::item { padding: 4px 20px; color: #abb2bf; }
            QMenu::item:selected { background-color: #61afef; color: #21252b;}
            QSplitter::handle { background-color: #21252b; }
            QSplitter::handle:horizontal { width: 1px; }
            QSplitter::handle:vertical { height: 1px; }
        """
        )

    def showHelpDialog(self) -> None:
        help_text = (
            "Musicians Organizer\n\n"
            "1. Select Folder: Choose a directory with music samples.\n"
            "2. Filter: Use controls in the left panel (Name, Key, BPM, Tag Text) to filter.\n"
            "3. Edit Tags: Double-click 'Tags' cell or use 'Edit Tags' action.\n"
            "4. Duplicates: Use 'Find Duplicates' action.\n"
            "5. Preview Audio: Select file, use 'Preview' action.\n"
            "6. Stop: Use 'Stop' action to halt playback or background tasks.\n"
            "7. Analyze: Use 'Analyze Library' to compute advanced features.\n"
            "8. Delete: Use 'Delete Selected' action (uses Recycle Bin if checked).\n"
            # Add more details as features grow
        )
        QtWidgets.QMessageBox.information(self, "Usage Help", help_text)
