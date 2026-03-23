# FILE: tests/test_ui_main_window.py

import pytest
from pytestqt.qtbot import QtBot

from services.database_manager import DatabaseManager
from ui.main_window import MainWindow

# --- Test Function using Pytest Fixtures ---


# No test class needed for simple functional tests with pytest
def test_main_window_instantiation(qtbot: QtBot, db_manager: DatabaseManager):
    """
    Tests if the MainWindow can be instantiated correctly,
    passing the required db_manager fixture.
    qtbot fixture manages QApplication lifetime.
    """
    # Instantiate MainWindow, passing the db_manager provided by the fixture
    window = MainWindow(db_manager=db_manager)

    # Basic assertion: Check if the window object was created
    assert window is not None

    # Optional: Add a qtbot wait to ensure the window is processed by event loop
    # qtbot.waitExposed(window) # Uncomment if needed for more complex tests

    # Optional: Further checks on the window state after instantiation
    assert window.windowTitle() == "Musicians Organizer"
    assert window.db_manager is db_manager  # Verify db_manager was stored
