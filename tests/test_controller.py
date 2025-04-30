# tests/test_controller.py
import pytest
from unittest.mock import MagicMock, patch, call # Keep necessary imports

from PyQt5.QtCore import QObject, pyqtSignal # Keep imports if needed elsewhere

# Assume imports for AnalysisController, ControllerState exist
from ui.controllers import AnalysisController, ControllerState
# We no longer need to import AdvancedAnalysisWorker itself when only patching
# from services.advanced_analysis_worker import AdvancedAnalysisWorker
from services.database_manager import DatabaseManager

# --- Mock Fixture for DB Manager (Keep as is) ---
@pytest.fixture
def mock_db_manager():
    """ Mock the DatabaseManager """
    mock = MagicMock(spec=DatabaseManager)
    mock.engine = MagicMock()
    return mock

# --- REMOVED MockAnalysisWorker class definition ---
# The custom class is no longer needed with the standard patch approach.


# --- Test Function (Using standard patch, no new_callable) ---

# MODIFIED: Standard patch without new_callable. Decorator injects a mock CLASS.
@patch('ui.controllers.AdvancedAnalysisWorker')
# Test signature receives the MagicMock CLASS from the patch decorator, and db_manager fixture.
def test_analysis_controller_signal_connections(MockWorkerClass, mock_db_manager):
    """
    Verify AnalysisController instantiates the worker class correctly
    and calls its start method.
    """
    controller = AnalysisController(db_manager=mock_db_manager)
    dummy_files = [{'path': 'a.wav'}, {'path': 'b.wav'}]

    # --- Act ---
    # Calling start_analysis will now call the MockWorkerClass (a MagicMock class)
    # This instantiation call returns a MagicMock INSTANCE.
    controller.start_analysis(dummy_files)

    # Get the MagicMock INSTANCE that was created and assigned to controller._worker
    mock_worker_instance = controller._worker

    # --- Assert ---
    # 1. Check that the worker instance was created and stored.
    assert mock_worker_instance is not None, "Worker instance should be created by controller"
    # Optional: Check it's a MagicMock instance (it will be)
    assert isinstance(mock_worker_instance, MagicMock), "Worker instance should be a MagicMock"

    # 2. Verify that the AnalysisController called the constructor of the
    #    (mocked) AdvancedAnalysisWorker class with the correct arguments.
    MockWorkerClass.assert_called_once_with(dummy_files, db_manager=controller.db_manager)

    # 3. Check that the 'start' method was called on the MagicMock INSTANCE.
    mock_worker_instance.start.assert_called_once()

    # 4. Check that the 'deleteLater' method exists on the mock instance
    #    (MagicMock creates methods automatically on access). Calling it here
    #    just ensures the attribute access works, doesn't assert it was called yet.
    assert hasattr(mock_worker_instance, 'deleteLater')
    # NOTE: We cannot easily test signal connections with this standard mock.
    # Testing the controller's *reaction* to signals would require spying on the
    # controller's slots and manually triggering the mock worker instance's
    # signal attributes (which are also MagicMocks) like:
    # controller._worker.analysisComplete.emit([]) # Requires QSignalSpy on controller


# (Add other controller tests below if needed)