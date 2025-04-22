# ui/dialogs/feature_view_dialog.py
"""
Dialog for displaying detailed audio features of a selected file.
"""

import os
import logging
from typing import Any, Dict

from PyQt5 import QtCore, QtWidgets

# Import constants from the central settings file
# Assuming config directory is accessible from ui.dialogs path
# Adjust relative path if needed, e.g., from ...config.settings import ...
try:
    from config.settings import ALL_FEATURE_KEYS, FEATURE_DISPLAY_NAMES
except ImportError:
    # Fallback or raise error if settings cannot be imported
    logging.error("CRITICAL: Could not import settings from config.settings!")
    # Define fallbacks ONLY FOR RUNNING this module standalone for testing,
    # application run should rely on correct PYTHONPATH.
    ALL_FEATURE_KEYS = ['brightness', 'loudness_rms'] # Example fallback
    FEATURE_DISPLAY_NAMES = {'brightness': 'Brightness', 'loudness_rms': 'Loudness'} # Example fallback

logger = logging.getLogger(__name__)

class FeatureViewDialog(QtWidgets.QDialog):
    """
    Displays calculated audio features for a single file in a table format.
    """
    def __init__(self, file_info: Dict[str, Any], parent=None):
        super().__init__(parent)

        file_path = file_info.get("path", "Unknown File")
        self.setWindowTitle(f"Audio Features: {os.path.basename(file_path)}")
        self.setMinimumWidth(450)
        self.setMinimumHeight(400)
        self.resize(450, 500) # Default size

        layout = QtWidgets.QVBoxLayout(self)

        # Add file path label for context
        path_label = QtWidgets.QLabel(f"<b>File:</b> {file_path}")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        # Create Table
        self.tableWidget = QtWidgets.QTableWidget()
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Feature", "Value"])
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tableWidget.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers) # Read-only
        self.tableWidget.verticalHeader().setVisible(False) # Hide row numbers
        self.tableWidget.setAlternatingRowColors(True) # Improve readability

        self.populate_table(file_info)

        # Resize columns after populating
        self.tableWidget.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.tableWidget.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.tableWidget.resizeRowsToContents() # Adjust row height if needed

        layout.addWidget(self.tableWidget)

        # Standard OK button
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        buttonBox.accepted.connect(self.accept)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def populate_table(self, file_info: Dict[str, Any]):
        """Fills the table with feature names and values."""
        # Filter keys to display only those present in FEATURE_DISPLAY_NAMES
        # and potentially also check if they are in file_info to avoid empty rows,
        # or display N/A as implemented below.
        display_keys = [key for key in ALL_FEATURE_KEYS if key in FEATURE_DISPLAY_NAMES]

        self.tableWidget.setRowCount(len(display_keys))

        row = 0
        for key in display_keys:
            display_name = FEATURE_DISPLAY_NAMES[key] # Use guaranteed key
            value = file_info.get(key) # Get value, might be None

            # Format value for display
            if isinstance(value, float):
                formatted_value = f"{value:.4f}" # Display floats with 4 decimal places
            elif value is None:
                formatted_value = "N/A" # Indicate missing data gracefully
            else:
                formatted_value = str(value) # Other types as string

            name_item = QtWidgets.QTableWidgetItem(display_name)
            value_item = QtWidgets.QTableWidgetItem(formatted_value)

            # Make name column non-editable flags just in case
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
            value_item.setFlags(value_item.flags() & ~QtCore.Qt.ItemIsEditable)

            # Align numerical values to the right (optional)
            if isinstance(value, (int, float)):
                 value_item.setTextAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

            self.tableWidget.setItem(row, 0, name_item)
            self.tableWidget.setItem(row, 1, value_item)
            row += 1

        # Ensure sorting is disabled
        self.tableWidget.setSortingEnabled(False)