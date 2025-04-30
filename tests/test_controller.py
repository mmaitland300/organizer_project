# tests/test_controllers.py (New or existing file)
import pytest
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QObject
# Assume imports for AnalysisController, AdvancedAnalysisWorker, ControllerState exist
from ui.controllers import AnalysisController, ControllerState
from services.advanced_analysis_worker import AdvancedAnalysisWorker
from services.database_manager import DatabaseManager # If needed for init

# Mock necessary classes/modules if they aren't easily instantiated
@pytest.fixture
def mock_db_manager():
    # Mock the DatabaseManager if needed for controller initialization
    mock = MagicMock()
    mock.engine = MagicMock() # Mock the engine attribute check
    return mock

@pytest.fixture
def mock_advanced_analysis_worker():
    """Mocks the AdvancedAnalysisWorker class."""
    # Create a mock class that inherits from QObject to handle signals/slots
    class MockWorker(QObject):
        # Define signals with the correct signatures
        progress = MagicMock()
        # Custom signal renamed
        analysisComplete = MagicMock(pyqtSignal = MagicMock(return_value=list))
        error = MagicMock()
        # QThread's built-in signal (mock doesn't actually inherit QThread,
        # but we mock the signal connection)
        finished = MagicMock(pyqtSignal = MagicMock(return_value=None)) # Built-in finished takes no args
        # Add methods needed by the controller
        isRunning = MagicMock(return_value=False)
        start = MagicMock()
        cancel = MagicMock()
        deleteLater = MagicMock()

        def __init__(self, files, db_manager):
            super().__init__() # QObject init
            # Mock signal connect/disconnect methods
            self.progress.connect = MagicMock()
            self.analysisComplete.connect = MagicMock()
            self.error.connect = MagicMock()
            self.finished.connect = MagicMock() # Mock connect for built-in signal

    return MockWorker


@patch('ui.controllers.AdvancedAnalysisWorker', new_callable=mock_advanced_analysis_worker)
def test_analysis_controller_signal_connections(MockWorkerClass, mock_db_manager):
    """
    Verify AnalysisController connects worker signals to the correct slots.
    """
    controller = AnalysisController(db_manager=mock_db_manager)
    dummy_files = [{'path': 'a.wav'}, {'path': 'b.wav'}]

    # --- Act ---
    controller.start_analysis(dummy_files)
    mock_worker_instance = controller._worker # Get the instantiated mock worker

    # --- Assert ---
    assert mock_worker_instance is not None, "Worker should be instantiated"

    # Check connection for custom data signal 'analysisComplete'
    mock_worker_instance.analysisComplete.connect.assert_called_once_with(controller._on_worker_data_finished)

    # Check connections for built-in 'finished' signal (cleanup)
    # It should be connected to _on_worker_thread_finished and deleteLater
    finish_calls = mock_worker_instance.finished.connect.call_args_list
    assert any(call.args[0] == controller._on_worker_thread_finished for call in finish_calls), \
        "Built-in finished signal not connected to _on_worker_thread_finished"
    assert any(call.args[0] == mock_worker_instance.deleteLater for call in finish_calls), \
        "Built-in finished signal not connected to deleteLater"

    # Check other connections (progress, error)
    mock_worker_instance.progress.connect.assert_called_once_with(controller.progress)
    # Error is connected to controller's error signal AND the thread finished slot
    error_calls = mock_worker_instance.error.connect.call_args_list
    assert any(call.args[0] == controller.error for call in error_calls)
    assert any(call.args[0] == controller._on_worker_thread_finished for call in error_calls)

    # Ensure the custom signal was *not* connected to the thread finished slot
    ac_connect_calls = mock_worker_instance.analysisComplete.connect.call_args_list
    assert not any(call.args[0] == controller._on_worker_thread_finished for call in ac_connect_calls), \
        "Custom data signal should NOT be connected to _on_worker_thread_finished"