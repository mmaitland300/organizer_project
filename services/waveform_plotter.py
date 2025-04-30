# services/waveform_plotter.py
"""
WaveformPlotter - utility for plotting downsampled audio waveforms.
"""

import logging
import os  # <<< Import the 'os' module
from typing import Any

import librosa
import numpy as np

logger = logging.getLogger(__name__)


class WaveformPlotter:
    @staticmethod
    def plot(file_path: str, ax: Any, max_points: int = 1000) -> None:
        """
        Plot downsampled waveform of audio file on the given matplotlib Axes,
        using the filename as the title.
        """
        try:
            y, sr = librosa.load(file_path, sr=None, mono=True)
            factor = max(1, int(len(y) / max_points))
            y_ds = y[::factor]
            times = np.linspace(0, len(y) / sr, num=len(y_ds))

            # Prepare filename for title
            base_filename = os.path.basename(file_path)  # <<< Get filename

            ax.clear()
            ax.plot(times, y_ds)
            ax.set_xlabel("Time (s)")
            ax.set_ylabel("Amplitude")
            # --- Modified Line ---
            ax.set_title(base_filename)  # <<< Use filename for title
            # --- End Modification ---

        except Exception as e:
            # Log the error but allow the calling UI to handle it if necessary
            logger.error(f"WaveformPlotter failed for {file_path}: {e}", exc_info=True)
            # Optionally re-raise, or clear the axes and display an error message
            ax.clear()
            ax.text(
                0.5,
                0.5,
                f"Error plotting:\n{os.path.basename(file_path)}",
                horizontalalignment="center",
                verticalalignment="center",
                transform=ax.transAxes,
                wrap=True,
                color="red",
            )
            # raise # Re-raising might crash the dialog, handle gracefully in UI if needed
