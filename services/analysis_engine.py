# services/analysis_engine.py
import os
import logging
from typing import Dict, Any


# Explicitly ensure that the FFmpeg bin path is in the environment PATH.
# Replace the following with your actual ffmpeg bin location.
ffmpeg_bin = r"C:\ffmpeg\bin"
if ffmpeg_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + ffmpeg_bin

logger = logging.getLogger(__name__)
logger.debug("Current PATH in AnalysisEngine: " + os.environ.get("PATH", ""))

try:
    import librosa
    import numpy as np
except ImportError:
    librosa = None
    np = None
    logger.error("librosa or numpy could not be imported.")

class AnalysisEngine:
    @staticmethod
    def analyze_audio_features(file_path: str, max_duration: float = 60.0) -> Dict[str, Any]:
        """
        Loads up to 'max_duration' seconds of audio from file_path and calculates
        features like brightness (spectral centroid), RMS loudness, and stereo width.
        Returns a dictionary mapping feature names to numeric values.
        If any error occurs (such as NoBackendError), it logs the error and returns an empty dict.
        """
        features = {}
        if not librosa or not np:
            logger.warning("librosa/numpy not installed. Skipping advanced DSP.")
            return features

        # Ensure the FFmpeg path is in the current environment.
        ffmpeg_bin = r"C:\ffmpeg\bin"
        if ffmpeg_bin not in os.environ.get("PATH", ""):
            os.environ["PATH"] += os.pathsep + ffmpeg_bin
            logger.debug("FFmpeg path appended to PATH in analyze_audio_features.")

        logger.debug("Analyzing file: " + file_path)
        try:
            # Attempt to load audio using librosa.
            y, sr = librosa.load(file_path, sr=None, duration=max_duration, mono=False)
            if y.ndim == 1:
                y = y[np.newaxis, :]  # Ensure stereo shape consistency

            # Calculate spectral centroid as a proxy for brightness.
            y_mono = np.mean(y, axis=0)
            centroid = librosa.feature.spectral_centroid(y=y_mono, sr=sr)
            features["brightness"] = float(centroid.mean())

            # RMS loudness calculation.
            features["loudness_rms"] = float(np.sqrt(np.mean(y ** 2)))

            # Stereo width: if stereo, calculate the RMS difference between channels.
            if y.shape[0] >= 2:
                diff = y[0] - y[1]
                features["stereo_width"] = float(np.sqrt(np.mean(diff ** 2)))
            else:
                features["stereo_width"] = 0.0

        except Exception as e:
            logger.error(f"Error analyzing advanced features for {file_path}: {e}", exc_info=True)

        return features

    @staticmethod
    def _compute_rms(signal: 'np.ndarray') -> float:
        import numpy as np
        return float(np.sqrt(np.mean(signal**2)))

    @staticmethod
    def _compute_stereo_width(left: 'np.ndarray', right: 'np.ndarray') -> float:
        import numpy as np
        diff = left - right
        return float(np.sqrt(np.mean(diff**2)))
