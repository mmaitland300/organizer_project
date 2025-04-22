# services/analysis_engine.py
"""
Provides the AnalysisEngine class with methods to extract advanced audio features
using librosa.
"""

import logging
import os
from typing import Any, Dict, Optional
from config.settings import N_MFCC, ALL_FEATURE_KEYS # Import N_MFCC and feature list
# --- Dependency Checks ---
# Check for numpy first as librosa depends on it
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None # Assign None so later checks fail cleanly
    NUMPY_AVAILABLE = False

# Check for librosa
try:
    # Only import if numpy is available
    if NUMPY_AVAILABLE:
        import librosa
        import librosa.feature
        LIBROSA_AVAILABLE = True
    else:
        librosa = None
        LIBROSA_AVAILABLE = False
except ImportError:
    librosa = None
    LIBROSA_AVAILABLE = False

# --- Logging Setup ---
logger = logging.getLogger(__name__)
if not LIBROSA_AVAILABLE or not NUMPY_AVAILABLE:
    logger.error("librosa or numpy not installed. Advanced audio analysis will be disabled.")

# --- Optional: FFmpeg Path (Commented out - Less portable, rely on librosa's backend) ---
# If you specifically need FFmpeg and know its path, uncomment and adjust.
ffmpeg_bin = r"C:\ffmpeg\bin" # Example Path
if ffmpeg_bin not in os.environ.get("PATH", ""):
    logger.info(f"Attempting to add FFmpeg path: {ffmpeg_bin}")
    os.environ["PATH"] += os.pathsep + ffmpeg_bin
logger.debug("Current PATH relevant to AnalysisEngine: %s", os.environ.get("PATH"))


class AnalysisEngine:
    """
    Provides static methods for analyzing audio file features.
    """

    @staticmethod
    def analyze_audio_features(
        file_path: str, max_duration: float = 60.0 # Removed n_mfcc arg, use constant from settings
    ) -> Dict[str, Optional[float]]:
        """
        Loads up to a specified duration of an audio file (in mono) and computes
        various audio features using librosa.

        Features Computed (returns None for a feature if calculation fails):
        - brightness (spectral_centroid mean)
        - loudness_rms (root mean square energy mean)
        - zcr_mean (zero-crossing rate mean)
        - spectral_contrast_mean (mean of spectral contrast bands)
        - mfcc1_mean ... mfccN_mean (mean of the first 'n_mfcc' coefficients)
        - stereo_width (currently hardcoded to 0.0 as audio is loaded mono)

        Args:
            file_path (str): Path to the audio file.
            max_duration (float): Maximum duration (in seconds) to load for analysis.
                                  Librosa might load slightly less depending on framing.
            n_mfcc (int): Number of MFCCs to compute.

        Returns:
            Dict[str, Optional[float]]: Dictionary containing computed feature names
                                        and their float values. Returns an empty
                                        dictionary if core dependencies (librosa, numpy)
                                        are missing or if loading fails entirely.
                                        Individual features might be None if their
                                        specific calculation fails.
        """
        # Use the N_MFCC constant imported from settings
        n_mfcc_to_use = N_MFCC

        if not librosa or not np:
            logger.warning("librosa/numpy not available. Skipping feature analysis.")
            # Return dict with expected keys, but all values None
            return {key: None for key in ALL_FEATURE_KEYS + ['bpm']} # ADD 'bpm' here

        # Initialize features dict with None for expected feature keys
        features: Dict[str, Optional[float]] = {key: None for key in ALL_FEATURE_KEYS}
        # Add placeholder for BPM, will be overwritten if calculated
        features['bpm'] = None

        load_duration = min(max_duration, 30.0)
        logger.debug(f"Analyzing first <= {load_duration}s of {file_path} for features and BPM")

        y: Optional[np.ndarray] = None
        sr: Optional[int] = None

        # --- Load Audio ---
        try:
            y, sr_loaded = librosa.load(
                file_path,
                sr=None,
                offset=0.0,
                duration=load_duration,
                mono=True,
                dtype=np.float32, # Requires numpy
            )
            sr = int(sr_loaded) if sr_loaded is not None else None
            if sr is None:
                 raise ValueError("Failed to determine sample rate during loading.")
            logger.debug(f"Loaded audio for {file_path} with sr={sr}, shape={y.shape if y is not None else 'None'}")
            # Check if audio data was actually loaded
            if y is None or y.size == 0:
                 logger.warning(f"Audio data loaded as None or empty for {file_path}. Cannot analyze.")
                 return features # Return dict with Nones

        except Exception as e:
            logger.error(f"Failed to load audio file {file_path}: {e}", exc_info=True)
            return features # Return dict with Nones

        # --- Feature Extraction ---

        # --- ADD BPM Calculation ---
        try:
            # Ensure 'y' is valid before passing to tempo
            if y is not None and sr is not None:
                 tempo = librosa.beat.tempo(y=y, sr=sr)
                 # Use float for consistency, handle None during save/display
                 bpm_val = float(tempo[0]) if tempo.size > 0 else None
                 features['bpm'] = bpm_val # Update the 'bpm' key
                 logger.debug(f"Calculated BPM for {file_path}: {bpm_val}")
            else:
                 logger.warning(f"Skipping BPM calculation for {file_path} due to missing audio data or sample rate.")
                 features['bpm'] = None # Ensure it's None if skipped
        except Exception as e:
            logger.warning(f"Could not compute BPM for {file_path}: {e}", exc_info=False)
            features['bpm'] = None # Ensure it's None on error
        # --- END BPM Calculation ---

        # --- Existing Feature Calculations ---
        # Check y and sr validity before proceeding with other features too
        if y is not None and sr is not None:
             # Brightness
            if 'brightness' in features:
                try:
                    centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
                    features["brightness"] = float(np.mean(centroid))
                except Exception as e:
                    logger.warning(f"Could not compute brightness for {file_path}: {e}", exc_info=False)

            # RMS Loudness
            if 'loudness_rms' in features:
                try:
                    rms_frames = librosa.feature.rms(y=y)[0]
                    features["loudness_rms"] = float(np.mean(rms_frames))
                except Exception as e:
                    logger.warning(f"Could not compute loudness_rms for {file_path}: {e}", exc_info=False)

            # Zero-Crossing Rate
            if 'zcr_mean' in features:
                try:
                    zcr = librosa.feature.zero_crossing_rate(y=y)
                    features["zcr_mean"] = float(np.mean(zcr))
                except Exception as e:
                    logger.warning(f"Could not compute zcr_mean for {file_path}: {e}", exc_info=False)

            # Spectral Contrast
            if 'spectral_contrast_mean' in features:
                try:
                    contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
                    features["spectral_contrast_mean"] = float(np.mean(contrast))
                except Exception as e:
                    logger.warning(f"Could not compute spectral_contrast_mean for {file_path}: {e}", exc_info=False)

            # MFCCs
            if f'mfcc1_mean' in features: # Check if MFCCs are expected
                try:
                    # Use the imported N_MFCC constant
                    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc_to_use)
                    mfcc_means = np.mean(mfccs, axis=1)
                    for i in range(n_mfcc_to_use):
                        key = f"mfcc{i+1}_mean"
                        if key in features: # Ensure the key is expected
                             features[key] = float(mfcc_means[i])
                except Exception as e:
                    logger.warning(f"Could not compute MFCCs for {file_path}: {e}", exc_info=False)
        else:
             logger.warning(f"Skipping feature calculations for {file_path} due to missing audio data or sample rate.")


        logger.debug(f"Finished feature analysis for {file_path}")
        return features
