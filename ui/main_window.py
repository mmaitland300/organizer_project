# FILE: ui/main_window.py

import logging
import os
import shutil

# Import Enum if ControllerState is used (it is)
from enum import Enum  # Ensure this is imported
import time
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
from ui.dialogs.spectrogram_dialog import SpectrogramDialog
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

    def __init__(self, db_manager: DatabaseManager, parent=None): # Accept db_manager
        super().__init__(parent)
        self.db_manager = db_manager

    def run(self):
        """Performs the statistics calculation."""
        logger.info("StatsWorker thread run() method entered.")
        message = "Statistics updated successfully."
        success = False
        stats = None # Initialize stats variable

        try:
            # --- ADD specific try...except around the DB call ---
            try:
                logger.info("StatsWorker: Calling get_feature_statistics(refresh=True)...")
                # This is the potentially hanging/erroring call:
                logger.debug("StatsWorker: >>> Entering DB stats calculation call.")
                stats = self.db_manager.get_feature_statistics(refresh=True)
                logger.debug("StatsWorker: <<< Exited DB stats calculation call.")
                logger.info("StatsWorker: get_feature_statistics call completed.")
            except Exception as db_error:
                # Log the specific error from the DB call
                logger.error(f"StatsWorker: CRITICAL ERROR during get_feature_statistics call: {db_error}", exc_info=True)
                message = f"Error calling database for statistics: {db_error}"
                success = False
                stats = None # Ensure stats is None so subsequent check fails gracefully
            # --- END specific try...except ---

            # Check the result *after* the call attempt
            # This part only runs if the DB call didn't raise an exception caught above
            if stats is not None:
                 success = True # Only set success True if stats calculation *actually* succeeded
                 logger.info("StatsWorker: Statistics calculation successful.")
            # Only set error message if DB call didn't already set one
            elif not message.startswith("Error calling database"):
                 message = "Statistics calculation failed or returned no data."
                 logger.error(message)
                 success = False # Ensure success is False

        except Exception as e:
            # Catch any other unexpected errors in the worker's overall logic
            message = f"Unexpected error within StatsWorker run method: {e}"
            logger.error(message, exc_info=True)
            success = False
        finally:
            # This finally block MUST be reached now unless the thread hangs completely
            logger.info(f"StatsWorker thread run() finished. Emitting finished signal (success={success}).")
            # Emit the signal to trigger onStatsWorkerFinished in MainWindow
            self.finished.emit(success, message)
    # --- End modified run method ---

class MainWindow(QtWidgets.QMainWindow):
    """
    Main window for Musicians Organizer. Integrates controllers for background
    tasks and provides enhanced filtering capabilities.
    """

    # --- MODIFY __init__ ---
    def __init__(self, db_manager: DatabaseManager) -> None: # Accept db_manager
        super().__init__()
        self.db_manager = db_manager # Store the instance
        self.setWindowTitle("Musicians Organizer")
        self.resize(1000, 700)
        self.all_files_info: List[Dict[str, Any]] = []
        self.size_unit: str = "KB"
        self.last_folder: str = ""
        self.cubase_folder: str = ""
        self.theme: str = "light"  # Initialize theme attribute

        # --- Controllers ---
        self.scan_ctrl = ScanController(db_manager=self.db_manager, parent=self) # <<< Pass db_manager
        self.dup_ctrl = DuplicatesController(self)
        self.anal_ctrl = AnalysisController(db_manager=self.db_manager, parent=self) # <<< Pass db_manager
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
        """Creates and lays out the UI widgets, including new feature filters."""
        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Toolbars (Keep existing toolbar code as is) ---
        # File Management Toolbar
        self.fileToolBar = QtWidgets.QToolBar("File Management", self)
        self.fileToolBar.setObjectName("fileToolBar")
        self.fileToolBar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.fileToolBar)
        # ... (Add actions: actSelectFolder, actFindDuplicates, etc.) ...
        self.actSelectFolder = QtWidgets.QAction("Select Folder", self); self.actSelectFolder.setObjectName("actSelectFolder"); self.actSelectFolder.triggered.connect(self.selectFolder); self.fileToolBar.addAction(self.actSelectFolder)
        self.actFindDuplicates = QtWidgets.QAction("Find Duplicates", self); self.actFindDuplicates.setObjectName("actFindDuplicates"); self.actFindDuplicates.triggered.connect(self.findDuplicates); self.fileToolBar.addAction(self.actFindDuplicates)
        actOpenFolder = QtWidgets.QAction("Open Folder", self); actOpenFolder.triggered.connect(self.openSelectedFileLocation); self.fileToolBar.addAction(actOpenFolder)
        actDeleteSelected = QtWidgets.QAction("Delete Selected", self); actDeleteSelected.setObjectName("actDeleteSelected"); actDeleteSelected.triggered.connect(self.deleteSelected); self.fileToolBar.addAction(actDeleteSelected)
        actSetCubase = QtWidgets.QAction("Set Cubase Folder", self); actSetCubase.triggered.connect(self.setCubaseFolder); self.fileToolBar.addAction(actSetCubase)
        leftExpSpacer = QtWidgets.QWidget(self); leftExpSpacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred); self.fileToolBar.addWidget(leftExpSpacer)
        self.progressBar = QtWidgets.QProgressBar(self); self.progressBar.setValue(0); self.progressBar.setFixedWidth(200); progressAction = QtWidgets.QWidgetAction(self.fileToolBar); progressAction.setDefaultWidget(self.progressBar); self.fileToolBar.addAction(progressAction)
        rightExpSpacer = QtWidgets.QWidget(self); rightExpSpacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred); self.fileToolBar.addWidget(rightExpSpacer)

        # Audio Tools Toolbar
        self.audioToolBar = QtWidgets.QToolBar("Audio Tools", self)
        self.audioToolBar.setObjectName("audioToolBar")
        self.audioToolBar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.audioToolBar)
        # ... (Add actions: actPreview, actStopPreview, actWaveform, actWaveformPlayer, actAutoTag, actEditTags, actAnalyzeLibrary, actViewFeatures, actRecommend, actSendToCubase) ...
        actPreview = QtWidgets.QAction("Preview", self); actPreview.triggered.connect(self.previewSelected); self.audioToolBar.addAction(actPreview)
        self.actStopPreview = QtWidgets.QAction("Stop", self); self.actStopPreview.setObjectName("actStopPreview"); self.actStopPreview.triggered.connect(self.stopPreview); self.audioToolBar.addAction(self.actStopPreview)
        actWaveform = QtWidgets.QAction("Waveform", self); actWaveform.triggered.connect(self.waveformPreview); self.audioToolBar.addAction(actWaveform)
        # --- ADD Spectrogram Action ---
        actViewSpectrogram = QtWidgets.QAction("Spectrogram", self); actViewSpectrogram.setObjectName("actViewSpectrogram"); actViewSpectrogram.triggered.connect(self.viewSpectrogram); self.audioToolBar.addAction(actViewSpectrogram)
        actWaveformPlayer = QtWidgets.QAction("Waveform Player", self); actWaveformPlayer.triggered.connect(self.launchWaveformPlayer); self.audioToolBar.addAction(actWaveformPlayer)
        spacer2 = QtWidgets.QWidget(self); spacer2.setFixedWidth(15); self.audioToolBar.addWidget(spacer2)
        actAutoTag = QtWidgets.QAction("Auto Tag", self); actAutoTag.triggered.connect(self.autoTagFiles); self.audioToolBar.addAction(actAutoTag)
        actEditTags = QtWidgets.QAction("Edit Tags", self); actEditTags.setObjectName("actEditTags"); actEditTags.triggered.connect(self.editTagsForSelectedFile); self.audioToolBar.addAction(actEditTags)
        self.actAnalyzeLibrary = QtWidgets.QAction("Analyze Library", self); self.actAnalyzeLibrary.setObjectName("actAnalyzeLibrary"); self.actAnalyzeLibrary.triggered.connect(self.runAdvancedAnalysis); self.audioToolBar.addAction(self.actAnalyzeLibrary)
        self.actViewFeatures = QtWidgets.QAction("View Features", self); self.actViewFeatures.setObjectName("actViewFeatures"); self.actViewFeatures.triggered.connect(self.viewSelectedFileFeatures); self.audioToolBar.addAction(self.actViewFeatures)
        self.actRecommend = QtWidgets.QAction("Recommend", self); self.actRecommend.setObjectName("actRecommend"); self.actRecommend.triggered.connect(self.recommendSimilarSamples); self.audioToolBar.addAction(self.actRecommend)
        # Store reference if needed for _update_ui_state
        self.actViewSpectrogram = actViewSpectrogram # Optional: store reference
        actSendToCubase = QtWidgets.QAction("Send to Cubase", self); actSendToCubase.triggered.connect(self.sendToCubase); self.audioToolBar.addAction(actSendToCubase)


        # --- Layout Setup ---
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        left_panel = QtWidgets.QWidget(self)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(10) # Increase spacing slightly

        # --- Filter Controls ---
        filter_group_box = QtWidgets.QGroupBox("Filters") # Group filters
        filter_layout = QtWidgets.QVBoxLayout(filter_group_box)
        filter_layout.setSpacing(8)

        # Filename Filter
        lblFilter = QtWidgets.QLabel("Name Contains:", filter_group_box)
        self.txtFilter = QtWidgets.QLineEdit(filter_group_box)
        self.txtFilter.setPlaceholderText("E.g., kick AND tag:loop NOT name:perc...") # Updated hint
        filter_layout.addWidget(lblFilter)
        filter_layout.addWidget(self.txtFilter)

        # Key Filter
        lblKeyFilter = QtWidgets.QLabel("Key:", filter_group_box)
        self.comboKeyFilter = QtWidgets.QComboBox(filter_group_box)
        keys = ["Any", "C", "Cm", "C#", "C#m", "Db", "Dbm", "D", "Dm", "D#", "D#m", "Eb", "Ebm", "E", "Em", "F", "Fm", "F#", "F#m", "Gb", "Gbm", "G", "Gm", "G#", "G#m", "Ab", "Abm", "A", "Am", "A#", "A#m", "Bb", "Bbm", "B", "Bm", "N/A"]
        self.comboKeyFilter.addItems(keys)
        filter_layout.addWidget(lblKeyFilter)
        filter_layout.addWidget(self.comboKeyFilter)

        # BPM Filter
        lblBpmFilter = QtWidgets.QLabel("BPM Range:", filter_group_box)
        bpm_layout = QtWidgets.QHBoxLayout()
        self.spinBpmMin = QtWidgets.QSpinBox(filter_group_box)
        self.spinBpmMin.setRange(0, 500); self.spinBpmMin.setSuffix(" Min"); self.spinBpmMin.setSpecialValueText("Any")
        self.spinBpmMax = QtWidgets.QSpinBox(filter_group_box)
        self.spinBpmMax.setRange(0, 500); self.spinBpmMax.setSuffix(" Max"); self.spinBpmMax.setSpecialValueText("Any")
        # Default max BPM higher than min initially
        self.spinBpmMax.setValue(500) # Set initial max high
        bpm_layout.addWidget(self.spinBpmMin); bpm_layout.addWidget(self.spinBpmMax)
        filter_layout.addWidget(lblBpmFilter)
        filter_layout.addLayout(bpm_layout)

        # Tag Text Filter
        lblTagTextFilter = QtWidgets.QLabel("Tag Contains:", filter_group_box)
        self.txtTagTextFilter = QtWidgets.QLineEdit(filter_group_box)
        self.txtTagTextFilter.setPlaceholderText("e.g., KICK, BRIGHT, LOOP...")
        filter_layout.addWidget(lblTagTextFilter)
        filter_layout.addWidget(self.txtTagTextFilter)

        # --- Add NEW Feature Filters ---
        # Separator before new filters
        line_features = QtWidgets.QFrame(filter_group_box)
        line_features.setFrameShape(QtWidgets.QFrame.HLine); line_features.setFrameShadow(QtWidgets.QFrame.Sunken)
        filter_layout.addWidget(line_features)

        # LUFS Range Filter
        lblLufsFilter = QtWidgets.QLabel("LUFS Range:", filter_group_box)
        lufs_layout = QtWidgets.QHBoxLayout()
        self.lufs_min_spinbox = QtWidgets.QDoubleSpinBox(filter_group_box)
        self.lufs_min_spinbox.setRange(-70.0, 0.0) # Realistic LUFS range
        self.lufs_min_spinbox.setDecimals(1)
        self.lufs_min_spinbox.setSingleStep(0.5)
        self.lufs_min_spinbox.setSuffix(" Min")
        self.lufs_min_spinbox.setSpecialValueText("Any") # Use special value text
        self.lufs_min_spinbox.setValue(self.lufs_min_spinbox.minimum()) # Default to min
        self.lufs_max_spinbox = QtWidgets.QDoubleSpinBox(filter_group_box)
        self.lufs_max_spinbox.setRange(-70.0, 0.0)
        self.lufs_max_spinbox.setDecimals(1)
        self.lufs_max_spinbox.setSingleStep(0.5)
        self.lufs_max_spinbox.setSuffix(" Max")
        self.lufs_max_spinbox.setSpecialValueText("Any") # Use special value text
        self.lufs_max_spinbox.setValue(self.lufs_max_spinbox.maximum()) # Default to max
        lufs_layout.addWidget(self.lufs_min_spinbox)
        lufs_layout.addWidget(self.lufs_max_spinbox)
        filter_layout.addWidget(lblLufsFilter)
        filter_layout.addLayout(lufs_layout)

        # Bit Depth Filter
        lblBitDepthFilter = QtWidgets.QLabel("Bit Depth:", filter_group_box)
        self.bit_depth_combobox = QtWidgets.QComboBox(filter_group_box)
        # Add common bit depths, ensure "Any" is first
        self.bit_depth_combobox.addItems(["Any", "16", "24", "32", "8"]) # Order as desired
        filter_layout.addWidget(lblBitDepthFilter)
        filter_layout.addWidget(self.bit_depth_combobox)

        # Pitch Hz Range Filter
        lblPitchFilter = QtWidgets.QLabel("Pitch Range (Hz):", filter_group_box)
        pitch_layout = QtWidgets.QHBoxLayout()
        self.pitch_min_spinbox = QtWidgets.QDoubleSpinBox(filter_group_box)
        self.pitch_min_spinbox.setRange(0.0, 20000.0) # Wide range for pitch
        self.pitch_min_spinbox.setDecimals(1)
        self.pitch_min_spinbox.setSingleStep(10.0)
        self.pitch_min_spinbox.setSuffix(" Hz Min")
        self.pitch_min_spinbox.setSpecialValueText("Any")
        self.pitch_min_spinbox.setValue(self.pitch_min_spinbox.minimum())
        self.pitch_max_spinbox = QtWidgets.QDoubleSpinBox(filter_group_box)
        self.pitch_max_spinbox.setRange(0.0, 20000.0)
        self.pitch_max_spinbox.setDecimals(1)
        self.pitch_max_spinbox.setSingleStep(10.0)
        self.pitch_max_spinbox.setSuffix(" Hz Max")
        self.pitch_max_spinbox.setSpecialValueText("Any")
        self.pitch_max_spinbox.setValue(self.pitch_max_spinbox.maximum())
        pitch_layout.addWidget(self.pitch_min_spinbox)
        pitch_layout.addWidget(self.pitch_max_spinbox)
        filter_layout.addWidget(lblPitchFilter)
        filter_layout.addLayout(pitch_layout)

        # Attack Time Range Filter
        lblAttackFilter = QtWidgets.QLabel("Attack Time Range (ms):", filter_group_box)
        attack_layout = QtWidgets.QHBoxLayout()
        self.attack_min_spinbox = QtWidgets.QDoubleSpinBox(filter_group_box)
        self.attack_min_spinbox.setRange(0.0, 10000.0) # e.g., 0 to 10 seconds in ms
        self.attack_min_spinbox.setDecimals(1)
        self.attack_min_spinbox.setSingleStep(1.0)
        self.attack_min_spinbox.setSuffix(" ms Min")
        self.attack_min_spinbox.setSpecialValueText("Any")
        self.attack_min_spinbox.setValue(self.attack_min_spinbox.minimum())
        self.attack_max_spinbox = QtWidgets.QDoubleSpinBox(filter_group_box)
        self.attack_max_spinbox.setRange(0.0, 10000.0)
        self.attack_max_spinbox.setDecimals(1)
        self.attack_max_spinbox.setSingleStep(1.0)
        self.attack_max_spinbox.setSuffix(" ms Max")
        self.attack_max_spinbox.setSpecialValueText("Any")
        self.attack_max_spinbox.setValue(self.attack_max_spinbox.maximum())
        attack_layout.addWidget(self.attack_min_spinbox)
        attack_layout.addWidget(self.attack_max_spinbox)
        filter_layout.addWidget(lblAttackFilter)
        filter_layout.addLayout(attack_layout)

        # Add the filter group box to the main left layout
        left_layout.addWidget(filter_group_box)

        # --- Other Left Panel Controls ---
        other_controls_group_box = QtWidgets.QGroupBox("Options") # Group options
        other_controls_layout = QtWidgets.QVBoxLayout(other_controls_group_box)

        self.chkOnlyUnused = QtWidgets.QCheckBox("Show Only Unused Samples", other_controls_group_box)
        self.chkOnlyUnused.setChecked(False)
        other_controls_layout.addWidget(self.chkOnlyUnused)

        sizeUnitLayout = QtWidgets.QHBoxLayout()
        lblSizeUnit = QtWidgets.QLabel("Size Unit:", other_controls_group_box)
        self.comboSizeUnit = QtWidgets.QComboBox(other_controls_group_box)
        self.comboSizeUnit.addItems(["KB", "MB", "GB"])
        sizeUnitLayout.addWidget(lblSizeUnit)
        sizeUnitLayout.addWidget(self.comboSizeUnit)
        other_controls_layout.addLayout(sizeUnitLayout)

        self.chkRecycleBin = QtWidgets.QCheckBox("Use Recycle Bin (on Delete)", other_controls_group_box)
        self.chkRecycleBin.setChecked(True)
        other_controls_layout.addWidget(self.chkRecycleBin)

        left_layout.addWidget(other_controls_group_box)
        left_layout.addStretch() # Pushes controls up

        splitter.addWidget(left_panel)

        # --- Right Panel (Table View - Keep existing setup) ---
        right_panel = QtWidgets.QWidget(self)
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(5)

        # Create models (use the corrected FileTableModel from previous step)
        self.model = FileTableModel([], self.db_manager, self.size_unit) # <<< Pass db_manager
        self.proxyModel = FileFilterProxyModel(self)
        self.proxyModel.setSourceModel(self.model)

        self.tableView = QtWidgets.QTableView(self)
        self.tableView.setModel(self.proxyModel)
        # ... (keep existing tableView settings: sorting, selection, headers, etc.) ...
        self.tableView.setSortingEnabled(True)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tableView.selectionModel().selectionChanged.connect(lambda: self._update_ui_state())
        self.tableView.verticalHeader().setVisible(False)
        self.tableView.horizontalHeader().setStretchLastSection(True) # Keep last column (Tags) stretching

        right_layout.addWidget(self.tableView)
        self.labelSummary = QtWidgets.QLabel("Scanned 0 files.", self)
        right_layout.addWidget(self.labelSummary)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1) # Adjust stretch factor if needed (Left panel)
        splitter.setStretchFactor(1, 3) # Adjust stretch factor if needed (Right panel)
        main_layout.addWidget(splitter)

        # --- Status Bar and Menu Bar (Keep existing setup) ---
        self.setStatusBar(QtWidgets.QStatusBar(self))
        menuBar = self.menuBar()
        helpMenu = menuBar.addMenu("Help"); helpAction = QtWidgets.QAction("Usage Help", self); helpAction.triggered.connect(self.showHelpDialog); helpMenu.addAction(helpAction)
        themeMenu = menuBar.addMenu("Theme"); actLight = QtWidgets.QAction("Light Mode", self); actLight.triggered.connect(lambda: self.setTheme("light", save=True)); themeMenu.addAction(actLight); actDark = QtWidgets.QAction("Dark Mode", self); actDark.triggered.connect(lambda: self.setTheme("dark", save=True)); themeMenu.addAction(actDark)


        # --- Connect Filter UI Signals (Consolidated at end of initUI) ---
        # Standard Filters
        self.txtFilter.textChanged.connect(self._start_name_filter_timer)
        self.chkOnlyUnused.stateChanged.connect(self.on_unused_filter_changed)
        self.comboSizeUnit.currentIndexChanged.connect(self.on_size_unit_changed)
        self.comboKeyFilter.activated[str].connect(self.proxyModel.set_filter_key) # Direct connect
        self.spinBpmMin.valueChanged.connect(self._update_bpm_filter) # Use helper slot
        self.spinBpmMax.valueChanged.connect(self._update_bpm_filter) # Use helper slot
        self.txtTagTextFilter.textChanged.connect(self._start_tag_text_filter_timer)

        # --- Connect NEW Feature Filter Signals ---
        self.lufs_min_spinbox.valueChanged[float].connect(self._update_lufs_filter)
        self.lufs_max_spinbox.valueChanged[float].connect(self._update_lufs_filter)
        self.bit_depth_combobox.activated[str].connect(self._update_bit_depth_filter)
        self.pitch_min_spinbox.valueChanged[float].connect(self._update_pitch_hz_filter)
        self.pitch_max_spinbox.valueChanged[float].connect(self._update_pitch_hz_filter)
        # Use valueChanged (emits float) for attack time spinboxes
        self.attack_min_spinbox.valueChanged.connect(self._update_attack_time_filter)
        self.attack_max_spinbox.valueChanged.connect(self._update_attack_time_filter)

        # --- Connect Debounce Timers ---
        # --- MODIFICATION: Ensure nameFilterTimer timeout connects to the correct slot ---
        # This slot now calls set_advanced_filter instead of set_filter_name
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
        )

        self.anal_ctrl.analysis_data_finished.connect(self.onAdvancedAnalysisFinished) # New signal name
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
        db = self.db_manager #  Use stored instance
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
    # --- ADD Slot for View Spectrogram Action ---
    @pyqtSlot()
    def viewSpectrogram(self) -> None:
        """Handles the 'View Spectrogram' action."""
        logger.debug("View Spectrogram action triggered.")
        path = self.getSelectedFilePath()

        if not path:
            QtWidgets.QMessageBox.information(self, "View Spectrogram", "No file selected.")
            return

        # Check if the file is likely an audio file based on extension
        if not path.lower().endswith(tuple(AUDIO_EXTENSIONS)):
            QtWidgets.QMessageBox.warning(self, "View Spectrogram", "Cannot show spectrogram for non-audio file.")
            return

        # Create and show the dialog
        logger.info(f"Showing spectrogram for: {path}")
        dialog = SpectrogramDialog(path, theme=self.theme, parent=self)
        dialog.exec_()

    def is_any_task_busy(self) -> bool:
        """Checks if any background controller or stats worker is active."""
        # Check controller states directly
        is_scan_busy = self.scan_ctrl.state != ControllerState.Idle
        is_dup_busy = self.dup_ctrl.state != ControllerState.Idle
        is_anal_busy = self.anal_ctrl.state != ControllerState.Idle
        # Check stats flag
        is_stats_busy = self._is_calculating_stats

        # Return True if any are busy
        return is_scan_busy or is_dup_busy or is_anal_busy or is_stats_busy

    def autoTagFiles(self) -> None:
        """Applies auto-tagging (currently key from filename) to all loaded files."""

        if self.is_any_task_busy(): # Assuming is_any_task_busy helper exists as defined before
             QMessageBox.warning(self, "Auto Tag", "Cannot tag files while another task is running.")
             return

        if not self.all_files_info:
            QtWidgets.QMessageBox.information(
                self, "Auto Tag", "No files loaded to tag."
            )
            return

        logger.info("Starting auto-tagging...")
        updated_count = 0
        db = self.db_manager # <<< Use stored instance
        files_to_save: List[Dict[str, Any]] = []
        for file_info in self.all_files_info:
            # Apply auto-tagging in-place and get a flag if anything changed
            modified = AutoTagService.auto_tag(file_info)
            if modified:
                updated_count += 1
                files_to_save.append(file_info)

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

            db_manager = self.db_manager # <<< Use stored instance
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

        # +++ START DEBUG LOGGING +++
        logger.debug("--- Retrieved file_info for FeatureViewDialog ---")
        # Log a few key standard and advanced features to check their presence/values
        log_features = ['path', 'bpm', 'brightness', 'loudness_rms', 'loudness_lufs', 'pitch_hz', 'attack_time', 'bit_depth']
        logged_data = {key: file_info.get(key) for key in log_features if key in file_info}
        logger.debug(f"Data subset: {logged_data}")
        # Optionally log all keys to see what's available:
        # logger.debug(f"All keys in file_info: {list(file_info.keys())}")
        # +++ END DEBUG LOGGING +++


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

        self.proxyModel.set_advanced_filter(filter_text) # Changed from set_filter_name


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
        logger.debug(f"State changed for {controller_name}: New State={state}")

        # Check if the controller is the AnalysisController and it just became Idle
        # after having been requested to cancel.
        if isinstance(sender_controller, AnalysisController) and state == ControllerState.Idle:
            if sender_controller.was_cancelled():
                logger.info(f"{controller_name} finished after cancellation. Resetting progress bar.")
                self.progressBar.setValue(0) # Reset progress bar to 0

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
        """
        Handles finished signal from AnalysisController.
        Ensures all file dictionaries have expected feature keys before updating the model.
        Updates the main model with results and triggers stats update ONLY IF
        the analysis task was NOT cancelled.
        """
        logger.info("Advanced analysis finished signal received.")
        # Import the master list of feature keys
        try:
            from config.settings import ALL_FEATURE_KEYS
        except ImportError:
            logger.error("Cannot import ALL_FEATURE_KEYS from settings. Unable to ensure data consistency.")
            # Handle error appropriately - maybe return or use a fallback
            QMessageBox.critical(self, "Configuration Error", "Could not load feature key definitions.")
            return


        # --- CRITICAL CHECK: Use the controller's cancellation flag ---
        if self.anal_ctrl.was_cancelled():
            logger.info("Analysis task was cancelled (flag detected). Skipping statistics update.")
            self.statusBar().showMessage("Analysis cancelled by user.", 5000)
            # Even if cancelled, try to ensure data consistency for partial results
            self.all_files_info = updated_files # Use the potentially partial results

            # --- Ensure Keys Exist (Apply even on cancel for consistency) ---
            logger.debug("Ensuring all feature keys exist in results after cancelled analysis...")
            for file_info in self.all_files_info:
                if isinstance(file_info, dict): # Check it's a dict
                    for key in ALL_FEATURE_KEYS:
                        if key not in file_info:
                            file_info[key] = None # Add missing keys with None
            logger.debug("Key consistency check complete for cancelled results.")
            # --- End Key Check ---

            self.model.updateData(self.all_files_info)
            self.updateSummaryLabel()
            self.progressBar.setValue(0)
            return

        # --- If NOT Cancelled, Proceed ---
        logger.info("Analysis completed successfully. Ensuring keys, updating model, triggering statistics.")
        self.progressBar.setValue(100)
        self.all_files_info = updated_files # Assign results

        # +++ START Ensure Keys Exist +++
        logger.debug("Ensuring all feature keys exist in successfully completed analysis results...")
        missing_keys_added_count = 0
        for file_info in self.all_files_info:
            if isinstance(file_info, dict): # Check it's a dict
                for key in ALL_FEATURE_KEYS:
                    if key not in file_info:
                        file_info[key] = None # Add missing keys with None
                        missing_keys_added_count += 1
            else:
                 logger.warning(f"Item in updated_files is not a dictionary: {file_info}")
        if missing_keys_added_count > 0:
             logger.info(f"Added {missing_keys_added_count} missing feature keys with None value for consistency.")
        logger.debug("Key consistency check complete.")
        # +++ END Ensure Keys Exist +++

        # 1) Update UI with the *consistent* analysis results
        self.model.updateData(self.all_files_info) # Update model AFTER ensuring keys
        self.updateSummaryLabel()
        self.statusBar().showMessage("Analysis complete. Refreshing feature statistics...", 0)
        logger.info("Main model updated after analysis and key check. Preparing stats worker.")

        # --- Start StatsWorker (rest of the code remains the same) ---
        if self._is_calculating_stats and (not self.stats_worker or not self.stats_worker.isRunning()):
            logger.warning("Stale stats flag detected before starting new worker; resetting.")
            self._is_calculating_stats = False

        if self._is_calculating_stats:
            logger.warning("Statistics calculation already in progress (_is_calculating_stats=True). Skipping new trigger.")
            self.statusBar().showMessage("Analysis complete. Statistics update already running.", 5000)
            self._update_ui_state()
            return
        if self.stats_worker and self.stats_worker.isRunning():
            logger.warning("StatsWorker instance is unexpectedly still running. Skipping new trigger.")
            self.statusBar().showMessage("Analysis complete. Statistics update already running.", 5000)
            self._update_ui_state()
            return

        logger.info("Creating and starting StatsWorker thread for statistics refresh.")
        self.stats_worker = StatsWorker(db_manager=self.db_manager, parent=self) # <<< Pass db_manager
        self.stats_worker.finished.connect(self.onStatsWorkerFinished)
        self._is_calculating_stats = True
        logger.debug("_is_calculating_stats set to True.")
        self._update_ui_state()
        self.stats_worker.start()
        logger.info("StatsWorker thread started.")



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
                    self.db_manager.save_file_record(file_info)
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
        """ Handles application close event. Attempts to cancel background tasks. """
        logger.info("Close event triggered.")
        # Check if any task is running
        is_busy = (
            self.scan_ctrl.state != ControllerState.Idle
            or self.dup_ctrl.state != ControllerState.Idle
            or self.anal_ctrl.state != ControllerState.Idle
            # Add self._is_calculating_stats if that should prevent closing
        )

        if is_busy:
            # Ask confirmation only if tasks are running
            reply = QMessageBox.question(
                self,
                "Confirm Exit",
                "A background task is running.\nExiting now will attempt to stop it.\n\nAre you sure you want to exit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                logger.info("Close event ignored by user.")
                event.ignore()
                return
            else:
                # If user confirms exit OR if no task was busy initially:
                logger.info("Attempting to cancel background tasks before closing...")
                # Request cancellation for all potentially running tasks
                if self.scan_ctrl.state != ControllerState.Idle: self.scan_ctrl.cancel()
                if self.dup_ctrl.state != ControllerState.Idle: self.dup_ctrl.cancel()
                if self.anal_ctrl.state != ControllerState.Idle: self.anal_ctrl.cancel()
                # *** REMOVED explicit wait() loop ***
                # Rely on controller/worker cleanup via signals and context managers
                logger.info("Cancellation requested for running tasks.")

        # Proceed with saving settings and accepting the close event
        self.saveSettings()
        logger.info("Accepting close event. Exiting application.")
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

        view_spectrogram_action = getattr(self, "actViewSpectrogram", None) # Get new action

        # --- Set Enabled States ---
        select_folder_action.setEnabled(not is_controller_busy)
        find_duplicates_action.setEnabled(not is_controller_busy and bool(self.all_files_info))
        analyze_library_action.setEnabled(not is_controller_busy and bool(self.all_files_info))

        if delete_action: delete_action.setEnabled(can_operate_on_selection)
        if preview_action: preview_action.setEnabled(can_operate_on_selection)
        if send_cubase_action: send_cubase_action.setEnabled(can_operate_on_selection and bool(self.cubase_folder))
        if edit_tags_action: edit_tags_action.setEnabled(can_operate_on_selection)
        recommend_action.setEnabled(
            (not is_controller_busy)
            and (not is_stats_busy)
            and is_single_selection
            )
        
        # Enable spectrogram view for single audio file selection when not busy
        if view_spectrogram_action: view_spectrogram_action.setEnabled(can_operate_on_single_select)

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

    # --- Helper Methods to Update NEW Feature Filters ---

    @pyqtSlot()
    def _update_lufs_filter(self) -> None:
        """
        Reads min/max LUFS spinboxes and updates the proxy model.
        Robustly handles 'Any' state by checking against min/max values.
        """
        if not hasattr(self, 'lufs_min_spinbox') or not hasattr(self, 'lufs_max_spinbox'):
             logger.warning("LUFS spinboxes not available for filter update.")
             return

        min_val = self.lufs_min_spinbox.value()
        max_val = self.lufs_max_spinbox.value()

        # Determine if filter boundary should be active (None means inactive/"Any")
        # Consider boundary inactive if value is AT the minimum or maximum
        min_lufs = None if min_val == self.lufs_min_spinbox.minimum() else min_val
        max_lufs = None if max_val == self.lufs_max_spinbox.maximum() else max_val

        # Basic validation: ensure min <= max if both are active
        if min_lufs is not None and max_lufs is not None and min_lufs > max_lufs:
            # If min > max, we could arguably disable the filter or sync values.
            # For simplicity, we pass them; the filter logic should handle empty result.
            logger.debug(f"Invalid LUFS range: Min ({min_lufs}) > Max ({max_lufs}). Filter likely yields no results.")

        self.proxyModel.set_filter_lufs_range(min_lufs, max_lufs)

    @pyqtSlot(str) # Connected to activated[str] signal
    def _update_bit_depth_filter(self, selected_text: str):
        """Reads the Bit Depth combobox and updates the proxy model."""
        if selected_text == "Any":
            bit_depth = None
        else:
            try:
                bit_depth = int(selected_text)
            except (ValueError, TypeError):
                logger.warning(f"Invalid bit depth selection: {selected_text}")
                bit_depth = None # Default to no filter if conversion fails

        self.proxyModel.set_filter_bit_depth(bit_depth)

    @pyqtSlot()
    def _update_pitch_hz_filter(self):
        """Reads min/max Pitch Hz spinboxes and updates the proxy model."""
        if not hasattr(self, 'pitch_min_spinbox') or not hasattr(self, 'pitch_max_spinbox'):
             logger.warning("Pitch Hz spinboxes not available for filter update.")
             return

        min_val = self.pitch_min_spinbox.value()
        max_val = self.pitch_max_spinbox.value()

        min_hz = None if self.pitch_min_spinbox.text() == self.pitch_min_spinbox.specialValueText() else min_val
        max_hz = None if self.pitch_max_spinbox.text() == self.pitch_max_spinbox.specialValueText() else max_val

        if min_hz is not None and max_hz is not None and min_hz > max_hz:
            logger.debug(f"Invalid Pitch Hz range: Min ({min_hz}) > Max ({max_hz}). Passing as is.")

        self.proxyModel.set_filter_pitch_hz_range(min_hz, max_hz)

    @pyqtSlot() # Connected to valueChanged signal
    def _update_attack_time_filter(self):
        """Reads min/max Attack Time (ms) spinboxes and updates the proxy model."""
        if not hasattr(self, 'attack_min_spinbox') or not hasattr(self, 'attack_max_spinbox'):
             logger.warning("Attack Time spinboxes not available for filter update.")
             return

        min_val_ms = self.attack_min_spinbox.value()
        max_val_ms = self.attack_max_spinbox.value()

        # Use special value text check for disabling filter boundary
        min_ms = None if self.attack_min_spinbox.text() == self.attack_min_spinbox.specialValueText() else min_val_ms
        max_ms = None if self.attack_max_spinbox.text() == self.attack_max_spinbox.specialValueText() else max_val_ms

        # Basic validation
        if min_ms is not None and max_ms is not None and min_ms > max_ms:
            logger.debug(f"Invalid Attack Time range: Min ({min_ms}ms) > Max ({max_ms}ms). Passing as is.")

        # Pass values in ms to the setter (it handles conversion to seconds)
        self.proxyModel.set_filter_attack_time_range(min_ms, max_ms)

    # --- Keep existing helper methods like _update_bpm_filter ---
    # Make sure _update_bpm_filter also uses specialValueText if you updated the spinboxes
    def _update_bpm_filter(self):
        """Reads min/max BPM spinboxes and updates the proxy model."""
        if hasattr(self, 'spinBpmMin') and hasattr(self, 'spinBpmMax'):
            min_val = self.spinBpmMin.value()
            max_val = self.spinBpmMax.value()
            min_bpm = None if min_val == self.spinBpmMin.minimum() else min_val
            max_bpm = None if max_val == self.spinBpmMax.maximum() else max_val

            if min_bpm is not None and max_bpm is not None and min_bpm > max_bpm:
                logger.debug(f"Invalid BPM range: Min ({min_bpm}) > Max ({max_bpm}). Passing as is.")

            self.proxyModel.set_filter_bpm_range(min_bpm, max_bpm)

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
            # Show appropriate status message based on success
            if success:
                self.statusBar().showMessage("Statistics update complete.", 5000)
                logger.info("Feature statistics successfully refreshed.")
            else:
                # Show error message from worker, don't show generic "failed" message
                self.statusBar().showMessage("Statistics update failed. See logs or dialog.", 5000)
                QMessageBox.warning(self, "Statistics Update Error", f"Failed to update statistics:\n{message}")
                logger.error(f"Statistics update failed: {message}")
        except Exception as e:
            logger.error(f"Error processing StatsWorker result message: {e}", exc_info=True)
        finally:
            # --- Crucial Cleanup ---
            logger.debug("Executing finally block in onStatsWorkerFinished.")
            # Clear the state flag *reliably*
            self._is_calculating_stats = False
            logger.debug("_is_calculating_stats set to False.")
            # Clean up worker reference
            self.stats_worker = None
            logger.debug("Set self.stats_worker = None.")
            # Update the UI state *after* clearing the flag
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
