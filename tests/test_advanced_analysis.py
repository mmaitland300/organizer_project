# tests/test_advanced_analysis.py

import sys
import time
from typing import Dict, Optional
import pytest
import logging

# Added Future import, removed ANY as it's less needed now
from unittest.mock import patch, MagicMock, call
import copy

# Import Future for mocking submit return value
from concurrent.futures import Future

from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer, QEventLoop

from services.advanced_analysis_worker import (
    AdvancedAnalysisWorker,
    _analyze_file_process_worker,
)  # Import the real worker function for type checking if needed
from services.database_manager import DatabaseManager

app = QApplication.instance() or QApplication(sys.argv)
logger = logging.getLogger(__name__)


def mock_analyze_process_worker_side_effect(
    file_info: Dict, cancel_event: MagicMock
) -> Optional[Dict]:
    """
    Mocks the return value of _analyze_file_process_worker based on path.
    Returns the *updated* file_info dict or None.
    (Implementation unchanged from previous step)
    """
    path = file_info.get("path")
    logger.debug(f"Mock analyzing (process worker side effect): {path}")
    time.sleep(0.01)  # Reduced sleep

    updated_info = copy.deepcopy(file_info)

    if path == "/dummy/audio1.wav":
        updated_info.update(
            {"brightness": 1000.0, "loudness_rms": 0.5, "pitch_hz": 440.0}
        )
        return updated_info
    elif path == "/dummy/audio2.flac":
        updated_info.update(
            {"brightness": 2000.0, "loudness_rms": 0.7, "pitch_hz": 880.0}
        )
        return updated_info
    elif path == "/dummy/audio_error.mp3":
        return None
    elif path == "/dummy/audio_no_features.aiff":
        return None
    elif path == "/dummy/non_audio.txt":
        return None
    else:
        return None


# --- Mock function for the *worker process* function ---
# This function needs to simulate the return value of _analyze_file_process_worker
def mock_analyze_process_worker_side_effect(
    file_info: Dict, cancel_event: MagicMock
) -> Optional[Dict]:
    """
    Mocks the return value of _analyze_file_process_worker based on path.
    Returns the *updated* file_info dict or None.
    """
    path = file_info.get("path")
    logger.debug(f"Mock analyzing (process worker): {path}")
    time.sleep(0.05)  # Simulate some work

    # Make a copy to modify and return, simulating the real worker
    updated_info = copy.deepcopy(file_info)

    if path == "/dummy/audio1.wav":
        updated_info.update(
            {"brightness": 1000.0, "loudness_rms": 0.5, "pitch_hz": 440.0}
        )
        return updated_info
    elif path == "/dummy/audio2.flac":
        updated_info.update(
            {"brightness": 2000.0, "loudness_rms": 0.7, "pitch_hz": 880.0}
        )
        return updated_info
    elif path == "/dummy/audio_error.mp3":
        # Simulate analysis failure by returning None (as the real worker does on exception)
        return None
    elif path == "/dummy/audio_no_features.aiff":
        # Simulate analysis returning no new features (real worker returns None in this case)
        return None
    elif path == "/dummy/non_audio.txt":
        # Simulate non-audio file (real worker returns None)
        return None
    else:
        # Default case: return None if no match (simulates other errors or skipped files)
        return None


# --- Pytest Test Functions ---

# --- Test Function (MODIFIED Patch Target) ---


@patch.object(DatabaseManager, "save_file_records")
# MODIFIED: Patch the 'submit' method using the alias path '_cf'
@patch("services.advanced_analysis_worker._cf.ProcessPoolExecutor.submit")
# Test function signature includes the mock for the aliased path
def test_parallel_analysis_and_db_save(
    mock_aliased_submit,  # <<< Mock for _cf.ProcessPoolExecutor.submit
    mock_save_records,
    db_manager: DatabaseManager,
):
    """
    Tests successful parallel analysis by patching submit via its alias _cf.
    """
    logger.info("Running test_parallel_analysis_and_db_save patching via alias _cf")

    # --- Define the side effect for the mocked submit ---
    submitted_futures = []

    def mock_submit_side_effect(func, *args, **kwargs):
        file_info = args[0]
        mock_cancel_event = MagicMock()
        logger.debug(f"Mock aliased submit called for: {file_info.get('path')}")
        result = mock_analyze_process_worker_side_effect(file_info, mock_cancel_event)
        mock_future = Future()
        mock_future.set_result(result)
        submitted_futures.append(mock_future)
        return mock_future

    # Assign the side effect to the mock for the aliased path
    mock_aliased_submit.side_effect = mock_submit_side_effect
    # ----------------------------------------------------

    # Keep file list setup
    files = [
        {
            "path": "/dummy/audio1.wav",
            "tags": {"filetype": [".wav"]},
            "bpm": 120,
            "size": 100,
            "mod_time": 1.0,
        },
        {
            "path": "/dummy/non_audio.txt",
            "tags": {"filetype": [".txt"]},
            "bpm": None,
            "size": 10,
            "mod_time": 1.0,
        },
        {
            "path": "/dummy/audio2.flac",
            "tags": {"filetype": [".flac"]},
            "bpm": None,
            "size": 200,
            "mod_time": 1.0,
        },
        {
            "path": "/dummy/audio_error.mp3",
            "tags": {"filetype": [".mp3"]},
            "bpm": None,
            "size": 50,
            "mod_time": 1.0,
        },
        {
            "path": "/dummy/audio_no_features.aiff",
            "tags": {"filetype": [".aiff"]},
            "bpm": None,
            "size": 150,
            "mod_time": 1.0,
        },
    ]
    total_files = len(files)

    # Keep worker setup and signal spying
    worker = AdvancedAnalysisWorker(files, db_manager=db_manager)
    spy_finished = QSignalSpy(worker.analysisComplete)
    spy_progress = QSignalSpy(worker.progress)

    # Keep QEventLoop and Timeout logic
    loop = QEventLoop()
    worker.analysisComplete.connect(loop.quit)
    worker.error.connect(loop.quit)
    TIMEOUT_MS = 6000
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: loop.exit(1))
    timer.start(TIMEOUT_MS)
    worker.start()
    exit_code = loop.exec_()

    # --- Assertions ---
    if exit_code != 0:
        worker.cancel()
        pytest.fail(
            f"Worker did not finish within {TIMEOUT_MS}ms timeout (exit code: {exit_code})"
        )

    # --- Assert Mock Submit Calls (Using mock_aliased_submit) ---
    assert (
        mock_aliased_submit.call_count == total_files
    ), f"Expected aliased executor.submit call count == {total_files}, but got {mock_aliased_submit.call_count}"

    # --- Assert Progress ---
    assert len(spy_progress) > 0, "Progress signal(s) not emitted"
    assert any(
        args[0] == total_files and args[1] == total_files for args in spy_progress
    ), f"No progress signal reached final count {total_files}/{total_files}. Signals: {spy_progress}"

    # --- Assert Finished Signal ---
    assert len(spy_finished) == 1, "analysisComplete signal emitted more/less than once"
    finished_list = spy_finished[0][0]
    assert (
        len(finished_list) == total_files
    ), "Finished list has incorrect number of files"

    # --- Assertions on Finished Data ---
    # (Keep existing assertions - unchanged)
    results_dict = {f["path"]: f for f in finished_list}
    assert "/dummy/audio1.wav" in results_dict
    assert results_dict["/dummy/audio1.wav"].get("brightness") == pytest.approx(1000.0)
    assert "/dummy/audio2.flac" in results_dict
    assert results_dict["/dummy/audio2.flac"].get("brightness") == pytest.approx(2000.0)
    assert results_dict["/dummy/non_audio.txt"].get("brightness") is None
    assert results_dict["/dummy/audio_error.mp3"].get("brightness") is None
    assert results_dict["/dummy/audio_no_features.aiff"].get("brightness") is None

    # --- Assert DB Save ---
    # (Keep existing assertions - unchanged)
    assert mock_save_records.call_count == 1, "save_file_records should be called once"
    saved_list = mock_save_records.call_args[0][0]
    assert isinstance(saved_list, list)
    assert len(saved_list) == 2, "Incorrect number of records saved to DB"
    saved_paths = {r["path"] for r in saved_list}
    assert "/dummy/audio1.wav" in saved_paths
    assert "/dummy/audio2.flac" in saved_paths
    assert "/dummy/non_audio.txt" not in saved_paths
    assert "/dummy/audio_error.mp3" not in saved_paths
    assert "/dummy/audio_no_features.aiff" not in saved_paths

    # (Keep checks on saved_list content)
    for record in saved_list:
        assert "brightness" in record
        if record["path"] == "/dummy/audio1.wav":
            assert record.get("bpm") == 120


@patch.object(DatabaseManager, "save_file_records")
@patch("concurrent.futures.ProcessPoolExecutor.submit")  # Patch submit
def test_cancellation(mock_submit, mock_save_records, db_manager: DatabaseManager):
    """Tests cancellation stops processing and DB save by patching submit"""
    logger.info("Running test_cancellation patching executor.submit")

    # --- Define side effect for mocked submit during cancel test ---
    def cancel_mock_submit_side_effect(func, *args, **kwargs):
        file_info = args[0]
        logger.debug(f"Mock submit called (cancel test): {file_info.get('path')}")
        # Simulate analysis result (doesn't really matter as worker should cancel)
        result = None  # Or copy(file_info)
        mock_future = Future()
        mock_future.set_result(result)
        # Don't sleep here, let the main worker loop handle timing/cancellation
        return mock_future

    mock_submit.side_effect = cancel_mock_submit_side_effect
    # -------------------------------------------------------------

    files = [
        {
            "path": "/dummy/cancel1.wav",
            "tags": {"filetype": [".wav"]},
            "size": 1,
            "mod_time": 1,
        },
        {
            "path": "/dummy/cancel2.wav",
            "tags": {"filetype": [".wav"]},
            "size": 1,
            "mod_time": 1,
        },
        {
            "path": "/dummy/cancel3.wav",
            "tags": {"filetype": [".wav"]},
            "size": 1,
            "mod_time": 1,
        },
    ]

    worker = AdvancedAnalysisWorker(files, db_manager=db_manager)
    spy_finished = QSignalSpy(worker.analysisComplete)
    spy_progress = QSignalSpy(worker.progress)

    loop = QEventLoop()
    worker.analysisComplete.connect(loop.quit)
    worker.error.connect(loop.quit)

    TIMEOUT_MS = 5000
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(lambda: loop.exit(1))
    timer.start(TIMEOUT_MS)

    worker.start()
    QTimer.singleShot(100, worker.cancel)  # Cancel slightly earlier
    exit_code = loop.exec_()

    # --- Assertions ---
    assert exit_code == 0, f"Worker timed out during cancellation test ({TIMEOUT_MS}ms)"
    assert len(spy_finished) >= 1, "analysisComplete signal not emitted after cancel"
    assert (
        mock_save_records.call_count == 0
    ), "save_file_records should not be called after cancellation"

    # Check mock submit calls (might be called for some/all before cancel stops loop)
    logger.info(f"Cancel test mock submit call count: {mock_submit.call_count}")
    assert mock_submit.call_count <= len(files)  # Could be 0 to len(files)

    finished_list = spy_finished[0][0]
    assert len(finished_list) == len(files)
    original_paths = {f["path"] for f in files}
    finished_paths = {f["path"] for f in finished_list}
    assert original_paths == finished_paths
