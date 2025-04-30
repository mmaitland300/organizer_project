# Filename: ui/dialogs/spectrogram_dialog.py
# New File

import logging
import os
from typing import Optional

# --- PyQt5 Imports ---
from PyQt5 import QtWidgets, QtCore

# --- Matplotlib Imports ---
try:
    import matplotlib
    matplotlib.use('Qt5Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    FigureCanvas = object # type: ignore
    NavigationToolbar = object # type: ignore
    Figure = object # type: ignore

# --- Application Imports ---
try:
    # Assuming SpectrogramPlotter service is in services directory now
    from services.spectrogram_plotter import SpectrogramPlotter
    PLOTTER_AVAILABLE = True
except ImportError:
    SpectrogramPlotter = None # type: ignore
    PLOTTER_AVAILABLE = False

logger = logging.getLogger(__name__)

class SpectrogramDialog(QtWidgets.QDialog):
    """
    A dialog window that displays an audio file's spectrogram using SpectrogramPlotter.
    Manages the Matplotlib Figure, Canvas, and Toolbar integration within Qt.
    """
    def __init__(self, file_path: str, theme: str = 'light', parent: Optional[QtWidgets.QWidget] = None):
        """
        Initializes the SpectrogramDialog.

        Args:
            file_path: The absolute path to the audio file to display.
            theme: The current theme ('light' or 'dark') for styling.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.file_path = file_path
        self.theme = theme.lower()

        # Set window properties
        self.setWindowTitle(f"Spectrogram: {os.path.basename(self.file_path)}")
        self.setMinimumSize(600, 400) # Set a reasonable minimum size
        self.resize(800, 500) # Set a default size

        # Main layout
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5) # Add small margins

        # --- Check Dependencies ---
        if not MATPLOTLIB_AVAILABLE or not PLOTTER_AVAILABLE:
            error_msg = "Cannot display spectrogram:\n"
            if not MATPLOTLIB_AVAILABLE:
                error_msg += "- Matplotlib components missing.\n"
            if not PLOTTER_AVAILABLE:
                 error_msg += "- SpectrogramPlotter service missing.\n"
            logger.error(error_msg)
            error_label = QtWidgets.QLabel(error_msg)
            error_label.setAlignment(QtCore.Qt.AlignCenter)
            main_layout.addWidget(error_label)
            # Add only an OK button if dependencies are missing
            buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
            buttonBox.accepted.connect(self.accept)
            main_layout.addWidget(buttonBox)
            self.setLayout(main_layout)
            return # Stop initialization

        # --- Matplotlib Widget Setup ---
        try:
            # Create Figure, Canvas, Axes, and Toolbar
            # Store figure explicitly if needed elsewhere, otherwise just create
            self.figure = Figure(figsize=(8, 4)) # Control aspect ratio/default size
            self.canvas = FigureCanvas(self.figure)
            self.canvas.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            self.ax = self.figure.add_subplot(111)
            self.toolbar = NavigationToolbar(self.canvas, self) # Parent is the dialog

            # Add Toolbar and Canvas to layout
            main_layout.addWidget(self.toolbar)
            main_layout.addWidget(self.canvas)

            # --- Plotting ---
            # Call the static plot method from the service
            plot_successful = SpectrogramPlotter.plot(
                file_path=self.file_path,
                ax=self.ax,
                figure=self.figure,
                theme=self.theme
            )
            # No specific action needed here based on plot_successful, as errors
            # are handled by displaying text directly on the axes by the plotter.

            # Initial draw of the canvas
            self.canvas.draw()

        except Exception as e:
            logger.critical(f"Failed to create Matplotlib canvas/toolbar or plot: {e}", exc_info=True)
            # Fallback: display an error message if Matplotlib setup fails
            main_layout.removeWidget(self.toolbar) # Remove potentially half-added widgets
            main_layout.removeWidget(self.canvas)
            error_label = QtWidgets.QLabel(f"Error creating plot area:\n{e}")
            error_label.setAlignment(QtCore.Qt.AlignCenter)
            main_layout.addWidget(error_label)


        # --- Dialog Button Box ---
        buttonBox = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        buttonBox.accepted.connect(self.accept)
        main_layout.addWidget(buttonBox)

        self.setLayout(main_layout)
        self._apply_dialog_theme() # Apply theme to dialog background

    def _apply_dialog_theme(self):
        """Applies theme to the dialog's background."""
        # Simple background styling for the dialog itself
        bg_color = '#282c34' if self.theme == 'dark' else '#FFFFFF'
        self.setStyleSheet(f"QDialog {{ background-color: {bg_color}; }}")