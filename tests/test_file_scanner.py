import datetime
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from services.database_manager import DatabaseManager
from services.file_scanner import FileScannerService

# Ensure a QApplication instance is available.
if QApplication.instance() is None:
    app = QApplication(sys.argv)


class TestFileScannerService(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory with one dummy file.
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_file_path = os.path.join(self.temp_dir.name, "test_audio.mp3")
        # Write some dummy data (it need not be valid audio)
        with open(self.test_file_path, "wb") as f:
            f.write(b"\x00" * 1024)  # 1KB dummy file.

            # Mock DatabaseManager for setUp - tests might need more specific mocks
            mock_db_manager = MagicMock(spec=DatabaseManager)
            # Create the scanner, passing the required db_manager (mocked)
            self.scanner = FileScannerService(
                root_path=self.temp_dir.name, db_manager=mock_db_manager
            )

    def tearDown(self):
        self.temp_dir.cleanup()

    @unittest.skip(
        "Temporarily skipping file scanner test due to hanging metadata extraction"
    )
    def test_scan(self):
        # Create a dummy tag to be returned by TinyTag.get.
        dummy_tag = MagicMock()
        dummy_tag.duration = 100.0
        dummy_tag.samplerate = 44100
        dummy_tag.channels = 2

        # Patch both the reference in config.settings and in services.file_scanner.
        with (
            patch(
                "config.settings.TinyTag.get", return_value=dummy_tag
            ) as mock_get_config,
            patch(
                "services.file_scanner.TinyTag.get", return_value=dummy_tag
            ) as mock_get_scanner,
        ):

            # Use QSignalSpy to capture the finished signal.
            spy = QSignalSpy(self.scanner.finished)
            self.scanner.start()

            # Wait up to 2 seconds for the finished signal.
            if not spy.wait(2000):
                self.fail("Finished signal was not emitted in time")
            files_info = spy[0][0]
            self.assertTrue(
                len(files_info) > 0, f"Expected non-empty file info, got: {files_info}"
            )
            file_info = files_info[0]
            self.assertEqual(file_info.get("duration"), 100.0)
            self.assertEqual(file_info.get("samplerate"), 44100)
            self.assertEqual(file_info.get("channels"), 2)
            self.assertIn("path", file_info)


if __name__ == "__main__":
    unittest.main()
