"""
WaveformDialog – displays a waveform preview for a given audio file using matplotlib.
"""

import os
from typing import Optional
from PyQt5 import QtWidgets
from config.settings import ENABLE_WAVEFORM_PREVIEW, librosa, plt, np, FigureCanvas

class WaveformDialog(QtWidgets.QDialog):
    def __init__(self, file_path: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Waveform Preview: {os.path.basename(file_path)}")
        self.resize(800, 400)
        layout = QtWidgets.QVBoxLayout(self)
        self.file_path = file_path
        if ENABLE_WAVEFORM_PREVIEW:
            self.figure = plt.figure()
            self.canvas = FigureCanvas(self.figure)
            layout.addWidget(self.canvas)
            self.plot_waveform()
        else:
            label = QtWidgets.QLabel("Waveform preview is not available due to missing dependencies.")
            layout.addWidget(label)
    
    def plot_waveform(self) -> None:
        try:
            y, sr = librosa.load(self.file_path, sr=None, mono=True)
            times = np.linspace(0, len(y) / sr, num=len(y))
            ax = self.figure.add_subplot(111)
            ax.clear()
            ax.plot(times, y)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            ax.set_title("Waveform")
            self.canvas.draw()
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Could not load waveform: {e}")
