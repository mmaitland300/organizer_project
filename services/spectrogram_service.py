# Filename: services/spectrogram_service.py
# New File

import functools
import logging
import os
from typing import (  # For TypeAlias if needed
    TYPE_CHECKING,
    Any,
    Dict,
    Optional,
    Tuple,
    Type,
)

# Dependency Checks & Imports
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore[assignment] # Runtime assignment
    NUMPY_AVAILABLE = False

try:
    if NUMPY_AVAILABLE:
        import librosa
        import librosa.feature

        LIBROSA_AVAILABLE = True
    else:
        librosa = None  # type: ignore[assignment]
        LIBROSA_AVAILABLE = False
except ImportError:
    librosa = None  # type: ignore[assignment]
    LIBROSA_AVAILABLE = False

# Import settings constants
try:
    from config.settings import (
        SPECTROGRAM_CACHE_SIZE,
        STFT_HOP_LENGTH,
        STFT_N_FFT,
        STFT_WIN_LENGTH,
        STFT_WINDOW,
    )
except ImportError:
    logging.critical("Could not import STFT settings. Spectrogram Service may fail.")
    # Define minimal fallbacks
    STFT_N_FFT = 2048
    STFT_HOP_LENGTH = 512
    STFT_WIN_LENGTH = None
    STFT_WINDOW = "hann"
    SPECTROGRAM_CACHE_SIZE = 1  # Minimal cache on error

logger = logging.getLogger(__name__)

# Log dependency status
if not NUMPY_AVAILABLE:
    logger.error("numpy not installed. SpectrogramService disabled.")
if not LIBROSA_AVAILABLE:
    logger.error("librosa not installed. SpectrogramService disabled.")


class SpectrogramService:
    """
    Service for calculating and caching spectrogram data (Magnitude, Power, Mel).
    Uses librosa for calculations and functools.lru_cache for in-memory caching.
    """

    def __init__(self):
        """Initializes the SpectrogramService."""
        if not NUMPY_AVAILABLE or not LIBROSA_AVAILABLE:
            raise ImportError(
                "SpectrogramService requires numpy and librosa to be installed."
            )
        logger.info(
            f"SpectrogramService initialized with cache size: {SPECTROGRAM_CACHE_SIZE}"
        )
        # Clear cache upon initialization if desired (e.g., for testing or specific lifecycle)
        self._compute_spectrogram_data.cache_clear()

    @staticmethod
    @functools.lru_cache(maxsize=SPECTROGRAM_CACHE_SIZE)
    def _compute_spectrogram_data(
        file_path: str,
        n_fft: int,
        hop_length: int,
        win_length: Optional[int],
        window: str,
        load_duration: Optional[float] = 30.0,  # Optional: Limit loading duration
    ) -> Dict[str, Any]:
        """
        Private static method that performs the actual audio loading and STFT calculation.
        Results are cached based on input arguments.
        """
        logger.debug(
            f"Computing spectrogram for: {os.path.basename(file_path)} with params: n_fft={n_fft}, hop={hop_length}, win={win_length}, window='{window}'"
        )
        results: Dict[str, Any] = {
            "y": None,  # <<< ADDED: To store loaded audio
            "magnitude": None,
            "power": None,
            "mel": None,
            "sr": None,
            "n_fft": n_fft,
            "hop_length": hop_length,
            "win_length": (
                win_length if win_length is not None else n_fft
            ),  # Store actual win_length used
            "window": window,
            "error": None,
        }
        try:
            # Ensure file exists before trying to load
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Audio file not found: {file_path}")

            y, sr = librosa.load(
                file_path,
                sr=None,  # Load native sample rate
                mono=True,
                duration=load_duration,
                dtype=np.float32,
            )
            results["sr"] = sr
            results["y"] = y  # Store loaded audio

            # Compute Short-Time Fourier Transform (STFT)
            S_complex = librosa.stft(
                y=y,
                n_fft=n_fft,
                hop_length=hop_length,
                win_length=win_length,
                window=window,
            )

            # Compute Magnitude Spectrogram
            S_magnitude = np.abs(S_complex)
            results["magnitude"] = S_magnitude

            # Compute Power Spectrogram
            # S_power = S_magnitude**2 # Optional: Compute if needed later
            # results['power'] = S_power

            # Compute Mel Spectrogram (often used for features like MFCCs)
            # n_mels can be added as a parameter if needed
            S_mel = librosa.feature.melspectrogram(
                S=S_magnitude**2,  # Pass power spectrogram to melspectrogram
                sr=sr,
                n_fft=n_fft,
                hop_length=hop_length,
                win_length=win_length,
                window=window,
                # n_mels=128 # Default is 128
            )
            results["mel"] = S_mel
            logger.debug(
                f"Successfully computed spectrogram for {os.path.basename(file_path)}"
            )

        except FileNotFoundError as fnf_err:
            logger.error(
                f"File not found error during spectrogram calculation: {fnf_err}"
            )
            results["error"] = str(fnf_err)
        except Exception as e:
            logger.error(
                f"Error computing spectrogram for {file_path}: {e}", exc_info=True
            )
            results["error"] = f"Calculation Error: {e}"

        return results

    def get_spectrogram_data(
        self,
        file_path: str,
        load_duration: Optional[float] = 30.0,  # Duration limit for loading
        **stft_params_override: Any,
    ) -> Dict[str, Any]:
        """
        Retrieves spectrogram data for a given file path.
        Uses cached results if available for the same file and parameters.

        Args:
            file_path (str): Path to the audio file.
            load_duration (Optional[float]): Max duration to load (default 30s).
            **stft_params_override: Keyword arguments to override default STFT parameters
                                     (n_fft, hop_length, win_length, window).

        Returns:
            Dict[str, Any]: Dictionary containing spectrogram data ('magnitude', 'mel', 'sr', etc.)
                            or an 'error' key if calculation failed. Returns empty dict if
                            dependencies (numpy, librosa) are missing.
        """
        if not NUMPY_AVAILABLE or not LIBROSA_AVAILABLE:
            logger.warning(
                "SpectrogramService dependencies not met. Returning empty dict."
            )
            return {"error": "Missing dependencies (numpy or librosa)"}

        # Resolve STFT parameters: defaults overridden by kwargs
        n_fft = stft_params_override.get("n_fft", STFT_N_FFT)
        hop_length = stft_params_override.get("hop_length", STFT_HOP_LENGTH)
        # Handle win_length potentially being None
        win_length_override = stft_params_override.get("win_length", "DEFAULT_SENTINEL")
        win_length = (
            STFT_WIN_LENGTH
            if win_length_override == "DEFAULT_SENTINEL"
            else win_length_override
        )

        window = stft_params_override.get("window", STFT_WINDOW)

        # Ensure file path is absolute for consistent caching
        abs_file_path = os.path.abspath(file_path)

        # Call the cached static method
        # Pass parameters explicitly as arguments for lru_cache
        results = self._compute_spectrogram_data(
            file_path=abs_file_path,
            n_fft=n_fft,
            hop_length=hop_length,
            win_length=win_length,  # Pass resolved value (can be None)
            window=window,
            load_duration=load_duration,
        )

        # Optionally check for errors in the results and log/handle them
        if results.get("error"):
            logger.warning(
                f"Spectrogram data retrieval failed for {os.path.basename(file_path)}: {results['error']}"
            )
            # Decide return strategy: return dict with error, or empty dict?
            # Returning dict with error key is more informative.

        return results

    def get_cache_info(self):
        """Returns information about the LRU cache."""
        if not hasattr(self, "_compute_spectrogram_data") or not hasattr(
            self._compute_spectrogram_data, "cache_info"
        ):
            return "Cache not available."
        return self._compute_spectrogram_data.cache_info()

    def clear_cache(self):
        """Clears the LRU cache."""
        if hasattr(self, "_compute_spectrogram_data") and hasattr(
            self._compute_spectrogram_data, "cache_clear"
        ):
            logger.info("Clearing SpectrogramService cache.")
            self._compute_spectrogram_data.cache_clear()
