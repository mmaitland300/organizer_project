# services/waveform_plotter.py
"""
WaveformPlotter – utility for plotting downsampled audio waveforms.
"""

import logging
from typing import Any

import librosa
import numpy as np

logger = logging.getLogger(__name__)


class WaveformPlotter:
    @staticmethod
    def plot(file_path: str, ax: Any, max_points: int = 1000) -> None:
        """
        Plot downsampled waveform of audio file on the given matplotlib Axes.
        """
        try:
            y, sr = librosa.load(file_path, sr=None, mono=True)
            factor = max(1, int(len(y) / max_points))
            y_ds = y[::factor]
            times = np.linspace(0, len(y) / sr, num=len(y_ds))
            ax.clear()
            ax.plot(times, y_ds)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            ax.set_title("Waveform")
        except Exception as e:
            logger.error(f"WaveformPlotter failed for {file_path}: {e}")
            raise
