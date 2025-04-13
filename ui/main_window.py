"""
MainWindow – the primary user interface for Musicians Organizer.

This module creates the main window and toolbars, and connects UI actions to service classes.
"""

import os
import shutil
import logging
from typing import List, Dict, Optional, Any

from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtCore import QUrl, pyqtSlot
from send2trash import send2trash

from models.file_model import FileTableModel, FileFilterProxyModel
from services.file_scanner import FileScannerService
from services.duplicate_finder import DuplicateFinderService
from services.auto_tagger import AutoTagService
from services.database_manager import DatabaseManager
from utils.helpers import bytes_to_unit, open_file_location
from config.settings import AUDIO_EXTENSIONS
from ui.dialogs.duplicate_manager_dialog import DuplicateManagerDialog
from ui.dialogs.waveform_dialog import WaveformDialog
from ui.dialogs.multi_dim_tag_editor_dialog import MultiDimTagEditorDialog
from ui.dialogs.waveform_player_widget import WaveformPlayerWidget

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class MainWindow(QtWidgets.QMainWindow):
    """
    Main window for Musicians Organizer.

    Provides file scanning, duplicate detection, audio preview, waveform visualization, and auto-tagging.
    """
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Musicians Organizer")
        self.resize(1000, 700)
        self.all_files_info: List[Dict[str, Any]] = []
        self.size_unit: str = "KB"
        self.last_folder: str = ""
        self.cubase_folder: str = ""
        self.scanner: Optional[FileScannerService] = None
        self.duplicateFinder: Optional[DuplicateFinderService] = None
        
        self.filterTimer = QtCore.QTimer(self)
        self.filterTimer.setSingleShot(True)
        self.filterTimer.timeout.connect(self.updateFilter)
        
        self.chkOnlyUnused = QtWidgets.QCheckBox("Show Only Unused Samples", self)
        self.chkOnlyUnused.setChecked(False)
        self.chkOnlyUnused.stateChanged.connect(self.onOnlyUnusedChanged)
        
        self.player = QMediaPlayer(self)
        self.initUI()
        self.loadSettings()
    
    def initUI(self) -> None:
        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # File Management Toolbar
        self.fileToolBar = QtWidgets.QToolBar("File Management", self)
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
        
        self.progressBar = QtWidgets.QProgressBar(self)
        self.progressBar.setValue(0)
        self.progressBar.setFixedWidth(200)
        progressAction = QtWidgets.QWidgetAction(self.fileToolBar)
        progressAction.setDefaultWidget(self.progressBar)
        self.fileToolBar.addAction(progressAction)
        
        rightExpSpacer = QtWidgets.QWidget(self)
        rightExpSpacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.fileToolBar.addWidget(rightExpSpacer)
        
        # Audio Tools Toolbar
        self.audioToolBar = QtWidgets.QToolBar("Audio Tools", self)
        self.audioToolBar.setObjectName("audioToolBar")
        self.audioToolBar.setMovable(False)
        self.addToolBar(QtCore.Qt.TopToolBarArea, self.audioToolBar)
        
        actPreview = QtWidgets.QAction("Preview", self)
        actPreview.setToolTip("Preview the selected audio file.")
        actPreview.triggered.connect(self.previewSelected)
        self.audioToolBar.addAction(actPreview)
        
        actStopPreview = QtWidgets.QAction("Stop", self)
        actStopPreview.setToolTip("Stop audio playback or cancel active operation.")
        actStopPreview.triggered.connect(self.stopPreview)
        self.audioToolBar.addAction(actStopPreview)
        
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
        
        actRecommend = QtWidgets.QAction("Recommend", self)
        actRecommend.setToolTip("Recommend similar samples based on BPM or tags.")
        actRecommend.triggered.connect(self.recommendSimilarSamples)
        self.audioToolBar.addAction(actRecommend)
        
        actSendToCubase = QtWidgets.QAction("Send to Cubase", self)
        actSendToCubase.setToolTip("Send selected file(s) to the Cubase folder.")
        actSendToCubase.triggered.connect(self.sendToCubase)
        self.audioToolBar.addAction(actSendToCubase)
        
        # Layout: Splitter for file list and filters
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        left_panel = QtWidgets.QWidget(self)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(10)
        
        lblFilter = QtWidgets.QLabel("Filter by Name:", self)
        self.txtFilter = QtWidgets.QLineEdit(self)
        self.txtFilter.setPlaceholderText("Type to filter files...")
        self.txtFilter.textChanged.connect(self.onFilterTextChanged)
        left_layout.addWidget(lblFilter)
        left_layout.addWidget(self.txtFilter)
        
        self.chkBPM = QtWidgets.QCheckBox("BPM Detection", self)
        self.chkBPM.setChecked(False)
        left_layout.addWidget(self.chkBPM)
        left_layout.addWidget(self.chkOnlyUnused)
        
        sizeUnitLayout = QtWidgets.QHBoxLayout()
        lblSizeUnit = QtWidgets.QLabel("Size Unit:", self)
        self.comboSizeUnit = QtWidgets.QComboBox(self)
        self.comboSizeUnit.addItems(["KB", "MB", "GB"])
        self.comboSizeUnit.currentIndexChanged.connect(self.onSizeUnitChanged)
        sizeUnitLayout.addWidget(lblSizeUnit)
        sizeUnitLayout.addWidget(self.comboSizeUnit)
        left_layout.addLayout(sizeUnitLayout)
        
        self.chkRecycleBin = QtWidgets.QCheckBox("Use Recycle Bin", self)
        self.chkRecycleBin.setChecked(True)
        left_layout.addWidget(self.chkRecycleBin)
        left_layout.addStretch()
        splitter.addWidget(left_panel)
        
        right_panel = QtWidgets.QWidget(self)
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(5)
        self.model = FileTableModel([], self.size_unit)
        self.proxyModel = FileFilterProxyModel(self)
        self.proxyModel.setSourceModel(self.model)
        self.tableView = QtWidgets.QTableView(self)
        self.tableView.setModel(self.proxyModel)
        self.tableView.setSortingEnabled(True)
        self.tableView.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tableView.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        right_layout.addWidget(self.tableView)
        self.labelSummary = QtWidgets.QLabel("Scanned 0 files.", self)
        right_layout.addWidget(self.labelSummary)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        main_layout.addWidget(splitter)
        
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
    
    def onFilterTextChanged(self) -> None:
        self.filterTimer.start(300)
    
    def updateFilter(self) -> None:
        filter_text = self.txtFilter.text()
        self.proxyModel.setFilterRegExp(filter_text)
    
    def onOnlyUnusedChanged(self) -> None:
        self.proxyModel.setOnlyUnused(self.chkOnlyUnused.isChecked())
    
    def onSizeUnitChanged(self) -> None:
        self.size_unit = self.comboSizeUnit.currentText()
        self.model.size_unit = self.size_unit
        self.model.updateData(self.all_files_info)
        self.updateSummaryLabel()
    
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
    
    def setTheme(self, theme: str, save: bool = True) -> None:
        self.theme = theme.lower()
        if self.theme == "dark":
            self.applyDarkThemeStylesheet()
        else:
            self.applyLightThemeStylesheet()
        if save:
            self.saveSettings()
    
    def applyLightThemeStylesheet(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background-color: #ffffff; color: #000000; }
            QToolBar { background-color: #f0f0f0; spacing: 6px; }
            QToolBar QToolButton { background-color: #ffffff; color: #000000;
                border: 1px solid #cccccc; border-radius: 4px; padding: 4px 10px; margin: 3px; }
            QToolBar QToolButton:hover { background-color: #e0e0e0; }
            QLabel, QCheckBox, QRadioButton { color: #333333; font-size: 13px; }
            QLineEdit { background-color: #ffffff; border: 1px solid #cccccc;
                color: #333333; border-radius: 4px; padding: 4px; }
            QComboBox { background-color: #ffffff; border: 1px solid #cccccc;
                color: #333333; border-radius: 4px; padding: 2px; }
            QTableView { background-color: #ffffff; alternate-background-color: #f9f9f9;
                gridline-color: #dddddd; color: #000000; font-size: 13px; }
            QHeaderView::section { background-color: #f0f0f0; color: #333333;
                border: 1px solid #cccccc; padding: 4px; }
            QProgressBar { background-color: #ffffff; border: 1px solid #cccccc;
                text-align: center; color: #333333; }
            QProgressBar::chunk { background-color: #4caf50; }
            QStatusBar { background-color: #f0f0f0; border-top: 1px solid #cccccc; }
            QMenuBar { background-color: #f0f0f0; color: #333333; }
            QMenuBar::item { background: transparent; padding: 4px 12px; }
            QMenuBar::item:selected { background-color: #4caf50; }
            QMenu { background-color: #ffffff; border: 1px solid #cccccc; }
            QMenu::item { padding: 4px 20px; color: #333333; }
            QMenu::item:selected { background-color: #4caf50; }
        """)
    
    def applyDarkThemeStylesheet(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background-color: #282c34; color: #ffffff; }
            QToolBar { background-color: #21252b; spacing: 6px; }
            QToolBar QToolButton { background-color: #3a3f4b; color: #abb2bf;
                border: 1px solid #3a3f4b; border-radius: 4px; padding: 4px 10px; margin: 3px; }
            QToolBar QToolButton:hover { background-color: #4b5263; }
            QLabel, QCheckBox, QRadioButton { color: #abb2bf; font-size: 13px; }
            QLineEdit { background-color: #3a3f4b; border: 1px solid #4b5263;
                color: #abb2bf; border-radius: 4px; padding: 4px; }
            QComboBox { background-color: #3a3f4b; border: 1px solid #4b5263;
                color: #abb2bf; border-radius: 4px; padding: 2px; }
            QTableView { background-color: #3a3f4b; alternate-background-color: #333842;
                gridline-color: #4b5263; color: #ffffff; font-size: 13px; }
            QHeaderView::section { background-color: #21252b; color: #61afef;
                border: 1px solid #3a3f4b; padding: 4px; }
            QProgressBar { background-color: #3a3f4b; border: 1px solid #4b5263;
                text-align: center; color: #ffffff; }
            QProgressBar::chunk { background-color: #98c379; }
            QStatusBar { background-color: #21252b; border-top: 1px solid #3a3f4b; }
            QMenuBar { background-color: #21252b; color: #abb2bf; }
            QMenuBar::item { background: transparent; padding: 4px 12px; }
            QMenuBar::item:selected { background-color: #61afef; }
            QMenu { background-color: #21252b; border: 1px solid #3a3f4b; }
            QMenu::item { padding: 4px 20px; color: #abb2bf; }
            QMenu::item:selected { background-color: #61afef; }
        """)
    
    def showHelpDialog(self) -> None:
        help_text = (
            "Musicians Organizer\n\n"
            "1. Select Folder: Choose a directory with music samples.\n"
            "2. Filter: Type in the left panel to filter files by name.\n"
            "3. Edit Metadata: Double-click Duration, BPM, Key, or Tags in the table.\n"
            "4. Duplicates: Use the toolbar to find duplicate files.\n"
            "5. Preview Audio: Use the toolbar to preview or stop audio playback.\n"
            "6. Waveform: View waveform for audio files.\n"
            "7. Delete Selected: Delete files via the toolbar.\n"
            "8. Cubase Integration: Set Cubase folder and send files directly.\n"
            "9. Progress Bar: Scanning and duplicate detection run in background threads.\n"
            "10. Sorting: Click on column headers to sort files.\n"
            "11. Theme: Switch between light and dark themes via the menu."
        )
        QtWidgets.QMessageBox.information(self, "Usage Help", help_text)
    
    def getSelectedFilePath(self) -> Optional[str]:
        selection = self.tableView.selectionModel().selectedRows()
        if selection:
            index = selection[0]
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            if file_info:
                return file_info["path"]
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
    
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self.saveSettings()
        event.accept()
    
    def selectFolder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            self.last_folder = folder

            db = DatabaseManager.instance()
            db.delete_files_in_folder(folder)

            self.scanner = FileScannerService(
                folder, 
                bpm_detection=self.chkBPM.isChecked()
            )
            self.scanner.progress.connect(lambda cur, tot: self.progressBar.setValue(int(cur / tot * 100)))
            self.scanner.finished.connect(self.onScanFinished)
            self.scanner.finished.connect(lambda: setattr(self, "scanner", None))
            QtCore.QTimer.singleShot(50, self.scanner.start)
    
    def onScanFinished(self, files: List[Dict[str, Any]]) -> None:
        self.progressBar.setValue(100)

        db = DatabaseManager.instance()

        folder_files = db.get_files_in_folder(self.last_folder)
        
        self.all_files_info = folder_files
        self.model.updateData(folder_files)

        from utils.helpers import bytes_to_unit
        total_size = sum(f["size"] for f in folder_files)
        converted_size = bytes_to_unit(total_size, self.size_unit)
        self.labelSummary.setText(
            f"Scanned {len(folder_files)} files. "
            f"Total size: {converted_size:.2f} {self.size_unit} (approx)."
        )
    
    def findDuplicates(self) -> None:
        self.progressBar.setValue(0)
        self.duplicateFinder = DuplicateFinderService(self.all_files_info)
        self.duplicateFinder.progress.connect(self.onDuplicateProgress)
        self.duplicateFinder.finished.connect(self.onDuplicatesFound)
        self.duplicateFinder.finished.connect(lambda: setattr(self, "duplicateFinder", None))
        self.duplicateFinder.start()
    
    @pyqtSlot(int, int)
    def onDuplicateProgress(self, current: int, total: int) -> None:
        if total > 0:
            percent = int((current / total) * 100)
            self.progressBar.setValue(percent)
        else:
            self.progressBar.setValue(0)
    
    @pyqtSlot(list)
    def onDuplicatesFound(self, duplicate_groups: List[List[Dict[str, Any]]]) -> None:
        self.progressBar.setValue(100)
        if duplicate_groups:
            dlg = DuplicateManagerDialog(duplicate_groups, size_unit=self.size_unit, use_recycle_bin=self.chkRecycleBin.isChecked(), parent=self)
            dlg.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "Find Duplicates", "No duplicate files found.")
    
    def openSelectedFileLocation(self) -> None:
        path = self.getSelectedFilePath()
        if path:
            open_file_location(path)
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")
    
    def deleteSelected(self) -> None:
        selection = self.tableView.selectionModel().selectedRows()
        if not selection:
            QtWidgets.QMessageBox.information(self, "Delete Selected", "No files selected.")
            return
        confirm = QtWidgets.QMessageBox.question(self, "Confirm Deletion",
                    f"Are you sure you want to delete {len(selection)} file(s)?",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
        if confirm != QtWidgets.QMessageBox.Yes:
            return
        
        errors = []
        indices_to_delete = []
        for index in selection:
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            try:
                if self.chkRecycleBin.isChecked():
                    send2trash(file_info["path"])
                else:
                    os.remove(file_info["path"])
                # Also remove from DB
                from services.database_manager import DatabaseManager
                DatabaseManager.instance().delete_file_record(file_info["path"])

                indices_to_delete.append(source_index.row())
            except Exception as e:
                errors.append(f"Error deleting {file_info['path']}: {str(e)}")
        
        if errors:
            QtWidgets.QMessageBox.critical(self, "Deletion Errors", "\n".join(errors))
        else:
            QtWidgets.QMessageBox.information(self, "Delete Selected", "Selected files deleted successfully.")
        
        for row in sorted(indices_to_delete, reverse=True):
            del self.all_files_info[row]
        self.model.updateData(self.all_files_info)
    
    def setCubaseFolder(self) -> None:
        folder = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Cubase Folder")
        if folder:
            self.cubase_folder = folder
    
    def previewSelected(self) -> None:
        path = self.getSelectedFilePath()
        if path:
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(path)))
            self.player.play()
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")
    
    def stopPreview(self) -> None:
        operation_canceled = False
        if self.scanner is not None:
            self.scanner.cancel()
            operation_canceled = True
            self.progressBar.setValue(0)
        if self.duplicateFinder is not None:
            self.duplicateFinder.cancel()
            operation_canceled = True
        if operation_canceled:
            QtWidgets.QMessageBox.information(self, "Operation Cancelled", "The active operation has been cancelled.")
        else:
            self.player.stop()
    
    def waveformPreview(self) -> None:
        path = self.getSelectedFilePath()
        if path:
            dialog = WaveformDialog(path, parent=self)
            dialog.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")
    
    def launchWaveformPlayer(self) -> None:
        path = self.getSelectedFilePath()
        if path:
            player_widget = WaveformPlayerWidget(path, theme=self.theme, parent=self)
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle("Waveform Player")
            layout = QtWidgets.QVBoxLayout(dialog)
            layout.addWidget(player_widget)
            dialog.exec_()
        else:
            QtWidgets.QMessageBox.information(self, "No Selection", "No file selected.")
    
    def autoTagFiles(self) -> None:
        if not self.all_files_info:
            QtWidgets.QMessageBox.information(self, "Auto Tag", "No files to tag.")
            return
        self.all_files_info = AutoTagService.auto_tag_files(self.all_files_info)
        self.model.updateData(self.all_files_info)
        QtWidgets.QMessageBox.information(self, "Auto Tag", "Auto-tagging completed.")
    
    def recommendSimilarSamples(self) -> None:
        QtWidgets.QMessageBox.information(self, "Recommend", "Recommendation feature is not implemented yet.")
    
    def sendToCubase(self) -> None:
        selection = self.tableView.selectionModel().selectedRows()
        if not selection or not self.cubase_folder:
            QtWidgets.QMessageBox.information(self, "Send to Cubase", "No file selected or Cubase folder not set.")
            return
        for index in selection:
            source_index = self.proxyModel.mapToSource(index)
            file_info = self.model.getFileAt(source_index.row())
            try:
                shutil.copy(file_info["path"], self.cubase_folder)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to send {file_info['path']} to Cubase: {e}")
        QtWidgets.QMessageBox.information(self, "Send to Cubase", "Files sent to Cubase successfully.")

    def updateSummaryLabel(self) -> None:
        if not self.all_files_info:
            self.labelSummary.setText("No files scanned.")
            return
        from utils.helpers import bytes_to_unit
        total_size = sum(f["size"] for f in self.all_files_info)
        converted_size = bytes_to_unit(total_size, self.size_unit)
        self.labelSummary.setText(
            f"Scanned {len(self.all_files_info)} files. "
            f"Total size: {converted_size:.2f} {self.size_unit} (approx)."
        )
