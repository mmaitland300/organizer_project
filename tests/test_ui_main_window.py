# FILE: tests/test_ui_main_window.py
# Refactored to use pytest fixtures, corrected qtbot import path

import pytest # Import pytest
import os
import sys

# Import necessary types for hints
from PyQt5.QtWidgets import QApplication
# Note: qtbot fixture handles QApplication instance, explicit import often not needed

# --- CORRECTED IMPORT ---
# Import QtBot class using the actual filename 'qtbot.py' found in site-packages
from pytestqt.qtbot import QtBot # For type hinting the fixture

# Import code being tested
from ui.main_window import MainWindow
from services.database_manager import DatabaseManager # For type hint

# Ensure platform is set correctly for headless environments if needed
# pytest-qt generally handles this, but keep if required for your specific setup
# os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
    assert window.db_manager is db_manager # Verify db_manager was stored