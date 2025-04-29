# tests/test_database_manager.py
"""
Unit tests for the DatabaseManager service.
Uses an in-memory SQLite database initialized via Alembic migrations.
"""

import sys
import unittest
import sqlite3
import os
import datetime
import logging
from unittest.mock import patch, MagicMock
# ADD THIS IMPORT FOR THE ENGINE CREATION:
from sqlalchemy import create_engine, text
# --- Alembic Imports ---
try:
    from alembic.config import Config
    from alembic import command
    ALEMBIC_AVAILABLE = True
except ImportError:
    ALEMBIC_AVAILABLE = False
    Config = None
    command = None

# Ensure imports work based on project structure
from services.database_manager import DatabaseManager

logging.basicConfig(level=logging.INFO) # Adjust level as needed
logger = logging.getLogger(__name__)

# --- Helper to find alembic.ini ---
# Adjust this path if your alembic.ini is located elsewhere relative to tests
# Assumes tests are run from the project root where alembic.ini resides
ALEMBIC_INI_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'alembic.ini'))

@unittest.skipUnless(ALEMBIC_AVAILABLE, "Alembic is not installed, skipping DatabaseManager tests that require migrations.")
class TestDatabaseManager(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Check if alembic.ini exists once for the whole class."""
        # --- Check Alembic Availability and INI Path ---
        if not ALEMBIC_AVAILABLE:
             raise unittest.SkipTest("Alembic is not installed.")
        if not os.path.exists(ALEMBIC_INI_PATH):
            raise FileNotFoundError(f"Alembic configuration file not found at expected path: {ALEMBIC_INI_PATH}")

    def setUp(self):
        """
        Set up a clean in-memory database using DatabaseManager's SQLAlchemy engine
        and run Alembic migrations against that engine.
        """
        logger.info(f"--- Setting up test: {self.id()} ---")
        DatabaseManager._instance = None # Reset singleton

        # --- Use an in-memory SQLite database ---
        self.db_path = ':memory:'
        # Patch DB_FILENAME *before* instance creation
        self.filename_patcher = patch.object(DatabaseManager, 'DB_FILENAME', self.db_path)
        self.mock_db_filename = self.filename_patcher.start()
        self.addCleanup(self.filename_patcher.stop) # Ensure patch stops even on error

        # --- Create DB Manager Instance (Now creates self.engine internally) ---
        try:
            # Instantiate the manager, it should now create self.engine pointing to :memory:
            self.db_manager = DatabaseManager.instance()
            # --- Assert that the SQLAlchemy ENGINE was created ---
            self.assertIsNotNone(self.db_manager.engine, "DatabaseManager failed to create SQLAlchemy engine for :memory:")
            logger.info(f"DatabaseManager created with SQLAlchemy engine pointing to {self.db_manager.engine.url}")
        except Exception as e:
            # Ensure patcher stops if instantiation fails
            if hasattr(self, 'filename_patcher'):
                self.filename_patcher.stop()
            self.fail(f"DatabaseManager instantiation failed: {e}")

        # --- Run Alembic Migrations using the DatabaseManager's ENGINE ---
        logger.info(f"Running Alembic migrations using engine from DatabaseManager via config {ALEMBIC_INI_PATH}...")
        try:
            alembic_cfg = Config(ALEMBIC_INI_PATH)

            # --- Pass the DatabaseManager's SQLAlchemy ENGINE via attributes ---
            # env.py should detect this as an engine
            alembic_cfg.attributes['connection'] = self.db_manager.engine # Use the manager's engine

            # Set the URL - may still be needed by Alembic's Config loading,
            # even though the engine is passed via attributes.
            alembic_cfg.set_main_option('sqlalchemy.url', f'sqlite:///{self.db_path}')

            # Apply migrations up to 'head' (latest) using the provided engine
            command.upgrade(alembic_cfg, 'head')
            logger.info("Alembic migrations applied successfully using DatabaseManager's engine.")

        except Exception as e:
            logger.error(f"Alembic upgrade failed during test setup: {e}", exc_info=True)
            # Clean up engine if migration fails
            if hasattr(self, 'db_manager') and self.db_manager.engine:
                logger.debug("Disposing engine after Alembic failure in setUp.")
                self.db_manager.engine.dispose()
            self.fail(f"Alembic upgrade failed: {e}") # Fail the test here

        # --- Verify Schema Creation using the ENGINE ---
        try:
            # Use the engine to connect and verify
            with self.db_manager.engine.connect() as connection:
                 # Verify 'files' table
                 result_files = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='files';"))
                 files_table_exists = result_files.fetchone()
                 self.assertIsNotNone(files_table_exists, "'files' table should exist after Alembic upgrade")

                 # Verify 'alembic_version' table
                 result_alembic = connection.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version';"))
                 alembic_table_exists = result_alembic.fetchone()
                 self.assertIsNotNone(alembic_table_exists, "'alembic_version' table should exist after Alembic upgrade")
            logger.info("Schema tables verified successfully using SQLAlchemy engine connection.")
        except Exception as e:
             logger.error(f"Schema verification query failed after Alembic upgrade: {e}", exc_info=True)
             # Clean up engine if verification fails
             if hasattr(self, 'db_manager') and self.db_manager.engine:
                 logger.debug("Disposing engine after schema verification failure.")
                 self.db_manager.engine.dispose()
             self.fail(f"Schema verification query failed after Alembic upgrade: {e}")

    def tearDown(self):
        """
        Clean up by disposing the SQLAlchemy engine.
        """
        logger.info(f"--- Tearing down test: {self.id()} ---")

        # Dispose the engine via the DatabaseManager instance if it exists
        if hasattr(self, 'db_manager') and self.db_manager and self.db_manager.engine:
            logger.debug(f"Disposing SQLAlchemy engine (URL: {self.db_manager.engine.url})")
            self.db_manager.engine.dispose()
            self.db_manager.engine = None # Clear reference on the manager instance if possible/needed

        # Reset the singleton again for the next test
        DatabaseManager._instance = None
        # Patchers stopped via addCleanup in setUp
        logger.info("--- Teardown complete ---")

    # --- Test Methods ---

    def test_singleton_instance(self):
        """Verify that instance() returns the same object."""
        logger.info("Running test_singleton_instance")
        instance1 = self.db_manager
        instance2 = DatabaseManager.instance()
        self.assertIs(instance1, instance2, "instance() should return the same singleton object")

    def test_save_and_get_file_record(self):
        """Test saving a single record and retrieving it accurately."""
        logger.info("Running test_save_and_get_file_record")
        mod_time_dt = datetime.datetime.now()
        mod_time_ts = mod_time_dt.timestamp()
        file_info = {
            "path": "/test/save/file.wav", "size": 1024, "mod_time": mod_time_dt,
            "duration": 5.123, "bpm": 120, "key": "C", "used": False,
            "samplerate": 44100, "channels": 2, "tags": {"genre": ["TEST"], "mood": ["HAPPY"]}
        }
        self.db_manager.save_file_record(file_info)
        retrieved = self.db_manager.get_file_record("/test/save/file.wav")

        self.assertIsNotNone(retrieved, "Record should be retrieved")
        self.assertEqual(retrieved["path"], file_info["path"])
        self.assertEqual(retrieved["size"], file_info["size"])
        self.assertAlmostEqual(retrieved["mod_time"].timestamp(), mod_time_ts, places=5)
        self.assertAlmostEqual(retrieved["duration"], file_info["duration"], places=5)
        self.assertEqual(retrieved["bpm"], file_info["bpm"])
        self.assertEqual(retrieved["key"], file_info["key"])
        self.assertEqual(retrieved["used"], file_info["used"])
        self.assertEqual(retrieved["samplerate"], file_info["samplerate"])
        self.assertEqual(retrieved["channels"], file_info["channels"])
        self.assertEqual(retrieved["tags"], file_info["tags"], "Tags dictionary mismatch")

    def test_get_nonexistent_record(self):
        """Test getting a record that hasn't been saved returns None."""
        logger.info("Running test_get_nonexistent_record")
        retrieved = self.db_manager.get_file_record("/test/nonexistent/file.wav")
        self.assertIsNone(retrieved, "Getting a non-existent record should return None")

    def test_batch_save_and_get(self):
        """Test saving multiple records via batch and retrieving them."""
        logger.info("Running test_batch_save_and_get")
        ts1 = datetime.datetime.now().timestamp()
        ts2 = ts1 + 1
        files_to_save = [
            {"path": "/batch/1.wav", "size": 100, "mod_time": ts1, "tags": {"a": ["1"]}, "bpm": 100},
            {"path": "/batch/2.flac", "size": 200, "mod_time": ts2, "tags": {"b": ["2"]}, "key": "Dm"},
        ]
        self.db_manager.save_file_records(files_to_save)

        retrieved1 = self.db_manager.get_file_record("/batch/1.wav")
        retrieved2 = self.db_manager.get_file_record("/batch/2.flac")
        retrieved_nonexistent = self.db_manager.get_file_record("/batch/nonexistent.wav")

        self.assertIsNotNone(retrieved1, "Record 1 should be retrieved")
        self.assertIsNotNone(retrieved2, "Record 2 should be retrieved")
        self.assertIsNone(retrieved_nonexistent, "Non-existent record should be None")

        if retrieved1:
             self.assertEqual(retrieved1["size"], 100)
             self.assertEqual(retrieved1["tags"], {"a": ["1"]})
             self.assertEqual(retrieved1["bpm"], 100)
        if retrieved2:
             self.assertEqual(retrieved2["size"], 200)
             self.assertEqual(retrieved2["tags"], {"b": ["2"]})
             self.assertEqual(retrieved2["key"], "Dm")

    def test_update_record_via_save(self):
        """Test that saving a record with an existing path updates it."""
        logger.info("Running test_update_record_via_save")
        path = "/update/file.mp3"
        ts1 = datetime.datetime.now().timestamp()
        ts2 = ts1 + 10

        initial_info = {
            "path": path, "size": 500, "mod_time": ts1, "bpm": 90, "tags": {"initial": ["TAG"]}
        }
        updated_info = {
            "path": path, "size": 550, "mod_time": ts2, "bpm": 95, "tags": {"updated": ["NEWTAG"]}, "key": "Am"
        }

        self.db_manager.save_file_record(initial_info)
        retrieved_initial = self.db_manager.get_file_record(path)
        self.assertIsNotNone(retrieved_initial)
        self.assertEqual(retrieved_initial["bpm"], 90)

        self.db_manager.save_file_record(updated_info)
        retrieved_updated = self.db_manager.get_file_record(path)
        self.assertIsNotNone(retrieved_updated)
        self.assertEqual(retrieved_updated["size"], 550)
        self.assertAlmostEqual(retrieved_updated["mod_time"].timestamp(), ts2, places=5)
        self.assertEqual(retrieved_updated["bpm"], 95)
        self.assertEqual(retrieved_updated["tags"], {"updated": ["NEWTAG"]})
        self.assertEqual(retrieved_updated["key"], "Am")

    def test_get_all_files(self):
        """Test retrieving all saved records."""
        logger.info("Running test_get_all_files")
        files_to_save = [
            {"path": "/all/1.wav", "size": 10},
            {"path": "/all/2.wav", "size": 20},
            {"path": "/all/sub/3.aiff", "size": 30},
        ]
        self.db_manager.save_file_records(files_to_save)

        all_files = self.db_manager.get_all_files()
        self.assertEqual(len(all_files), 3)
        retrieved_paths = {f["path"] for f in all_files}
        expected_paths = {"/all/1.wav", "/all/2.wav", "/all/sub/3.aiff"}
        self.assertEqual(retrieved_paths, expected_paths)

    def test_delete_file_record(self):
        """Test deleting a specific record."""
        logger.info("Running test_delete_file_record")
        path_to_delete = "/delete/this.wav"
        path_to_keep = "/delete/keep.wav"
        files_to_save = [
            {"path": path_to_delete, "size": 10},
            {"path": path_to_keep, "size": 20},
        ]
        self.db_manager.save_file_records(files_to_save)
        self.assertIsNotNone(self.db_manager.get_file_record(path_to_delete))
        self.db_manager.delete_file_record(path_to_delete)
        self.assertIsNone(self.db_manager.get_file_record(path_to_delete))
        self.assertIsNotNone(self.db_manager.get_file_record(path_to_keep))

    def test_delete_files_in_folder(self):
        """Test deleting records based on a folder path prefix."""
        logger.info("Running test_delete_files_in_folder")
        folder_to_clear = "/folder/to/clear"
        # Use normpath for consistency
        f1_path = os.path.normpath(os.path.join(folder_to_clear, "file1.wav"))
        f2_path = os.path.normpath(os.path.join(folder_to_clear, "sub", "file2.wav"))
        f3_path = os.path.normpath("/folder/to/keep/file3.wav")
        f4_path = os.path.normpath("/other/root/file4.wav")
        files_to_save = [
            {"path": f1_path, "size": 10}, {"path": f2_path, "size": 20},
            {"path": f3_path, "size": 30}, {"path": f4_path, "size": 40},
        ]
        self.db_manager.save_file_records(files_to_save)
        self.assertEqual(len(self.db_manager.get_all_files()), 4)
        self.db_manager.delete_files_in_folder(os.path.normpath(folder_to_clear))
        all_remaining = self.db_manager.get_all_files()
        self.assertEqual(len(all_remaining), 2)
        remaining_paths = {f["path"] for f in all_remaining}
        self.assertNotIn(f1_path, remaining_paths)
        self.assertNotIn(f2_path, remaining_paths)
        self.assertIn(f3_path, remaining_paths)
        self.assertIn(f4_path, remaining_paths)

    def test_get_files_in_folder(self):
            """Test retrieving records based on a folder path prefix (simplified paths)."""
            logger.info("Running test_get_files_in_folder (simplified paths)")

            # --- Use simpler, absolute-style paths directly ---
            target_folder = "/target/folder"
            path_in_1 = "/target/folder/fileA.wav"
            path_in_2 = "/target/folder/sub/fileB.wav"
            path_out_1 = "/target/folder_other/fileC.wav"
            path_out_2 = "/target/fileD.wav" # Different parent

            # --- Normalize paths BEFORE saving ---
            files_to_save = [
                {"path": os.path.normpath(path_in_1), "size": 11},
                {"path": os.path.normpath(path_in_2), "size": 22},
                {"path": os.path.normpath(path_out_1), "size": 33},
                {"path": os.path.normpath(path_out_2), "size": 44},
            ]
            query_folder_path = os.path.normpath(target_folder)

            # Save the records
            self.db_manager.save_file_records(files_to_save)

            # --- ADD DIRECT DB INSPECTION ---
            try:
                with self.db_manager.connection: # Use connection as context manager
                    cursor = self.db_manager.connection.cursor()
                    cursor.execute("SELECT file_path FROM files")
                    all_paths_in_db = [row[0] for row in cursor.fetchall()]
                    print(f"\nDEBUG (Direct DB Query): All paths in table = {all_paths_in_db}\n")
                    cursor.close()
            except Exception as db_e:
                print(f"\nDEBUG: Error during direct DB query: {db_e}\n")
            # --- END OF DIRECT DB INSPECTION ---

            # Call the function under test
            folder_files = self.db_manager.get_files_in_folder(query_folder_path)

            # Debugging print (keep this)
            returned_paths = [f.get('path') for f in folder_files]
            print(f"\nDEBUG (Function Result): Found files in folder '{query_folder_path}': {returned_paths}\n")

            # --- Assertions ---
            self.assertEqual(len(folder_files), 2) # This line fails
            expected_paths = {
                os.path.normpath(path_in_1),
                os.path.normpath(path_in_2)
            }
            self.assertEqual(set(returned_paths), expected_paths)
            self.assertNotIn(os.path.normpath(path_out_1), set(returned_paths))

# Standard entry point
if __name__ == "__main__":
    # Basic runner, consider using pytest for more features
    suite = unittest.TestSuite()
    # Only add tests if Alembic is available
    if ALEMBIC_AVAILABLE:
        suite.addTest(unittest.makeSuite(TestDatabaseManager))
    else:
        print("Alembic not found, skipping database tests.")

    runner = unittest.TextTestRunner()
    runner.run(suite)
