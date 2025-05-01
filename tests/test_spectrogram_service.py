# Filename: tests/test_spectrogram_service.py
# With corrected test_file_not_found

import os
import sys  # Import sys for module checking
import unittest
import unittest.mock as mock

import numpy as np

# Mock librosa and numpy before importing the service if they might not be installed
# This ensures tests can run even without the heavy dependencies
MOCK_LIBS = False  # Set to True to force mocking even if libs are installed
if MOCK_LIBS or "librosa" not in sys.modules:
    # Use autospec=True to better mimic the actual objects
    sys.modules["librosa"] = mock.MagicMock(spec=["load", "stft"])
    sys.modules["librosa.feature"] = mock.MagicMock(spec=["melspectrogram"])
if MOCK_LIBS or "numpy" not in sys.modules:
    sys.modules["numpy"] = mock.MagicMock(spec=["abs", "array", "float32"])
    # Mock common numpy functions/attributes if needed by the service directly
    sys.modules["numpy"].abs = mock.MagicMock(
        side_effect=lambda x: (
            np.core.umath.absolute(x) if isinstance(x, np.ndarray) else abs(x)
        )
    )  # More realistic abs
    sys.modules["numpy"].array = (
        np.array
    )  # Use real numpy array if available but mocked
    sys.modules["numpy"].float32 = np.float32


# Assuming settings are structured correctly and importable
# If not, mock settings constants as well
try:
    from config.settings import (
        SPECTROGRAM_CACHE_SIZE,
        STFT_HOP_LENGTH,
        STFT_N_FFT,
        STFT_WIN_LENGTH,
        STFT_WINDOW,
    )
except ImportError:
    # Fallback values if settings aren't available during testing
    STFT_N_FFT, STFT_HOP_LENGTH, STFT_WIN_LENGTH, STFT_WINDOW = 2048, 512, None, "hann"
    SPECTROGRAM_CACHE_SIZE = 128

# Now import the service
from services.spectrogram_service import SpectrogramService

# Use a known dummy file path for tests
DUMMY_FILE_PATH = "/path/to/dummy/audio.wav"
# Use os.path.abspath here to match the internal logic precisely
DUMMY_ABS_PATH = os.path.abspath(DUMMY_FILE_PATH)


class TestSpectrogramService(unittest.TestCase):

    def setUp(self):
        """Clear cache before each test."""
        # Ensure service can be instantiated (might fail if deps missing and not mocked)
        try:
            # Access the static method directly via the class to clear its cache
            if hasattr(SpectrogramService, "_compute_spectrogram_data") and hasattr(
                SpectrogramService._compute_spectrogram_data, "cache_clear"
            ):
                SpectrogramService._compute_spectrogram_data.cache_clear()
                # print(f"Cache cleared. Info: {SpectrogramService._compute_spectrogram_data.cache_info()}") # Optional debug
            self.service = SpectrogramService()  # Instantiate fresh for each test
        except ImportError:
            self.skipTest(
                "Skipping test: numpy or librosa not installed/mocked properly."
            )
        except Exception as e:
            print(f"Error during setUp: {e}")
            raise

    @mock.patch("services.spectrogram_service.os.path.exists")
    @mock.patch("services.spectrogram_service.librosa.load")
    @mock.patch("services.spectrogram_service.librosa.stft")
    @mock.patch("services.spectrogram_service.librosa.feature.melspectrogram")
    def test_calculation_success(
        self, mock_melspectrogram, mock_stft, mock_load, mock_exists
    ):
        """Test successful spectrogram calculation and result structure."""
        # --- (This test method remains unchanged from the previous correct version) ---
        mock_exists.return_value = True
        mock_sr = 44100
        mock_y = np.array([0.1, 0.2, 0.1, -0.1, -0.2], dtype=np.float32)
        mock_complex_stft = np.array(
            [[1 + 1j, 2 + 2j], [3 + 3j, 4 + 4j]], dtype=complex
        )
        mock_mag_stft = np.abs(mock_complex_stft)
        mock_mel_spec = np.array([[5.0, 6.0], [7.0, 8.0]], dtype=float)
        mock_load.return_value = (mock_y, mock_sr)
        mock_stft.return_value = mock_complex_stft
        mock_melspectrogram.return_value = mock_mel_spec
        result = self.service.get_spectrogram_data(DUMMY_FILE_PATH)
        mock_exists.assert_called_once_with(DUMMY_ABS_PATH)
        mock_load.assert_called_once()
        mock_stft.assert_called_once()
        mock_melspectrogram.assert_called_once()
        self.assertIsNone(result.get("error"))
        self.assertEqual(result["sr"], mock_sr)
        np.testing.assert_array_almost_equal(result["magnitude"], mock_mag_stft)
        np.testing.assert_array_almost_equal(result["mel"], mock_mel_spec)
        self.assertEqual(result["n_fft"], STFT_N_FFT)
        self.assertEqual(result["hop_length"], STFT_HOP_LENGTH)
        expected_win_length = (
            STFT_WIN_LENGTH if STFT_WIN_LENGTH is not None else STFT_N_FFT
        )
        self.assertEqual(result["win_length"], expected_win_length)
        self.assertEqual(result["window"], STFT_WINDOW)

    @mock.patch("services.spectrogram_service.os.path.exists")
    @mock.patch("services.spectrogram_service.librosa.load")
    @mock.patch("services.spectrogram_service.librosa.stft")
    @mock.patch("services.spectrogram_service.librosa.feature.melspectrogram")
    def test_caching(self, mock_melspectrogram, mock_stft, mock_load, mock_exists):
        """Test that results are cached and internal librosa calls happen only once."""
        # --- (This test method remains unchanged from the previous correct version) ---
        mock_exists.return_value = True
        mock_sr = 44100
        mock_y = np.array([0.1] * 100, dtype=np.float32)
        mock_complex_stft = np.array([[1 + 1j] * 5], dtype=complex)
        mock_mel_spec = np.array([[5.0] * 5], dtype=float)
        mock_load.return_value = (mock_y, mock_sr)
        mock_stft.return_value = mock_complex_stft
        mock_melspectrogram.return_value = mock_mel_spec
        result1 = self.service.get_spectrogram_data(DUMMY_FILE_PATH)
        mock_load.assert_called_once()
        mock_stft.assert_called_once()
        mock_melspectrogram.assert_called_once()
        result2 = self.service.get_spectrogram_data(DUMMY_FILE_PATH)
        mock_load.assert_called_once()
        mock_stft.assert_called_once()
        mock_melspectrogram.assert_called_once()
        self.assertIsNotNone(result1)
        self.assertIsNotNone(result2)
        self.assertIsNone(result1.get("error"))
        self.assertIsNone(result2.get("error"))
        self.assertEqual(result1["sr"], result2["sr"])
        np.testing.assert_array_equal(result1["magnitude"], result2["magnitude"])

    @mock.patch(
        "services.spectrogram_service.SpectrogramService._compute_spectrogram_data"
    )
    def test_parameter_override(self, mock_compute):
        """Test that overridden parameters are passed to the compute method."""
        # --- (This test method remains unchanged from the previous correct version) ---
        mock_compute.return_value = {"error": None}
        override_params = {"n_fft": 1024, "hop_length": 256, "window": "hamming"}
        # Explicitly pass load_duration=None or its default value
        default_load_duration = 30.0  # Or get from settings if possible
        self.service.get_spectrogram_data(
            DUMMY_FILE_PATH, load_duration=default_load_duration, **override_params
        )
        expected_win_length = STFT_WIN_LENGTH
        mock_compute.assert_called_once_with(
            file_path=DUMMY_ABS_PATH,
            n_fft=1024,
            hop_length=256,
            win_length=expected_win_length,
            window="hamming",
            load_duration=default_load_duration,  # Check correct load_duration was passed
        )

    # --- CORRECTED test_file_not_found ---
    @mock.patch("services.spectrogram_service.os.path.exists")
    @mock.patch("services.spectrogram_service.librosa.load")
    def test_file_not_found(self, mock_load, mock_exists):
        """Test handling of FileNotFoundError when os.path.exists returns False."""
        mock_exists.return_value = False  # Simulate file not existing

        # Call the public method - this will call _compute_spectrogram_data internally
        result = self.service.get_spectrogram_data(DUMMY_FILE_PATH)

        # Assert os.path.exists was checked with the absolute path
        mock_exists.assert_called_once_with(DUMMY_ABS_PATH)
        # Assert librosa.load was NOT called because the file check failed
        mock_load.assert_not_called()

        # Assert the result dictionary indicates an error
        self.assertIn("error", result)
        self.assertIsNotNone(result["error"])
        # Assert the error message contains the expected text and the path
        self.assertIn("Audio file not found", result["error"])
        self.assertIn(DUMMY_ABS_PATH, result["error"])

    # --- END CORRECTED test_file_not_found ---

    @mock.patch("services.spectrogram_service.os.path.exists")
    @mock.patch("services.spectrogram_service.librosa.load")
    @mock.patch("services.spectrogram_service.librosa.stft")
    def test_calculation_error(self, mock_stft, mock_load, mock_exists):
        """Test handling of errors during librosa calculation."""
        # --- (This test method remains unchanged from the previous correct version) ---
        mock_exists.return_value = True
        mock_load.return_value = (np.array([0.1], dtype=np.float32), 44100)
        mock_stft.side_effect = ValueError("Test STFT Error")
        result = self.service.get_spectrogram_data(DUMMY_FILE_PATH)
        mock_exists.assert_called_once_with(DUMMY_ABS_PATH)
        mock_load.assert_called_once()
        mock_stft.assert_called_once()
        self.assertIn("error", result)
        self.assertIn("Calculation Error", result["error"])
        self.assertIn("Test STFT Error", result["error"])


if __name__ == "__main__":
    # --- (This __main__ block remains unchanged) ---
    import sys

    if "numpy" not in sys.modules:
        sys.modules["numpy"] = mock.MagicMock(spec=["abs", "array", "float32"])
        sys.modules["numpy"].abs = mock.MagicMock(
            side_effect=lambda x: (
                np.core.umath.absolute(x) if isinstance(x, np.ndarray) else abs(x)
            )
        )
        sys.modules["numpy"].array = np.array
        sys.modules["numpy"].float32 = np.float32
    if "librosa" not in sys.modules:
        sys.modules["librosa"] = mock.MagicMock(spec=["load", "stft"])
        sys.modules["librosa.feature"] = mock.MagicMock(spec=["melspectrogram"])

    unittest.main()
