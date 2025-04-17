# tests/test_database_manager.py
import unittest
import tempfile
import os
import datetime
from services.database_manager import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        # Redirect the DB to a temp file
        self.tmp_db = tempfile.NamedTemporaryFile(delete=False)
        self.original_db = DatabaseManager.DB_FILENAME
        DatabaseManager.DB_FILENAME = self.tmp_db.name
        # Reset singleton
        DatabaseManager._instance = None
        self.db = DatabaseManager.instance()

    def tearDown(self):
        DatabaseManager.DB_FILENAME = self.original_db
        try:
            os.remove(self.tmp_db.name)
        except OSError:
            pass

    def test_batch_save_and_get(self):
        file1 = {
            "path": "p1.wav", "size": 100, "mod_time": 123.0,
            "duration": 1.0, "bpm": 120, "key": "C", "used": False,
            "samplerate": 44100, "channels": 2, "tags": {}
        }
        file2 = {
            "path": "p2.wav", "size": 200, "mod_time": 456.0,
            "duration": 2.0, "bpm": 130, "key": "D", "used": True,
            "samplerate": 48000, "channels": 1, "tags": {"general": ["TAG"]}
        }
        # Batch‐save both
        self.db.save_file_records([file1, file2])
        # Fetch and assert
        rec1 = self.db.get_file_record("p1.wav")
        self.assertIsNotNone(rec1)
        self.assertEqual(rec1["size"], 100)
        rec2 = self.db.get_file_record("p2.wav")
        self.assertTrue(rec2["used"])
        self.assertEqual(rec2["tags"].get("general"), ["TAG"])

if __name__ == "__main__":
    unittest.main()
