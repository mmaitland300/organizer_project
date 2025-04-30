# FILE: services/analysis_engine.py
"""
Provides the AnalysisEngine class with methods to extract advanced audio features
using librosa, soundfile, and pyloudnorm, supporting cancellation.
"""

import logging
import sys # Add sys import
print(f"--- analysis_engine.py --- sys.path: {sys.path}") # Print path when imported

import os
import re
# *** Import Event type hint ***
from multiprocessing.synchronize import Event as MPEvent # Precise type hint
from typing import Any, Dict, Optional, Union, List # Added List

# Import Constants
try:
    # Import the correct name: ADDITIONAL_FEATURE_KEYS instead of NEW_FEATURE_KEYS
    from config.settings import N_MFCC, ALL_FEATURE_KEYS, ADDITIONAL_FEATURE_KEYS
    ALL_EXPECTED_KEYS = list(set(ALL_FEATURE_KEYS + ADDITIONAL_FEATURE_KEYS + ['bpm'])) # Use the correct name here too

except ImportError:
    logging.critical("Could not import settings. Analysis Engine may fail.")
    # Fallbacks
    ALL_FEATURE_KEYS = ['brightness', 'loudness_rms', 'zcr_mean', 'spectral_contrast_mean']
    ADDITIONAL_FEATURE_KEYS = ['bit_depth', 'loudness_lufs', 'pitch_hz', 'attack_time'] # Adjust fallback variable name if needed for consistency
    ALL_EXPECTED_KEYS = list(set(ALL_FEATURE_KEYS + ADDITIONAL_FEATURE_KEYS + ['bpm']))
    N_MFCC = 13

# Dependency Checks & Imports (ensure numpy is imported as np)
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    np = None
    NUMPY_AVAILABLE = False

try:
    if NUMPY_AVAILABLE:
        import librosa
        import librosa.feature
        import librosa.onset
        LIBROSA_AVAILABLE = True
    else:
        librosa = None
        LIBROSA_AVAILABLE = False
except ImportError:
    librosa = None
    LIBROSA_AVAILABLE = False

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    sf = None
    SOUNDFILE_AVAILABLE = False

try:
    import pyloudnorm as pyln
    PYLOUDNORM_AVAILABLE = True
except ImportError:
    pyln = None
    PYLOUDNORM_AVAILABLE = False


logger = logging.getLogger(__name__)
# Log missing dependencies status
if not NUMPY_AVAILABLE: logger.error("numpy not installed. Some analysis features disabled.")
if not LIBROSA_AVAILABLE: logger.error("librosa not installed. Most analysis features disabled.")
if not SOUNDFILE_AVAILABLE: logger.warning("soundfile not installed. Bit depth analysis disabled.")
if not PYLOUDNORM_AVAILABLE: logger.warning("pyloudnorm not installed. LUFS loudness analysis disabled.")


class AnalysisEngine:
    """ Provides static methods for analyzing audio file features. """

    @staticmethod
    def analyze_audio_features(
        file_path: str,
        max_duration: float = 15.0, # Reduced from 60/30 to 15 seconds
        cancel_event: Optional[MPEvent] = None
    ) -> Dict[str, Optional[Union[float, int]]]:
        """
        Loads audio (up to max_duration) and computes features, checking cancel_event.
        """
        # --- Initial Cancellation Check ---
        if cancel_event and cancel_event.is_set():
            logger.info(f"Analysis cancelled before starting: {os.path.basename(file_path)}")
            return {}

        n_mfcc_to_use = N_MFCC

        if not librosa or not np:
            logger.warning("Librosa/Numpy not available for analysis.")
            return {}

        features: Dict[str, Optional[Union[float, int]]] = {key: None for key in ALL_EXPECTED_KEYS}

        # *** Use the potentially shorter max_duration ***
        load_duration = max_duration # Use the passed/default value directly
        logger.debug(f"Analyzing first <= {load_duration}s of {os.path.basename(file_path)}")

        y: Optional[np.ndarray] = None
        sr: Optional[int] = None

        # --- Load Audio ---
        try:
            if cancel_event and cancel_event.is_set(): return {}
            y, sr_loaded = librosa.load( file_path, sr=None, offset=0.0, duration=load_duration, mono=True, dtype=np.float32,) # Use load_duration
            sr = int(sr_loaded) if sr_loaded is not None else None
            if sr is None: raise ValueError("Failed to determine sample rate.")
            if y is None or y.size == 0: raise ValueError("Loaded audio data is empty.")
            # logger.debug(f"Loaded audio for {os.path.basename(file_path)} sr={sr}, shape={y.shape}") # Less verbose

            if cancel_event and cancel_event.is_set():
                logger.info(f"Analysis cancelled after loading: {os.path.basename(file_path)}")
                return {}

        except Exception as e:
            logger.error(f"Failed to load audio file {os.path.basename(file_path)}: {e}", exc_info=False)
            return {}

        # --- Feature Extraction (with cancellation checks) ---

        # BPM
        if 'bpm' in features:
            if cancel_event and cancel_event.is_set(): return {}
            try:
                tempo = librosa.beat.tempo(y=y, sr=sr)
                features['bpm'] = float(tempo[0]) if tempo.size > 0 else None
            except Exception as e: logger.warning(f"BPM failed for {os.path.basename(file_path)}: {e}", exc_info=False); features['bpm'] = None

        # Brightness
        if 'brightness' in features:
            if cancel_event and cancel_event.is_set(): return {}
            try:
                centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
                features["brightness"] = float(np.mean(centroid))
            except Exception as e: logger.warning(f"Brightness failed for {os.path.basename(file_path)}: {e}", exc_info=False)

        # RMS Loudness
        if 'loudness_rms' in features:
            if cancel_event and cancel_event.is_set(): return {}
            try:
                rms_frames = librosa.feature.rms(y=y)[0]
                features["loudness_rms"] = float(np.mean(rms_frames))
            except Exception as e: logger.warning(f"Loudness_rms failed for {os.path.basename(file_path)}: {e}", exc_info=False)

        # Zero-Crossing Rate
        if 'zcr_mean' in features:
            if cancel_event and cancel_event.is_set(): return {}
            try:
                zcr = librosa.feature.zero_crossing_rate(y=y)
                features["zcr_mean"] = float(np.mean(zcr))
            except Exception as e: logger.warning(f"ZCR failed for {os.path.basename(file_path)}: {e}", exc_info=False)

        # Spectral Contrast
        if 'spectral_contrast_mean' in features:
            if cancel_event and cancel_event.is_set(): return {}
            try:
                # NOTE: Spectral contrast can be slow, ideal place for internal check if possible
                contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
                features["spectral_contrast_mean"] = float(np.mean(contrast))
            except Exception as e: logger.warning(f"Spectral Contrast failed for {os.path.basename(file_path)}: {e}", exc_info=False)

        # MFCCs
        if f'mfcc1_mean' in features: # Check if MFCCs are expected
            if cancel_event and cancel_event.is_set(): return {}
            try:
                mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc_to_use)
                # Check event again after potentially long MFCC calculation
                if cancel_event and cancel_event.is_set(): return {}
                mfcc_means = np.mean(mfccs, axis=1)
                for i in range(n_mfcc_to_use):
                    key = f"mfcc{i+1}_mean"
                    if key in features: features[key] = float(mfcc_means[i])
            except Exception as e: logger.warning(f"MFCCs failed for {os.path.basename(file_path)}: {e}", exc_info=False)

        # Bit Depth
        if 'bit_depth' in features:
            if cancel_event and cancel_event.is_set(): return {}
            if SOUNDFILE_AVAILABLE and sf is not None:
                try:
                    info = sf.info(file_path)
                    subtype_str = getattr(info, 'subtype_info', '') or ''
                    match = re.search(r'(\d+)', subtype_str)
                    bit_depth = int(match.group(1)) if match else None
                    if bit_depth is None and 'float' in info.subtype.lower(): bit_depth = 32
                    features['bit_depth'] = bit_depth
                except Exception as e: logger.warning(f"Bit depth failed for {os.path.basename(file_path)}: {e}", exc_info=False); features['bit_depth'] = None
            else: features['bit_depth'] = None

        # LUFS Loudness
        if 'loudness_lufs' in features:
            if cancel_event and cancel_event.is_set(): return {}
            if PYLOUDNORM_AVAILABLE and pyln is not None:
                try:
                    if np.any(y):
                         meter = pyln.Meter(sr)
                         integrated_loudness = meter.integrated_loudness(y)
                         features['loudness_lufs'] = float(integrated_loudness) if np.isfinite(integrated_loudness) else None
                    else: features['loudness_lufs'] = None
                except Exception as e: logger.warning(f"LUFS failed for {os.path.basename(file_path)}: {e}", exc_info=False); features['loudness_lufs'] = None
            else: features['loudness_lufs'] = None

        # Pitch (Hz)
        if 'pitch_hz' in features:
            if cancel_event and cancel_event.is_set(): return {}
            if LIBROSA_AVAILABLE and NUMPY_AVAILABLE:
                try:
                    # pyin can be relatively slow
                    f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'), sr=sr)
                    # Check event again after pyin
                    if cancel_event and cancel_event.is_set(): return {}
                    median_f0 = np.nanmedian(f0) if f0 is not None and np.any(np.isfinite(f0)) else None
                    features['pitch_hz'] = float(median_f0) if median_f0 is not None else None
                except Exception as e: logger.warning(f"Pitch failed for {os.path.basename(file_path)}: {e}", exc_info=False); features['pitch_hz'] = None
            else: features['pitch_hz'] = None

        # Attack Time
        if 'attack_time' in features:
            if cancel_event and cancel_event.is_set(): return {}
            if LIBROSA_AVAILABLE:
                try:
                    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
                    # Check event again after onset_strength
                    if cancel_event and cancel_event.is_set(): return {}
                    onsets_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units='frames')
                    first_onset_time = librosa.frames_to_time(onsets_frames[0], sr=sr) if len(onsets_frames) > 0 else None
                    features['attack_time'] = float(first_onset_time) if first_onset_time is not None else None
                except Exception as e: logger.warning(f"Attack time failed for {os.path.basename(file_path)}: {e}", exc_info=False); features['attack_time'] = None
            else: features['attack_time'] = None

        # Final check before returning
        if cancel_event and cancel_event.is_set():
             logger.info(f"Analysis cancelled just before returning: {os.path.basename(file_path)}")
             return {}

        logger.debug(f"Finished analysis for {os.path.basename(file_path)}")
        return features # Return the dictionary with calculated values (or None)