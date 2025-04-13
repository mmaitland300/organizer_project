# services/analysis_engine.py

import logging
from typing import Dict, Any

try:
    import librosa
    import numpy as np
except ImportError:
    librosa = None
    np = None

logger = logging.getLogger(__name__)

class AnalysisEngine:
    @staticmethod
    def analyze_audio_features(file_path: str, max_duration: float = 60.0) -> Dict[str, float]:
        """
        Returns a dict of numeric metrics (brightness, loudness_rms, stereo_width, etc.)
        E.g. { "brightness": 3000.5, "loudness_rms": 0.25, "stereo_width": 0.70 }
        """
        features = {}
        if not librosa or not np:
            logger.warning("librosa/numpy not installed. Skipping advanced DSP.")
            return features

        try:
            # Load up to max_duration seconds, keep stereo
            y, sr = librosa.load(file_path, sr=None, duration=max_duration, mono=False)
            if y.ndim == 1:
                y = y[np.newaxis, :]

            # 1) Brightness (spectral centroid)
            y_mono = np.mean(y, axis=0)
            centroid = librosa.feature.spectral_centroid(y=y_mono, sr=sr)
            features["brightness"] = float(centroid.mean())

            # 2) RMS loudness
            features["loudness_rms"] = AnalysisEngine._compute_rms(y)

            # 3) Stereo width
            if y.shape[0] == 2:
                features["stereo_width"] = AnalysisEngine._compute_stereo_width(y[0], y[1])
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
