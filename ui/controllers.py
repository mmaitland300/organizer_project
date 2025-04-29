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

    # --- MODIFY: Update __init__ ---
    def __init__(self, db_manager: DatabaseManager, parent: QObject = None) -> None: # <<< Accept db_manager
        super().__init__(parent)
        self._scanner: Optional[FileScannerService] = None
        self.state = ControllerState.Idle
        self.db_manager = db_manager # <<< Store db_manager

    def start_scan(self, folder: str, bpm_detection: bool = False) -> None:
        """
        Begin scanning the given folder asynchronously.
        """
        # --- ADD check for db_manager ---
        if not self.db_manager or not self.db_manager.engine:
            err_msg = "DatabaseManager not initialized in ScanController."
            logger.error(err_msg)
            self.error.emit(err_msg)
            return
        # --- End check --
        try:
            if self._scanner and self._scanner.isRunning():
                 logger.warning("ScanController: Cancelling previous scanner before starting new one.")
                 self.cancel() # Ensure previous is stopped if somehow still running
                 # Potentially add a short wait or check state before proceeding

            # --- MODIFY: Pass db_manager to FileScannerService ---
            self._scanner = FileScannerService(folder, db_manager=self.db_manager) # <<< Pass stored db_manager
            # --- End Modification ---

            self._scanner.progress.connect(self.progress)
            self._scanner.finished.connect(self._on_finished)
            # Switch to Running state
            self.state = ControllerState.Running
            self.stateChanged.emit(self.state)
            self.started.emit()
            QTimer.singleShot(0, self._scanner.start) # Keep using QTimer for async start
        except Exception as e:
            logger.error(f"Scan start failed: {e}", exc_info=True)
            self.state = ControllerState.Idle # Reset state on error
            self.stateChanged.emit(self.state)
            self.error.emit(f"Scan start failed: {e}") # Emit error signal

    def cancel(self) -> None:
        """
        Cancel an ongoing scan.
        """
        # --- Corrected cancel logic based on your previous code ---
        if self._scanner and self._scanner.isRunning():
             try:
                 logger.info("ScanController: Requesting scanner cancellation.")
                 self.state = ControllerState.Cancelling
                 self.stateChanged.emit(self.state) # Emit cancelling state
                 self._scanner.cancel()
                 # Don't wait indefinitely here, _on_finished will handle state reset
                 # self._scanner.wait(100) # Avoid long waits in controller slot
             except Exception as e:
                 logger.error(f"Scan cancel failed: {e}", exc_info=True)
                 # Optionally reset state to Idle if cancel fails catastrophically
                 # self.state = ControllerState.Idle
                 # self.stateChanged.emit(self.state)
        else:
            logger.debug("ScanController: Cancel called but no scanner running.")
            # Ensure state is Idle if cancel is called erroneously
            if self.state != ControllerState.Idle:
                 self.state = ControllerState.Idle
                 self.stateChanged.emit(self.state)


    def _on_finished(self, files: List[Dict[str, Any]]) -> None:
        """
        Handler invoked when scanning completes or is cancelled.
        """
        # --- Corrected finished logic based on your previous code ---
        logger.debug(f"ScanController received finished signal. Current state: {self.state}")
        scanner_ref = self._scanner # Temp reference if needed for logging?

        # Check if cancellation was requested. Scanner might finish normally even after cancel request.
        was_cancelling = (self.state == ControllerState.Cancelling)
        self.state = ControllerState.Idle # Always go to Idle when finished/cancelled
        self.stateChanged.emit(self.state)

        if was_cancelling:
             logger.info("Scan finished after cancellation request.")
             # May emit empty list or partial results depending on scanner's cancel behavior
             self.finished.emit([]) # Emit empty list if cancelled is desired outcome
        else:
             logger.info("Scan finished normally.")
             self.finished.emit(files) # Emit results normally

        self._scanner = None # Clear scanner reference
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

    # --- MODIFY: Update __init__ ---
    def __init__(self, db_manager: DatabaseManager, parent: QObject = None) -> None: # <<< Accept db_manager
        super().__init__(parent)
        self._worker: Optional[AdvancedAnalysisWorker] = None
        self.state = ControllerState.Idle
        self._was_cancelled: bool = False
        self.db_manager = db_manager # <<< Store db_manager

    def start_analysis(self, files_info: List[Dict[str, Any]]) -> None:
        """ Begin advanced analysis on the provided file info list. """
        if not self.db_manager or not self.db_manager.engine:
            err_msg = "DatabaseManager not initialized in AnalysisController."
            logger.error(err_msg)
            self.error.emit(err_msg)
            return

        self._was_cancelled = False
        try:
            if self._worker and self._worker.isRunning():
                 logger.warning("AnalysisController: Cancelling previous worker before starting new one.")
                 self.cancel()

            # --- MODIFY THIS LINE ---
            # Pass the stored db_manager when creating the worker
            self._worker = AdvancedAnalysisWorker(files_info, db_manager=self.db_manager)
            # --- End Modification ---

            self._worker.progress.connect(self.progress)
            self._worker.finished.connect(self._on_finished)
            self.state = ControllerState.Running
            self.stateChanged.emit(self.state)
            self.started.emit()
            self._worker.start()
        except Exception as e:
             logger.error(f"Analysis start failed: {e}", exc_info=True)
             self.state = ControllerState.Idle
             self.stateChanged.emit(self.state)
             self.error.emit(f"Analysis start failed: {e}")


    def cancel(self):
        """Requests cancellation of the currently running worker task."""
        logger.info("AnalysisController cancel method called.")
        self._was_cancelled = True # Set cancellation flag

        if self._worker and self._worker.isRunning():
            self.state = ControllerState.Cancelling
            logger.info(f"Calling cancel() on worker: {self._worker}")
            self._worker.cancel() # Call cancel on the actual worker instance
            logger.info("Worker cancel() method called.")
        else:
            # If no worker running or instance doesn't exist, just ensure state is Idle
            logger.info("No running worker found or worker is None, setting state to Idle.")
            self.state = ControllerState.Idle


    def was_cancelled(self) -> bool: # Helper method
        return self._was_cancelled

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
