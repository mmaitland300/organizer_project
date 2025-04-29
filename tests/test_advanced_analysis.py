# tests/test_advanced_analysis.py

import sys
import time
import pytest  # Use pytest imports
import logging
from unittest.mock import patch, MagicMock, call # Keep mock imports

# Keep Qt imports if needed for signal spying, but ensure QApplication exists
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, QEventLoop # Import QEventLoop for blocking wait

# Ensure imports for the classes being tested/mocked are correct
from services.advanced_analysis_worker import AdvancedAnalysisWorker
from services.analysis_engine import AnalysisEngine
# Import DatabaseManager for type hint in fixture injection
from services.database_manager import DatabaseManager

# Ensure QApplication instance exists for QSignalSpy/QTimer if running outside a main Qt app
# Note: If your test runner (like pytest-qt) handles this, it might not be necessary.
app = QApplication.instance() or QApplication(sys.argv)

logger = logging.getLogger(__name__)

# --- Mock Analysis Function (Keep as is) ---
def mock_analyze_side_effect(file_path, max_duration=60.0):
    """ Mock function for AnalysisEngine.analyze_audio_features. """
    logger.debug(f"Mock analyzing: {file_path}") # Use logger
    if file_path == "/dummy/audio1.wav":
        time.sleep(0.1)
        return {"brightness": 1000.0, "loudness_rms": 0.5, "pitch_hz": 440.0} # Add more features
    elif file_path == "/dummy/audio2.flac":
        time.sleep(0.1)
        return {"brightness": 2000.0, "loudness_rms": 0.7, "pitch_hz": 880.0}
    elif file_path == "/dummy/audio_error.mp3":
        time.sleep(0.1)
        raise ValueError("Simulated analysis error")
    elif file_path == "/dummy/audio_no_features.aiff":
        time.sleep(0.1)
        return {}
    else:
        return {}

# --- Pytest Test Functions ---
# No test class needed

@patch.object(DatabaseManager, 'save_file_records')
@patch.object(AnalysisEngine, 'analyze_audio_features')
def test_parallel_analysis_and_db_save(mock_analyze, mock_save_records, db_manager: DatabaseManager):
    """ Tests successful parallel analysis using pytest fixtures and DI. """
    logger.info("Running test_parallel_analysis_and_db_save")
    mock_analyze.side_effect = mock_analyze_side_effect
    files = [
        {"path": "/dummy/audio1.wav", "tags": {"filetype": [".wav"]}, "bpm": 120},
        {"path": "/dummy/non_audio.txt", "tags": {"filetype": [".txt"]}, "bpm": None},
        {"path": "/dummy/audio2.flac", "tags": {"filetype": [".flac"]}, "bpm": None},
        {"path": "/dummy/audio_error.mp3", "tags": {"filetype": [".mp3"]}, "bpm": None},
        {"path": "/dummy/audio_no_features.aiff", "tags": {"filetype": [".aiff"]}, "bpm": None},
    ]
    total_files = len(files)

    worker = AdvancedAnalysisWorker(files, db_manager=db_manager)
    spy_progress = QSignalSpy(worker.progress)
    spy_finished = QSignalSpy(worker.finished)

    loop = QEventLoop()
    worker.finished.connect(loop.quit) # Quit loop when worker finishes

    # --- Use QTimer for timeout ---
    TIMEOUT_MS = 6000
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit) # Also quit loop on timeout
    timer.start(TIMEOUT_MS)
    # --- End QTimer setup ---

    worker.start()
    loop.exec_() # Start the event loop (no arguments needed)

    # --- Check if finished signal was received using len() ---
    if len(spy_finished) == 0: # <<< Use len() instead of count()
        worker.cancel()
        pytest.fail(f"Worker finished signal not emitted within {TIMEOUT_MS}ms timeout")

    # --- Assert Progress ---
    assert len(spy_progress) > 0, "Progress signal(s) not emitted"
    last_progress_args = spy_progress[-1]
    assert last_progress_args[0] == total_files, "Final progress count incorrect"
    assert last_progress_args[1] == total_files, "Final progress total incorrect"

    # --- Assert Finished Signal ---
    assert len(spy_finished) == 1, "Finished signal emitted more/less than once"
    finished_list = spy_finished[0][0]
    assert len(finished_list) == total_files, "Finished list has incorrect number of files"

    # --- Assertions on Finished Data ---
    results_dict = {f["path"]: f for f in finished_list}

    # File 1 assertions
    assert "/dummy/audio1.wav" in results_dict
    file1_result = results_dict["/dummy/audio1.wav"]
    assert "brightness" in file1_result and file1_result["brightness"] == pytest.approx(1000.0)
    assert "loudness_rms" in file1_result and file1_result["loudness_rms"] == pytest.approx(0.5)
    assert "pitch_hz" in file1_result and file1_result["pitch_hz"] == pytest.approx(440.0)
    assert "filetype" in file1_result.get("tags", {})
    assert file1_result.get("bpm") == 120

    # Non-audio file assertions
    assert "/dummy/non_audio.txt" in results_dict
    assert "brightness" not in results_dict["/dummy/non_audio.txt"]

    # File 2 assertions
    assert "/dummy/audio2.flac" in results_dict
    file2_result = results_dict["/dummy/audio2.flac"]
    assert "brightness" in file2_result and file2_result["brightness"] == pytest.approx(2000.0)
    assert "loudness_rms" in file2_result and file2_result["loudness_rms"] == pytest.approx(0.7)
    assert "pitch_hz" in file2_result and file2_result["pitch_hz"] == pytest.approx(880.0)

    # Error file assertions
    assert "/dummy/audio_error.mp3" in results_dict
    assert "brightness" not in results_dict["/dummy/audio_error.mp3"]

    # No features file assertions
    assert "/dummy/audio_no_features.aiff" in results_dict
    assert "brightness" not in results_dict["/dummy/audio_no_features.aiff"]


    # --- Assert DB Save ---
    # Use mock properties for checks
    assert mock_save_records.call_count == 1, "save_file_records should be called once"

    # Get arguments from the mock call
    saved_list = mock_save_records.call_args[0][0]

    assert len(saved_list) == 2, "Incorrect number of records saved to DB"
    saved_paths = {r["path"] for r in saved_list}
    assert "/dummy/audio1.wav" in saved_paths
    assert "/dummy/audio2.flac" in saved_paths
    assert "/dummy/non_audio.txt" not in saved_paths
    assert "/dummy/audio_error.mp3" not in saved_paths
    assert "/dummy/audio_no_features.aiff" not in saved_paths

    # Check data structure passed to save
    for record in saved_list:
        assert "brightness" in record
        assert isinstance(record.get("brightness"), float)
        if record["path"] == "/dummy/audio1.wav":
            assert record.get("bpm") == 120


@patch.object(DatabaseManager, 'save_file_records')
@patch.object(AnalysisEngine, 'analyze_audio_features')
def test_cancellation(mock_analyze, mock_save_records, db_manager: DatabaseManager):
    """ Tests cancellation stops processing and DB save, using pytest fixtures and DI. """
    logger.info("Running test_cancellation")
    def cancel_mock_analyze(file_path, max_duration=60.0):
        logger.debug(f"Mock analyzing (cancel test): {file_path}")
        time.sleep(0.3)
        return {"brightness": 500.0}
    mock_analyze.side_effect = cancel_mock_analyze

    files = [
        {"path": "/dummy/cancel1.wav", "tags": {"filetype": [".wav"]}},
        {"path": "/dummy/cancel2.wav", "tags": {"filetype": [".wav"]}},
        {"path": "/dummy/cancel3.wav", "tags": {"filetype": [".wav"]}},
    ]

    worker = AdvancedAnalysisWorker(files, db_manager=db_manager)
    spy_progress = QSignalSpy(worker.progress)
    spy_finished = QSignalSpy(worker.finished)

    loop = QEventLoop()
    worker.finished.connect(loop.quit) # Quit loop when worker finishes

    # --- Use QTimer for timeout (optional but good practice) ---
    TIMEOUT_MS = 5000
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(TIMEOUT_MS)
    # --- End QTimer setup ---

    worker.start()
    # Schedule cancellation shortly after starting
    QTimer.singleShot(200, worker.cancel)
    loop.exec_() # Wait for EITHER finish signal OR timeout

    # --- Assertions ---
    # Check if finished signal was emitted (it should be, even on cancel)
    assert len(spy_finished) >= 1, "Finished signal not emitted after cancel"
    # Check DB save was NOT called
    assert mock_save_records.call_count == 0, "save_file_records should not be called after cancellation"

    # Check finished list contains original files
    finished_list = spy_finished[0][0]
    assert len(finished_list) == len(files)