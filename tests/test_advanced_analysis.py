# tests/test_advanced_analysis.py

import sys
import time
import unittest
# Updated: Import patch from unittest.mock directly for clarity
from unittest.mock import patch, MagicMock, call

from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

# Ensure imports for the classes being tested/mocked are correct
from services.advanced_analysis_worker import AdvancedAnalysisWorker
from services.analysis_engine import AnalysisEngine
from services.database_manager import DatabaseManager

app = None
if QApplication.instance() is None:
    # Create QApplication instance only if none exists, suitable for test environments
    app = QApplication(sys.argv)

# --- Mock Analysis Function ---
def mock_analyze_side_effect(file_path, max_duration=60.0):
    """
    Mock function for AnalysisEngine.analyze_audio_features.
    Simulates analysis time and returns predefined results or raises errors.
    """
    print(f"Mock analyzing: {file_path}") # Useful for debugging test flow
    if file_path == "/dummy/audio1.wav":
        time.sleep(0.1) # Simulate work
        # Returns features as floats
        return {"brightness": 1000.0, "loudness_rms": 0.5}
    elif file_path == "/dummy/audio2.flac":
        time.sleep(0.1)
        return {"brightness": 2000.0, "loudness_rms": 0.7}
    elif file_path == "/dummy/audio_error.mp3":
        time.sleep(0.1)
        # Simulate an error during analysis for this specific file
        raise ValueError("Simulated analysis error")
    elif file_path == "/dummy/audio_no_features.aiff":
         time.sleep(0.1)
         # Simulate analysis completing but returning no features
         return {}
    else:
        # Default case for other files (like non_audio.txt)
        return {}

class TestAdvancedAnalysisWorker(unittest.TestCase):
    """Tests the AdvancedAnalysisWorker background thread."""

    @patch.object(DatabaseManager, 'save_file_records')
    @patch.object(AnalysisEngine, 'analyze_audio_features')
    def test_parallel_analysis_and_db_save(self, mock_analyze, mock_save_records):
        """
        Tests successful parallel analysis, checking progress, results, and final batch DB save.
        Uses corrected mocking and asserts features as top-level float values.
        """
        # --- Setup Mock Analysis ---
        mock_analyze.side_effect = mock_analyze_side_effect

        # --- Prepare Input Data ---
        files = [
            {"path": "/dummy/audio1.wav", "tags": {"filetype": [".wav"]}, "bpm": 120},
            {"path": "/dummy/non_audio.txt", "tags": {"filetype": [".txt"]}, "bpm": None},
            {"path": "/dummy/audio2.flac", "tags": {"filetype": [".flac"]}, "bpm": None},
            {"path": "/dummy/audio_error.mp3", "tags": {"filetype": [".mp3"]}, "bpm": None},
            {"path": "/dummy/audio_no_features.aiff", "tags": {"filetype": [".aiff"]}, "bpm": None},
        ]
        total_files = len(files)

        # --- Run Worker ---
        worker = AdvancedAnalysisWorker(files)
        spy_progress = QSignalSpy(worker.progress)
        spy_finished = QSignalSpy(worker.finished)

        worker.start()
        # Wait for the finished signal with a timeout
        self.assertTrue(spy_finished.wait(6000), "Worker finished signal not emitted in time") # Increased timeout slightly

        # --- Assert Progress ---
        self.assertTrue(len(spy_progress) > 0, "Progress signal(s) not emitted")
        # Check the arguments of the last progress signal emitted
        last_progress_args = spy_progress[-1]
        self.assertEqual(last_progress_args[0], total_files, "Final progress count incorrect")
        self.assertEqual(last_progress_args[1], total_files, "Final progress total incorrect")

        # --- Assert Finished Signal ---
        self.assertEqual(len(spy_finished), 1, "Finished signal emitted more than once")
        # Get the list of file dictionaries returned by the worker
        finished_list = spy_finished[0][0]
        self.assertEqual(len(finished_list), total_files, "Finished list has incorrect number of files")

        # --- Assertions on Finished Data Structure ---
        # Convert list to dict for easier lookup by path
        results_dict = {f["path"]: f for f in finished_list}

        # Check audio1.wav got updated correctly
        self.assertIn("/dummy/audio1.wav", results_dict)
        file1_result = results_dict["/dummy/audio1.wav"]
        # Assert features are top-level keys with float values
        self.assertIn("brightness", file1_result, "Brightness key missing")
        self.assertIsNotNone(file1_result.get("brightness"), "Brightness value is None")
        self.assertAlmostEqual(file1_result.get("brightness"), 1000.0)

        self.assertIn("loudness_rms", file1_result, "Loudness key missing")
        self.assertIsNotNone(file1_result.get("loudness_rms"), "Loudness value is None")
        self.assertAlmostEqual(file1_result.get("loudness_rms"), 0.5)
        # Check existing tag/bpm is preserved
        self.assertIn("filetype", file1_result.get("tags", {}))
        self.assertEqual(file1_result.get("bpm"), 120)

        # Check non_audio.txt was not updated with features
        self.assertIn("/dummy/non_audio.txt", results_dict)
        file_txt_result = results_dict["/dummy/non_audio.txt"]
        self.assertNotIn("brightness", file_txt_result) # Check feature key absent
        self.assertIn("filetype", file_txt_result.get("tags", {})) # Check tag preserved

        # Check audio2.flac got updated correctly
        self.assertIn("/dummy/audio2.flac", results_dict)
        file2_result = results_dict["/dummy/audio2.flac"]
        self.assertIn("brightness", file2_result, "Brightness key missing (audio2)")
        self.assertIsNotNone(file2_result.get("brightness"), "Brightness value is None (audio2)")
        self.assertAlmostEqual(file2_result.get("brightness"), 2000.0)

        self.assertIn("loudness_rms", file2_result, "Loudness key missing (audio2)")
        self.assertIsNotNone(file2_result.get("loudness_rms"), "Loudness value is None (audio2)")
        self.assertAlmostEqual(file2_result.get("loudness_rms"), 0.7)
        self.assertIn("filetype", file2_result.get("tags", {}))

        # Check audio_error.mp3 was included but *not* updated with features
        self.assertIn("/dummy/audio_error.mp3", results_dict)
        file_err_result = results_dict["/dummy/audio_error.mp3"]
        self.assertNotIn("brightness", file_err_result)
        self.assertIn("filetype", file_err_result.get("tags", {}))

        # Check audio_no_features.aiff was included but *not* updated with features
        self.assertIn("/dummy/audio_no_features.aiff", results_dict)
        file_nf_result = results_dict["/dummy/audio_no_features.aiff"]
        self.assertNotIn("brightness", file_nf_result)
        self.assertIn("filetype", file_nf_result.get("tags", {}))


        # --- Assert DB Save ---
        # Check that the mocked save_file_records was called exactly once
        mock_save_records.assert_called_once()

        # Get the list of records passed to the mocked save_file_records
        # call_args[0] is the tuple of positional arguments
        saved_list = mock_save_records.call_args[0][0]

        # Check that the correct files were marked for saving
        # (Worker should only save records where features were successfully added/updated)
        self.assertEqual(len(saved_list), 2, "Incorrect number of records saved to DB")
        saved_paths = {r["path"] for r in saved_list}
        self.assertIn("/dummy/audio1.wav", saved_paths)
        self.assertIn("/dummy/audio2.flac", saved_paths)
        self.assertNotIn("/dummy/non_audio.txt", saved_paths)
        self.assertNotIn("/dummy/audio_error.mp3", saved_paths)
        self.assertNotIn("/dummy/audio_no_features.aiff", saved_paths)

        # Optional: Check data structure passed to save_file_records
        for record in saved_list:
             self.assertIn("brightness", record)
             self.assertIn("loudness_rms", record)
             # Check that features are floats, not strings/lists
             self.assertIsInstance(record.get("brightness"), float)
             self.assertIsInstance(record.get("loudness_rms"), float)
             # Check that original tags/bpm are still present if they existed
             if record["path"] == "/dummy/audio1.wav":
                  self.assertEqual(record.get("bpm"), 120)
                  self.assertIn("filetype", record.get("tags", {}))


    @patch.object(DatabaseManager, 'save_file_records')
    @patch.object(AnalysisEngine, 'analyze_audio_features')
    def test_cancellation(self, mock_analyze, mock_save_records):
        """
        Tests that cancelling the worker stops processing and prevents DB save.
        Uses corrected mocking.
        """
        # --- Setup Mock Analysis (simulates work taking time) ---
        def cancel_mock_analyze(file_path, max_duration=60.0):
             print(f"Mock analyzing (cancel test): {file_path}")
             time.sleep(0.3) # Simulate longer analysis time
             return {"brightness": 500.0}
        mock_analyze.side_effect = cancel_mock_analyze

        # --- Prepare Input Data ---
        files = [
            {"path": "/dummy/cancel1.wav", "tags": {"filetype": [".wav"]}},
            {"path": "/dummy/cancel2.wav", "tags": {"filetype": [".wav"]}},
            {"path": "/dummy/cancel3.wav", "tags": {"filetype": [".wav"]}},
        ]

        # --- Run Worker and Cancel ---
        worker = AdvancedAnalysisWorker(files)
        spy_progress = QSignalSpy(worker.progress)
        spy_finished = QSignalSpy(worker.finished)
        worker.start()
        # Schedule cancellation after a short delay, before all tasks likely finish
        QTimer.singleShot(200, worker.cancel)
        # Wait for the finished signal after cancellation
        self.assertTrue(spy_finished.wait(5000), "Worker finished signal not emitted after cancel")

        # --- Assertions ---
        self.assertEqual(len(spy_finished), 1, "Finished signal emitted incorrectly on cancel")
        # CRITICAL: Ensure DB save was NOT called because worker was cancelled
        mock_save_records.assert_not_called()

        # Check that the finished list still contains all original files (as expected)
        finished_list = spy_finished[0][0]
        self.assertEqual(len(finished_list), len(files))

# Boilerplate to run tests if script is executed directly
if __name__ == "__main__":
    unittest.main()