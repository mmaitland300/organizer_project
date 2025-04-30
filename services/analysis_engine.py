# FILE: services/analysis_engine.py
"""
Provides the AnalysisEngine class with methods to extract advanced audio features
using librosa, soundfile, and pyloudnorm, supporting cancellation.
Leverages SpectrogramService for efficient spectrogram calculation and caching.
"""

import logging
import sys

# print(f"--- analysis_engine.py --- sys.path: {sys.path}") # Optional debug print

import math
import os
import re
from multiprocessing.synchronize import Event as MPEvent  # Precise type hint
from typing import Any, Dict, Optional, Union, List

# --- Application Imports ---
from services.spectrogram_service import SpectrogramService

# Import Constants from settings
try:
    from config.settings import N_MFCC, ALL_FEATURE_KEYS, ADDITIONAL_FEATURE_KEYS

    # Combine all expected feature keys for initialization
    ALL_EXPECTED_KEYS = list(set(["bpm"] + ALL_FEATURE_KEYS + ADDITIONAL_FEATURE_KEYS))
except ImportError:
    logging.critical("Could not import settings. Analysis Engine may fail.")
    # Define minimal fallbacks ONLY if settings import fails
    ALL_FEATURE_KEYS = [
        "brightness",
        "loudness_rms",
        "zcr_mean",
        "spectral_contrast_mean",
    ]
    ADDITIONAL_FEATURE_KEYS = ["bit_depth", "loudness_lufs", "pitch_hz", "attack_time"]
    ALL_EXPECTED_KEYS = list(set(["bpm"] + ALL_FEATURE_KEYS + ADDITIONAL_FEATURE_KEYS))
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
if not NUMPY_AVAILABLE:
    logger.error("numpy not installed. Some analysis features disabled.")
if not LIBROSA_AVAILABLE:
    logger.error("librosa not installed. Most analysis features disabled.")
if not SOUNDFILE_AVAILABLE:
    logger.warning("soundfile not installed. Bit depth analysis disabled.")
if not PYLOUDNORM_AVAILABLE:
    logger.warning("pyloudnorm not installed. LUFS loudness analysis disabled.")


class AnalysisEngine:
    """
    Provides static methods for analyzing audio file features.
    Uses SpectrogramService for STFT-based features.
    """

    @staticmethod
    def analyze_audio_features(
        file_path: str,
        max_duration: float = 15.0,
        cancel_event: Optional[MPEvent] = None,
        spectrogram_service_instance: Optional[SpectrogramService] = None,
    ) -> Dict[str, Optional[Union[float, int]]]:
        """
        Calculates various audio features for the given file path.

        Leverages SpectrogramService to get pre-computed spectrograms and raw audio data.
        Features requiring spectrograms (e.g., brightness, contrast, MFCCs) use the
        service's output. Features requiring raw audio (e.g., BPM, RMS, ZCR, pitch,
        attack, LUFS) use the 'y' array returned by the service. Bit depth uses
        soundfile directly on the path.

        Args:
            file_path (str): Absolute path to the audio file.
            max_duration (float): Maximum duration (in seconds) of audio to load
                                  and analyze. Defaults to 15.0.
            cancel_event (Optional[MPEvent]): A multiprocessing Event object to
                                              check for cancellation requests.
            spectrogram_service_instance (Optional[SpectrogramService]): An optional
                instance of SpectrogramService. If provided, it's used directly.
                If None, a new instance is created internally. Useful for testing.

        Returns:
            Dict[str, Optional[Union[float, int]]]: A dictionary where keys are
                feature names (e.g., 'bpm', 'brightness', 'mfcc1_mean') and values
                are the calculated feature values (float or int) or None if the
                feature could not be calculated or an error occurred. Returns an
                empty dictionary if critical dependencies are missing or initial
                data retrieval fails.
        """
        # --- Initial Cancellation Check ---
        if cancel_event and cancel_event.is_set():
            logger.info(
                f"Analysis cancelled before starting: {os.path.basename(file_path)}"
            )
            return {}

        # --- Dependency Check ---
        if not NUMPY_AVAILABLE or not LIBROSA_AVAILABLE:
            logger.error("AnalysisEngine cannot proceed: Missing numpy or librosa.")
            return {}

        # Initialize features dictionary with None values
        features: Dict[str, Optional[Union[float, int]]] = {
            key: None for key in ALL_EXPECTED_KEYS
        }
        n_mfcc_to_use = N_MFCC  # Number of MFCCs to compute

        # --- Get SpectrogramService instance ---
        the_service: SpectrogramService
        try:
            if spectrogram_service_instance:
                the_service = spectrogram_service_instance
                logger.debug("Using provided SpectrogramService instance.")
            else:
                # Create internal instance; relies on static cached method within service
                the_service = SpectrogramService()
                logger.debug("Created internal SpectrogramService instance.")
        except ImportError as e:
            logger.error(
                f"Failed to instantiate SpectrogramService (missing dependencies?): {e}"
            )
            return {}

        # --- Get Spectrogram and Audio Data ---
        logger.debug(
            f"Getting spectrogram data for first <= {max_duration}s of {os.path.basename(file_path)}"
        )
        try:
            spec_data = the_service.get_spectrogram_data(
                file_path, load_duration=max_duration
            )
        except Exception as spec_e:
            logger.error(
                f"Unexpected error calling get_spectrogram_data for {os.path.basename(file_path)}: {spec_e}",
                exc_info=True,
            )
            return {}  # Cannot proceed without data

        # --- Validate Service Result ---
        if spec_data.get("error"):
            logger.error(
                f"SpectrogramService failed for {os.path.basename(file_path)}: {spec_data['error']}"
            )
            return {}
        if not isinstance(spec_data.get("sr"), int) or spec_data.get("y") is None:
            logger.error(
                f"SpectrogramService returned invalid data (missing sr or y) for {os.path.basename(file_path)}"
            )
            return {}

        # Extract data needed for features (ensure type safety where possible)
        y: np.ndarray = spec_data["y"]  # type: ignore
        sr: int = spec_data["sr"]
        S_magnitude: Optional[np.ndarray] = spec_data.get("magnitude")  # type: ignore
        S_mel: Optional[np.ndarray] = spec_data.get("mel")  # type: ignore
        # hop_length = spec_data.get('hop_length') # Uncomment if needed

        # --- Feature Extraction (with cancellation checks interspersed) ---
        basename = os.path.basename(file_path)  # For logging clarity

        # BPM (Uses y)
        if "bpm" in features:
            if cancel_event and cancel_event.is_set():
                return {}
            try:
                # Consider using a different tempo estimation algorithm if needed
                tempo_result = librosa.beat.tempo(y=y, sr=sr)
                # tempo returns an array, potentially with multiple estimates
                features["bpm"] = (
                    float(tempo_result[0]) if tempo_result.size > 0 else None
                )
            except Exception as e:
                logger.warning(f"BPM failed for {basename}: {e}", exc_info=False)
                features["bpm"] = None

        # Brightness (Uses S_magnitude)
        if "brightness" in features:
            if cancel_event and cancel_event.is_set():
                return {}
            try:
                if S_magnitude is not None and S_magnitude.size > 0:
                    centroid = librosa.feature.spectral_centroid(S=S_magnitude, sr=sr)
                    features["brightness"] = float(
                        np.mean(centroid[np.isfinite(centroid)])
                    )  # Filter non-finite values
                else:
                    logger.warning(
                        f"Magnitude spectrogram missing or empty for brightness: {basename}"
                    )
            except Exception as e:
                logger.warning(f"Brightness failed for {basename}: {e}", exc_info=False)

        # RMS Loudness (Uses y)
        if "loudness_rms" in features:
            if cancel_event and cancel_event.is_set():
                return {}
            try:
                # rms function returns a 2D array (1, n_frames), access first row
                rms_frames = librosa.feature.rms(y=y)[0]
                # Filter out potential NaNs or Infs before mean calculation
                finite_rms = rms_frames[np.isfinite(rms_frames)]
                features["loudness_rms"] = (
                    float(np.mean(finite_rms)) if finite_rms.size > 0 else None
                )
            except Exception as e:
                logger.warning(
                    f"Loudness_rms failed for {basename}: {e}", exc_info=False
                )

        # Zero-Crossing Rate (Uses y)
        if "zcr_mean" in features:
            if cancel_event and cancel_event.is_set():
                return {}
            try:
                zcr = librosa.feature.zero_crossing_rate(y=y)[0]  # Access first row
                finite_zcr = zcr[np.isfinite(zcr)]
                features["zcr_mean"] = (
                    float(np.mean(finite_zcr)) if finite_zcr.size > 0 else None
                )
            except Exception as e:
                logger.warning(f"ZCR failed for {basename}: {e}", exc_info=False)

        # Spectral Contrast (Uses S_magnitude)
        if "spectral_contrast_mean" in features:
            if cancel_event and cancel_event.is_set():
                return {}
            try:
                if S_magnitude is not None and S_magnitude.size > 0:
                    contrast = librosa.feature.spectral_contrast(S=S_magnitude, sr=sr)
                    # Check event again after potentially slow calculation
                    if cancel_event and cancel_event.is_set():
                        return {}
                    finite_contrast = contrast[np.isfinite(contrast)]
                    features["spectral_contrast_mean"] = (
                        float(np.mean(finite_contrast))
                        if finite_contrast.size > 0
                        else None
                    )
                else:
                    logger.warning(
                        f"Magnitude spectrogram missing or empty for spectral contrast: {basename}"
                    )
            except Exception as e:
                logger.warning(
                    f"Spectral Contrast failed for {basename}: {e}", exc_info=False
                )
                features["spectral_contrast_mean"] = None

        # MFCCs (Uses S_mel)
        if f"mfcc1_mean" in features:  # Check if MFCCs are expected
            if cancel_event and cancel_event.is_set():
                return {}
            try:
                if S_mel is not None and S_mel.size > 0:
                    # Convert Mel spectrogram to dB scale, which is typical input for MFCC
                    S_mel_db = librosa.power_to_db(S_mel, ref=np.max)
                    mfccs = librosa.feature.mfcc(
                        S=S_mel_db, sr=sr, n_mfcc=n_mfcc_to_use
                    )
                    # Check event again after potentially long MFCC calculation
                    if cancel_event and cancel_event.is_set():
                        return {}
                    # Calculate mean for each MFCC coefficient, handling potential NaNs/Infs
                    for i in range(
                        min(n_mfcc_to_use, mfccs.shape[0])
                    ):  # Iterate over actual number of coefficients calculated
                        key = f"mfcc{i+1}_mean"
                        if key in features:
                            finite_coeffs = mfccs[i, np.isfinite(mfccs[i, :])]
                            features[key] = (
                                float(np.mean(finite_coeffs))
                                if finite_coeffs.size > 0
                                else None
                            )
                else:
                    logger.warning(
                        f"Mel spectrogram missing or empty for MFCC calculation: {basename}"
                    )
            except Exception as e:
                logger.warning(f"MFCCs failed for {basename}: {e}", exc_info=False)

        # Bit Depth (Uses file_path via soundfile)
        if "bit_depth" in features:
            if cancel_event and cancel_event.is_set():
                return {}
            if SOUNDFILE_AVAILABLE and sf is not None:
                try:
                    # Consider caching sf.info if called very frequently, though it's usually fast
                    info = sf.info(file_path)
                    subtype_str = getattr(info, "subtype_info", "") or ""
                    match = re.search(r"(\d+)", subtype_str)  # Extract digits
                    bit_depth_val = int(match.group(1)) if match else None
                    # Handle float formats (often represented as 32-bit or 64-bit float)
                    if bit_depth_val is None and "float" in info.subtype.lower():
                        bit_depth_val = (
                            32  # Assume 32-bit float if subtype indicates float
                        )
                    features["bit_depth"] = bit_depth_val
                except Exception as e:
                    logger.warning(
                        f"Bit depth analysis failed for {basename}: {e}", exc_info=False
                    )
                    features["bit_depth"] = None
            else:
                logger.debug("Soundfile not available, skipping bit depth.")
                features["bit_depth"] = None

        # LUFS Loudness (Uses y via pyloudnorm)
        if "loudness_lufs" in features:
            if cancel_event and cancel_event.is_set():
                return {}
            if PYLOUDNORM_AVAILABLE and pyln is not None:
                try:
                    # Ensure audio data is not silent or empty
                    if np.any(y):
                        meter = pyln.Meter(sr)  # Create BS.1770 meter
                        integrated_loudness = meter.integrated_loudness(y)
                        # Check if result is finite (can be -inf for silence)
                        features["loudness_lufs"] = (
                            float(integrated_loudness)
                            if np.isfinite(integrated_loudness)
                            else None
                        )
                    else:
                        logger.debug(
                            f"Audio data empty or silent, skipping LUFS for {basename}"
                        )
                        features["loudness_lufs"] = None
                except Exception as e:
                    logger.warning(
                        f"LUFS calculation failed for {basename}: {e}", exc_info=False
                    )
                    features["loudness_lufs"] = None
            else:
                logger.debug("pyloudnorm not available, skipping LUFS.")
                features["loudness_lufs"] = None

        # Pitch (Hz) (Uses y via librosa.pyin)
        if "pitch_hz" in features:
            if cancel_event and cancel_event.is_set():
                return {}
            # Note: pyin requires numpy and librosa
            try:
                # pyin can be computationally intensive
                # fmin/fmax help focus the search range
                f0, voiced_flag, voiced_probs = librosa.pyin(
                    y,
                    fmin=librosa.note_to_hz("C2"),
                    fmax=librosa.note_to_hz("C7"),
                    sr=sr,
                )
                # Check event again after pyin
                if cancel_event and cancel_event.is_set():
                    return {}
                # Calculate median pitch, ignoring unvoiced frames (where f0 is NaN)
                finite_f0 = f0[np.isfinite(f0)]
                median_f0 = np.median(finite_f0) if finite_f0.size > 0 else None
                features["pitch_hz"] = (
                    float(median_f0) if median_f0 is not None else None
                )
            except Exception as e:
                logger.warning(
                    f"Pitch (pyin) failed for {basename}: {e}", exc_info=False
                )
                features["pitch_hz"] = None

        # Attack Time (Uses y via librosa.onset)
        if "attack_time" in features:
            if cancel_event and cancel_event.is_set():
                return {}
            try:
                # Calculate onset strength envelope
                onset_env = librosa.onset.onset_strength(y=y, sr=sr)
                # Check event again
                if cancel_event and cancel_event.is_set():
                    return {}
                # Detect onset events (frame indices)
                # Parameters like wait, pre/post_avg/max can tune sensitivity
                onsets_frames = librosa.onset.onset_detect(
                    onset_envelope=onset_env,
                    sr=sr,
                    units="frames",
                    wait=1,
                    pre_avg=1,
                    post_avg=1,
                    pre_max=1,
                    post_max=1,
                )  # Use librosa defaults
                # Convert first detected onset frame to time (seconds)
                first_onset_time_sec = (
                    librosa.frames_to_time(onsets_frames[0], sr=sr)
                    if len(onsets_frames) > 0
                    else None
                )
                features["attack_time"] = (
                    float(first_onset_time_sec)
                    if first_onset_time_sec is not None
                    else None
                )
            except Exception as e:
                logger.warning(
                    f"Attack time failed for {basename}: {e}", exc_info=False
                )
                features["attack_time"] = None

        # --- Final Cancellation Check ---
        if cancel_event and cancel_event.is_set():
            logger.info(f"Analysis cancelled just before returning: {basename}")
            return {}

        logger.debug(f"Finished analysis for {basename}")
        return features  # Return the dictionary with calculated or None values
