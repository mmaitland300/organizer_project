# ui/controllers.py
import logging
import os
from collections import OrderedDict
from enum import Enum
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

from config.settings import AUDIO_EXTENSIONS
from services.advanced_analysis_worker import AdvancedAnalysisWorker
from services.analysis_engine import AnalysisEngine
from services.database_manager import DatabaseManager
from services.duplicate_finder import DuplicateFinderService
from services.file_scanner import FileScannerService

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ControllerState(Enum):
    Idle = 0
    Running = 1
    Cancelling = 2


class ScanController(QObject):
    """
    Encapsulates folder scanning functionality with state and error signaling.
    """

    started = pyqtSignal()
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    stateChanged = pyqtSignal(object)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self._scanner: Optional[FileScannerService] = None
        self.state = ControllerState.Idle

    def start_scan(self, folder: str, bpm_detection: bool = False) -> None:
        """
        Begin scanning the given folder asynchronously.
        """
        try:
            if self._scanner:
                self.cancel()
            self._scanner = FileScannerService(folder) 
            self._scanner.progress.connect(self.progress)
            self._scanner.finished.connect(self._on_finished)
            # Switch to Running state
            self.state = ControllerState.Running
            self.stateChanged.emit(self.state)
            self.started.emit()
            QTimer.singleShot(0, self._scanner.start) # Keep using QTimer for async start
        except Exception as e:
            logger.error(f"Scan start failed: {e}", exc_info=True) # Log traceback

    def cancel(self) -> None:
        """
        Cancel an ongoing scan.
        """
        if self._scanner:
            try:
                self._scanner.cancel()
                # Optionally wait briefly or check state before changing controller state
                self.state = ControllerState.Cancelling
                self.stateChanged.emit(self.state)
            except Exception as e:
                logger.error(f"Scan cancel failed: {e}", exc_info=True)

    def _on_finished(self, files: List[Dict[str, Any]]) -> None:
        """
        Handler invoked when scanning completes.
        """
        logger.debug(f"ScanController received finished signal. Setting state to Idle.")
        scanner_ref = self._scanner # Temp reference if needed
        self.state = ControllerState.Idle
        self.stateChanged.emit(self.state)
        self.finished.emit(files)
        self._scanner = None
        logger.debug("ScanController finished processing.")


class DuplicatesController(QObject):
    """
    Encapsulates duplicate detection functionality.
    """

    started = pyqtSignal()
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    stateChanged = pyqtSignal(object)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self._finder: Optional[DuplicateFinderService] = None
        self.state = ControllerState.Idle

    def start_detection(self, files_info: List[Dict[str, Any]]) -> None:
        """
        Begin duplicate detection on the provided file info list.
        """
        try:
            if self._finder:
                self.cancel()
            self._finder = DuplicateFinderService(files_info)
            self._finder.progress.connect(self.progress)
            self._finder.finished.connect(self._on_finished)
            self.state = ControllerState.Running
            self.stateChanged.emit(self.state)
            self.started.emit()
            self._finder.start()
        except Exception as e:
            self.error.emit(f"Duplicate detection start failed: {e}")

    def cancel(self) -> None:
        """
        Cancel ongoing duplicate detection.
        """
        if self._finder:
            try:
                self._finder.cancel()
                self.state = ControllerState.Cancelling
                self.stateChanged.emit(self.state)
            except Exception as e:
                self.error.emit(f"Duplicate cancel failed: {e}")

    def _on_finished(self, duplicate_groups: List[List[Dict[str, Any]]]) -> None:
        """
        Handler invoked when duplicate detection completes.
        """
        logger.debug(f"{self.__class__.__name__} task finished. Setting state to Idle.") # Added log
        self.state = ControllerState.Idle
        self.stateChanged.emit(self.state)
        self.finished.emit(duplicate_groups)
        self._finder = None


class AnalysisController(QObject):
    """
    Encapsulates advanced DSP analysis functionality.
    """

    started = pyqtSignal()
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    stateChanged = pyqtSignal(object)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self._worker: Optional[AdvancedAnalysisWorker] = None
        self.state = ControllerState.Idle

    def start_analysis(self, files_info: List[Dict[str, Any]]) -> None:
        """
        Begin advanced analysis on the provided file info list.
        """
        try:
            if self._worker:
                self.cancel()
            self._worker = AdvancedAnalysisWorker(files_info)
            self._worker.progress.connect(self.progress)
            self._worker.finished.connect(self._on_finished)
            self.state = ControllerState.Running
            self.stateChanged.emit(self.state)
            self.started.emit()
            self._worker.start()
        except Exception as e:
            self.error.emit(f"Analysis start failed: {e}")

    def cancel(self) -> None:
        """
        Cancel ongoing advanced analysis.
        """
        if self._worker:
            try:
                self._worker.cancel()
                self.state = ControllerState.Cancelling
                self.stateChanged.emit(self.state)
            except Exception as e:
                self.error.emit(f"Analysis cancel failed: {e}")

    def _on_finished(self, updated_files: List[Dict[str, Any]]) -> None:
        """Handler invoked when advanced analysis completes."""
        logger.debug("AnalysisController entering _on_finished. Current state: %s", self.state) # ADD LOG
        if self.state != ControllerState.Idle: # Only change state if not already Idle
            self.state = ControllerState.Idle
            logger.debug("AnalysisController state set to Idle.") # ADD LOG
            try:
                self.stateChanged.emit(self.state)
                logger.debug("AnalysisController stateChanged emitted.") # ADD LOG
            except Exception as e:
                 logger.error(f"Error emitting stateChanged from AnalysisController: {e}", exc_info=True) # ADD LOG
        else:
             logger.debug("AnalysisController already Idle in _on_finished.") # ADD LOG

        try:
            self.finished.emit(updated_files)
            logger.debug("AnalysisController finished signal emitted.") # ADD LOG
        except Exception as e:
             logger.error(f"Error emitting finished from AnalysisController: {e}", exc_info=True) # ADD LOG

        self._worker = None
        logger.debug("AnalysisController _on_finished completed.") # ADD LOG
