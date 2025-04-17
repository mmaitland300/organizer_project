# ui/dialogs/waveform_dialog.py
"""
WaveformDialog - displays a waveform preview for a given audio file using WaveformPlotter.
"""

import os
from typing import Optional
from PyQt5 import QtWidgets
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt

from services.waveform_plotter import WaveformPlotter
from config.settings import ENABLE_WAVEFORM_PREVIEW

class WaveformDialog(QtWidgets.QDialog):
    def __init__(self, file_path: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Waveform Preview: {os.path.basename(file_path)}")
        self.resize(800, 400)
        layout = QtWidgets.QVBoxLayout(self)
        self.file_path = file_path

        if ENABLE_WAVEFORM_PREVIEW:
            self.figure, self.ax = plt.subplots()
            self.canvas = FigureCanvas(self.figure)
            layout.addWidget(self.canvas)
            # Use unified plotter
            WaveformPlotter.plot(self.file_path, self.ax)
            self.canvas.draw()
        else:
            label = QtWidgets.QLabel(
                "Waveform preview is not available due to missing dependencies."
            )
            layout.addWidget(label)

