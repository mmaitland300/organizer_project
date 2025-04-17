# services/analysis_engine.py
import os
import logging
import numpy as np
from typing import Dict, Any

# Ensure FFmpeg bin in PATH if needed
ffmpeg_bin = r"C:\ffmpeg\bin"
if ffmpeg_bin not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + ffmpeg_bin

logger = logging.getLogger(__name__)
logger.debug("Current PATH in AnalysisEngine: %s", os.environ.get("PATH"))

try:
    import librosa
except ImportError:
    librosa = None
    logger.error("librosa not installed. Advanced DSP unavailable.")

class AnalysisEngine:
    @staticmethod
    def analyze_audio_features(file_path: str, max_duration: float = 60.0) -> Dict[str, Any]:
        """
        Loads up to 30 seconds of audio in mono for memory safety,
        computes brightness (spectral centroid) and RMS loudness.
        Stereo width set to 0 (mono only).
        """
        features: Dict[str, Any] = {}
        if not librosa or not np:
            logger.warning("librosa/numpy not installed. Skipping advanced DSP.")
            return features

        duration = min(max_duration, 30.0)
        try:
            y, sr = librosa.load(
                file_path,
                sr=None,
                offset=0.0,
                duration=duration,
                mono=True,
                dtype=np.float32,
            )
            # Brightness (spectral centroid)
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            features['brightness'] = float(centroid.mean())

            # RMS loudness
            features['loudness_rms'] = float(np.sqrt(np.mean(y**2)))

            # Stereo width unavailable on mono load
            features['stereo_width'] = 0.0
        except Exception as e:
            logger.error(f"Error analyzing advanced features for {file_path}: {e}", exc_info=True)

        return features

    @staticmethod
    def _compute_rms(signal: 'np.ndarray') -> float:
        return float(np.sqrt(np.mean(signal**2)))

    @staticmethod
    def _compute_stereo_width(left: 'np.ndarray', right: 'np.ndarray') -> float:
        diff = left - right
        return float(np.sqrt(np.mean(diff**2)))

