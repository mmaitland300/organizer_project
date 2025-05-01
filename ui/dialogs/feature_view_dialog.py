# FILE: ui/dialogs/feature_view_dialog.py
"""
Dialog for displaying detailed audio features of a selected file in a specific order.
"""

import logging
import os
from typing import Any, Dict, List  # Add List import

from PyQt5 import QtCore, QtWidgets

# --- Import necessary constants from settings ---
# Includes categorized keys for ordering and display names
try:
    from config.settings import ADDITIONAL_FEATURE_KEYS  # The new features
    from config.settings import (  # Keys needed for ordering:; ALL_FEATURE_KEYS # Not strictly needed if using categorized lists
        CORE_FEATURE_KEYS,
        FEATURE_DISPLAY_NAMES,
        MFCC_FEATURE_KEYS,
        SPECTRAL_FEATURE_KEYS,
    )
except ImportError:
    # Fallback or raise error if settings cannot be imported
    logging.error("CRITICAL: Could not import settings constants from config.settings!")
    # Define minimal fallbacks for standalone testing if absolutely necessary
    CORE_FEATURE_KEYS = ["brightness", "loudness_rms"]
    ADDITIONAL_FEATURE_KEYS = ["bit_depth", "loudness_lufs", "pitch_hz", "attack_time"]
    SPECTRAL_FEATURE_KEYS = ["zcr_mean", "spectral_contrast_mean"]
    MFCC_FEATURE_KEYS = []  # Assume none in fallback
    ALL_FEATURE_KEYS = (
        CORE_FEATURE_KEYS
        + ADDITIONAL_FEATURE_KEYS
        + SPECTRAL_FEATURE_KEYS
        + MFCC_FEATURE_KEYS
    )
    FEATURE_DISPLAY_NAMES = {
        key: key.replace("_", " ").title() for key in ALL_FEATURE_KEYS
    }

logger = logging.getLogger(__name__)


class FeatureViewDialog(QtWidgets.QDialog):
    """
    Displays calculated audio features for a single file in a table format,
    ordering primary and new features first, and MFCCs last.
    """

    def __init__(self, file_info: Dict[str, Any], parent=None):
        super().__init__(parent)

        self.file_info = file_info  # Store for population method
        file_path = file_info.get("path", "Unknown File")
        self.setWindowTitle(f"Audio Features: {os.path.basename(file_path)}")
        self.setMinimumWidth(450)  # Adjust as needed
        self.setMinimumHeight(400)
        self.resize(450, 550)  # Adjusted default height

        layout = QtWidgets.QVBoxLayout(self)

        # Add file path label for context
        path_label = QtWidgets.QLabel(f"<b>File:</b> {file_path}")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        # Create Table
        self.tableWidget = QtWidgets.QTableWidget()
        self.tableWidget.setObjectName("featureTableWidget")  # Add object name
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Feature", "Value"])
        self.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.tableWidget.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers
        )  # Read-only
        self.tableWidget.verticalHeader().setVisible(False)  # Hide row numbers
        self.tableWidget.setAlternatingRowColors(True)
        # Disable sorting, as we define the logical order
        self.tableWidget.setSortingEnabled(False)

        # Populate table using the modified method
        self.populate_table_ordered(file_info)

        # Resize columns after populating
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeToContents
        )  # Feature name fits content
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            1, QtWidgets.QHeaderView.Stretch
        )  # Value takes remaining space
        self.tableWidget.resizeRowsToContents()  # Adjust row heights

        layout.addWidget(self.tableWidget)

        # Standard OK button
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        buttonBox.accepted.connect(self.accept)
        layout.addWidget(buttonBox)

        self.setLayout(layout)

    def populate_table_ordered(self, file_info: Dict[str, Any]):
        """
        Fills the table with feature names and values in a specific order:
        Core -> New Features -> Spectral -> MFCCs.
        """
        # --- Define the desired display order using lists from settings ---
        ordered_keys: List[str] = []
        ordered_keys.extend(CORE_FEATURE_KEYS)
        ordered_keys.extend(ADDITIONAL_FEATURE_KEYS)  # Add NEW features here
        ordered_keys.extend(SPECTRAL_FEATURE_KEYS)
        # Add any other feature keys *not* in the above lists OR MFCCs, if desired
        # Example: Get all keys from file_info that might exist but aren't categorized
        # other_keys = [k for k in file_info.keys() if k in FEATURE_DISPLAY_NAMES and k not in ordered_keys and k not in MFCC_FEATURE_KEYS]
        # ordered_keys.extend(sorted(other_keys)) # Add alphabetically perhaps
        ordered_keys.extend(MFCC_FEATURE_KEYS)  # Add MFCCs last

        # Filter this list to only include keys actually present in FEATURE_DISPLAY_NAMES
        # (This handles cases where settings might have keys not meant for display)
        display_keys_ordered = [
            key for key in ordered_keys if key in FEATURE_DISPLAY_NAMES
        ]

        # Remove duplicates while preserving order (in case lists in settings overlap)
        seen = set()
        display_keys_unique_ordered = [
            k for k in display_keys_ordered if not (k in seen or seen.add(k))
        ]

        self.tableWidget.setRowCount(len(display_keys_unique_ordered))
        logger.debug(
            f"Populating feature table with {len(display_keys_unique_ordered)} ordered keys."
        )

        row = 0
        for key in display_keys_unique_ordered:
            display_name = FEATURE_DISPLAY_NAMES.get(
                key, key.replace("_", " ").title()
            )  # Use get() for safety
            value = file_info.get(key)  # Get value from the data dict

            # --- Format the value for display ---
            formatted_value: str
            if value is None:
                formatted_value = "N/A"  # Indicate missing data
            elif isinstance(value, float):
                # Use specific formatting based on the key for clarity
                if key == "attack_time":
                    formatted_value = (
                        f"{value:.4f} s"  # Show seconds with more precision
                    )
                elif key in ["loudness_lufs", "pitch_hz"]:
                    formatted_value = f"{value:.2f}"
                else:  # Default float formatting (e.g., MFCCs, brightness)
                    formatted_value = f"{value:.4f}"  # Increased default precision
            elif isinstance(value, int):
                # Display integers directly (e.g., bit_depth)
                formatted_value = str(value)
            else:
                # Fallback for any other data types (e.g., strings, if any)
                formatted_value = str(value)

            # --- Create Table Items ---
            name_item = QtWidgets.QTableWidgetItem(display_name)
            value_item = QtWidgets.QTableWidgetItem(formatted_value)

            # Set read-only flags
            name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemIsEditable)
            value_item.setFlags(value_item.flags() & ~QtCore.Qt.ItemIsEditable)

            # Align numerical values to the right for better readability
            if isinstance(value, (int, float)):
                value_item.setTextAlignment(
                    QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
                )
            else:
                value_item.setTextAlignment(
                    QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
                )

            # --- Add Items to Table ---
            self.tableWidget.setItem(row, 0, name_item)
            self.tableWidget.setItem(row, 1, value_item)
            row += 1

        logger.debug("Feature table population complete.")
