# FILE: services/analysis_engine.py
"""
Provides the AnalysisEngine class with methods to extract advanced audio features
using librosa, soundfile, and pyloudnorm.
"""

import logging
import os
import re # Needed for bit depth regex
from typing import Any, Dict, Optional, Union

# --- Import Constants ---
# Import feature lists and N_MFCC from settings
# Adjust path if your structure differs
try:
    from config.settings import N_MFCC, ALL_FEATURE_KEYS
    # Define the NEW feature keys expected (these must also be added to settings.py)
    NEW_FEATURE_KEYS = ['bit_depth', 'loudness_lufs', 'pitch_hz', 'attack_time']
    # Combine old and new for initialization (ensure settings.py -> ALL_FEATURE_KEYS reflects this)
    ALL_EXPECTED_KEYS = ALL_FEATURE_KEYS + NEW_FEATURE_KEYS
except ImportError:
    logging.critical("Could not import settings. Analysis Engine may fail.")
    # Define fallbacks ONLY if running standalone for basic testing
    ALL_FEATURE_KEYS = ['brightness', 'loudness_rms', 'zcr_mean', 'spectral_contrast_mean']
    NEW_FEATURE_KEYS = ['bit_depth', 'loudness_lufs', 'pitch_hz', 'attack_time']
    ALL_EXPECTED_KEYS = ALL_FEATURE_KEYS + NEW_FEATURE_KEYS
    N_MFCC = 13


# --- Dependency Checks & Imports ---
# Check for numpy first
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

# Check for librosa (depends on numpy)
try:
    if NUMPY_AVAILABLE:
        import librosa
        import librosa.feature
        import librosa.onset # Needed for attack time
        LIBROSA_AVAILABLE = True
    else:
        librosa = None
        LIBROSA_AVAILABLE = False
except ImportError:
    librosa = None
    LIBROSA_AVAILABLE = False

# Check for soundfile (needed for bit depth)
try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    sf = None
    SOUNDFILE_AVAILABLE = False

# Check for pyloudnorm (needed for LUFS)
try:
    import pyloudnorm as pyln
    PYLOUDNORM_AVAILABLE = True
except ImportError:
    pyln = None
    PYLOUDNORM_AVAILABLE = False


# --- Logging Setup ---
logger = logging.getLogger(__name__)
if not NUMPY_AVAILABLE: logger.error("numpy not installed. Some analysis features disabled.")
if not LIBROSA_AVAILABLE: logger.error("librosa not installed. Most analysis features disabled.")
if not SOUNDFILE_AVAILABLE: logger.warning("soundfile not installed. Bit depth analysis disabled.")
if not PYLOUDNORM_AVAILABLE: logger.warning("pyloudnorm not installed. LUFS loudness analysis disabled.")


class AnalysisEngine:
    """
    Provides static methods for analyzing audio file features.
    """

    @staticmethod
    def analyze_audio_features(
        file_path: str, max_duration: float = 60.0
        # n_mfcc is now read from settings directly below
    ) -> Dict[str, Optional[float]]:
        """
        Loads audio and computes features: BPM, spectral, MFCCs, bit depth, LUFS, pitch, attack.

        Args:
            file_path (str): Path to the audio file.
            max_duration (float): Max duration (seconds) to load for CPU-intensive analysis.

        Returns:
            Dict[str, Optional[float]]: Dictionary containing computed feature names
                                        and their float/int values. Returns empty dict
                                        if core dependencies are missing or loading fails.
                                        Individual features are None if calculation fails.
        """
        # Use N_MFCC constant imported from settings
        n_mfcc_to_use = N_MFCC

        # Check core dependencies needed for most features
        if not librosa or not np:
            logger.warning("librosa/numpy not available. Skipping most feature analysis.")
            # Return dict with expected keys, all values None
            return {key: None for key in ALL_EXPECTED_KEYS}

        # Initialize features dictionary with None for ALL expected keys
        features: Dict[str, Optional[Union[float, int]]] = {key: None for key in ALL_EXPECTED_KEYS}

        # Limit loading duration for performance/memory
        load_duration = min(max_duration, 30.0) # 30s often sufficient for many features
        logger.debug(f"Analyzing first <= {load_duration}s of {file_path}")

        y: Optional[np.ndarray] = None
        sr: Optional[int] = None

        # --- Load Audio (using librosa) ---
        try:
            y, sr_loaded = librosa.load(
                file_path,
                sr=None, # Load original sample rate
                offset=0.0,
                duration=load_duration,
                mono=True, # Analyze in mono for consistency
                dtype=np.float32,
            )
            sr = int(sr_loaded) if sr_loaded is not None else None
            if sr is None: raise ValueError("Failed to determine sample rate.")
            if y is None or y.size == 0: raise ValueError("Loaded audio data is empty.")
            logger.debug(f"Loaded audio for {file_path} with sr={sr}, shape={y.shape}")

        except Exception as e:
            logger.error(f"Failed to load audio file {file_path}: {e}", exc_info=True)
            # Return features dict with None values if loading fails
            return features # All values will be None

        # --- Feature Extraction ---

        # BPM (Requires librosa)
        if 'bpm' in features: # Check if 'bpm' is an expected key (it should be from base columns)
            try:
                tempo = librosa.beat.tempo(y=y, sr=sr)
                features['bpm'] = float(tempo[0]) if tempo.size > 0 else None
            except Exception as e:
                logger.warning(f"Could not compute BPM for {file_path}: {e}", exc_info=False)
                features['bpm'] = None # Ensure None on error

        # Brightness (Requires librosa, numpy)
        if 'brightness' in features:
            try:
                centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
                features["brightness"] = float(np.mean(centroid))
            except Exception as e:
                logger.warning(f"Could not compute brightness for {file_path}: {e}", exc_info=False)

        # RMS Loudness (Requires librosa, numpy)
        if 'loudness_rms' in features:
            try:
                rms_frames = librosa.feature.rms(y=y)[0]
                features["loudness_rms"] = float(np.mean(rms_frames))
            except Exception as e:
                logger.warning(f"Could not compute loudness_rms for {file_path}: {e}", exc_info=False)

        # Zero-Crossing Rate (Requires librosa, numpy)
        if 'zcr_mean' in features:
            try:
                zcr = librosa.feature.zero_crossing_rate(y=y)
                features["zcr_mean"] = float(np.mean(zcr))
            except Exception as e:
                logger.warning(f"Could not compute zcr_mean for {file_path}: {e}", exc_info=False)

        # Spectral Contrast (Requires librosa, numpy)
        if 'spectral_contrast_mean' in features:
            try:
                contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
                features["spectral_contrast_mean"] = float(np.mean(contrast))
            except Exception as e:
                logger.warning(f"Could not compute spectral_contrast_mean for {file_path}: {e}", exc_info=False)

        # MFCCs (Requires librosa, numpy)
        # Check if the first MFCC key exists as a proxy
        if f'mfcc1_mean' in features:
            try:
                mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc_to_use)
                mfcc_means = np.mean(mfccs, axis=1)
                for i in range(n_mfcc_to_use):
                    key = f"mfcc{i+1}_mean"
                    if key in features: # Check if this specific MFCC key is expected
                         features[key] = float(mfcc_means[i])
            except Exception as e:
                logger.warning(f"Could not compute MFCCs for {file_path}: {e}", exc_info=False)


        # --- New: Bit Depth (Requires soundfile, re) ---
        if 'bit_depth' in features:
            if SOUNDFILE_AVAILABLE and sf is not None:
                try:
                    info = sf.info(file_path)
                    # Extract number from subtype string (e.g., 'PCM_16', 'FLOAT')
                    subtype_str = getattr(info, 'subtype_info', '') or ''
                    match = re.search(r'(\d+)', subtype_str)
                    features['bit_depth'] = int(match.group(1)) if match else None
                    # Could add fallback for 'FLOAT' -> 32?
                    if features['bit_depth'] is None and 'float' in info.subtype.lower():
                         features['bit_depth'] = 32 # Common convention for float
                except ImportError: # Should not happen if SOUNDFILE_AVAILABLE is True, but safety
                     logger.error("Soundfile import failed unexpectedly during bit depth check.")
                     features['bit_depth'] = None
                except Exception as e:
                    logger.warning(f"Could not determine bit depth for {file_path}: {e}", exc_info=False)
                    features['bit_depth'] = None
            else:
                logger.debug("Skipping bit depth: soundfile library not available.")
                features['bit_depth'] = None

        # --- New: Loudness (Integrated LUFS) (Requires pyloudnorm) ---
        if 'loudness_lufs' in features:
            if PYLOUDNORM_AVAILABLE and pyln is not None and sr is not None:
                try:
                    # Ensure data is suitable for LUFS (not all zeros)
                    if np.any(y):
                         meter = pyln.Meter(sr) # Create loudness meter
                         # Calculate integrated loudness
                         integrated_loudness = meter.integrated_loudness(y)
                         # Check for -inf results which can occur for silence/very low levels
                         features['loudness_lufs'] = float(integrated_loudness) if np.isfinite(integrated_loudness) else None
                    else:
                         logger.debug(f"Skipping LUFS calculation for {file_path}: audio data is silent.")
                         features['loudness_lufs'] = None
                except ImportError:
                     logger.error("pyloudnorm import failed unexpectedly during LUFS check.")
                     features['loudness_lufs'] = None
                except Exception as e:
                    logger.warning(f"Could not compute LUFS loudness for {file_path}: {e}", exc_info=False)
                    features['loudness_lufs'] = None
            else:
                logger.debug("Skipping LUFS loudness: pyloudnorm library not available or sample rate missing.")
                features['loudness_lufs'] = None

        # --- New: Pitch (Hz) using librosa.pyin (Requires librosa, numpy) ---
        if 'pitch_hz' in features:
            # Check dependencies again just in case, though covered at start
            if LIBROSA_AVAILABLE and NUMPY_AVAILABLE and librosa is not None and np is not None and sr is not None:
                try:
                    # pyin estimates fundamental frequency (F0)
                    f0, voiced_flag, voiced_probs = librosa.pyin(
                        y,
                        fmin=librosa.note_to_hz('C2'), # Reasonable lower bound
                        fmax=librosa.note_to_hz('C7'), # Reasonable upper bound
                        sr=sr
                    )
                    # Calculate the median of detected pitches, ignoring NaNs
                    # Use nanmedian to be robust against frames where pitch isn't detected
                    median_f0 = np.nanmedian(f0) if f0 is not None and np.any(np.isfinite(f0)) else None
                    features['pitch_hz'] = float(median_f0) if median_f0 is not None else None
                except ImportError:
                     logger.error("librosa/numpy import failed unexpectedly during pitch check.")
                     features['pitch_hz'] = None
                except Exception as e:
                    logger.warning(f"Could not compute pitch (pyin) for {file_path}: {e}", exc_info=False)
                    features['pitch_hz'] = None
            else:
                 logger.debug("Skipping pitch detection: librosa/numpy not available or sample rate missing.")
                 features['pitch_hz'] = None

        # --- New: Attack Time (first onset) (Requires librosa) ---
        if 'attack_time' in features:
            if LIBROSA_AVAILABLE and librosa is not None and sr is not None:
                try:
                    # Calculate a standard onset strength envelope
                    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
                    # Detect onset times from the envelope
                    # Use wait=1, pre_avg=1, post_avg=1, post_max=1 for potentially faster detection
                    # Default units='frames', convert later if needed, or use units='time'
                    onsets_frames = librosa.onset.onset_detect(
                        onset_envelope=onset_env,
                        sr=sr,
                        units='frames', # Get frame indices first
                        # Optional parameters for tuning:
                        # wait=1, pre_avg=1, post_avg=1, post_max=1, delta=0.1, backtrack=False
                    )
                    # Convert first onset frame to time (seconds)
                    first_onset_time = librosa.frames_to_time(onsets_frames[0], sr=sr) if len(onsets_frames) > 0 else None
                    features['attack_time'] = float(first_onset_time) if first_onset_time is not None else None
                except ImportError:
                     logger.error("librosa import failed unexpectedly during attack time check.")
                     features['attack_time'] = None
                except Exception as e:
                    logger.warning(f"Could not compute attack time for {file_path}: {e}", exc_info=False)
                    features['attack_time'] = None
            else:
                 logger.debug("Skipping attack time: librosa not available or sample rate missing.")
                 features['attack_time'] = None

        # --- Final Logging & Return ---
        logger.debug(f"Finished feature analysis for {file_path}")
        # Log calculated values for debugging
        logger.debug(f"Calculated features for {os.path.basename(file_path)}: {features}")
        return features