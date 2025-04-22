import datetime
import sys
import unittest

from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from services.duplicate_finder import DuplicateFinderService

if QApplication.instance() is None:
    app = QApplication(sys.argv)


class TestDuplicateFinder(unittest.TestCase):
    def setUp(self):
        self.file1 = {
            "path": "/dummy/path/file1.wav",
            "size": 1024,
            "mod_time": datetime.datetime.now(),
            "hash": "abc123",
            "used": False,
        }
        self.file2 = {
            "path": "/dummy/path/file2.wav",
            "size": 1024,
            "mod_time": datetime.datetime.now(),
            "hash": "abc123",
            "used": False,
        }
        self.file3 = {
            "path": "/dummy/path/file3.wav",
            "size": 2048,
            "mod_time": datetime.datetime.now(),
            "hash": "def456",
            "used": False,
        }
        self.files_info = [self.file1, self.file2, self.file3]

    def test_duplicate_detection(self):
        dup_service = DuplicateFinderService(self.files_info)
        # Use QSignalSpy to catch the finished signal with a timeout.
        spy = QSignalSpy(dup_service.finished)
        dup_service.start()
        if not spy.wait(2000):
            self.fail("Finished signal was not emitted in time")
        # The spy returns a list of tuples; the first element of the first tuple is the result.
        result = spy[0][0]
        # We expect one duplicate group with two duplicates.
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 2)


if __name__ == "__main__":
    unittest.main()
