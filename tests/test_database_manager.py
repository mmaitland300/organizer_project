# tests/test_database_manager.py
"""
Pytest tests for the DatabaseManager service using fixtures.
"""
import datetime
import logging
import os

import pytest  # Import pytest

# --- Alembic Check ---
try:
    # Imports needed just for the skipif condition
    from alembic import command
    from alembic.config import Config

    ALEMBIC_AVAILABLE = True
except ImportError:
    ALEMBIC_AVAILABLE = False

# Import needed for type hints if used within tests
from sqlalchemy.engine import Engine

# Import the class we are testing
from services.database_manager import DatabaseManager

# Skip all tests in this module if Alembic isn't installed
pytestmark = pytest.mark.skipif(
    not ALEMBIC_AVAILABLE, reason="Alembic is not installed"
)

logger = logging.getLogger(__name__)

# --- Test Functions (using fixtures) ---
# No Test Class needed anymore


def test_save_and_get_file_record(db_manager: DatabaseManager):  # Inject fixture
    """Test saving a single record and retrieving it accurately."""
    logger.info("Running test_save_and_get_file_record")
    mod_time_dt = datetime.datetime.now()
    mod_time_ts = mod_time_dt.timestamp()
    # Ensure file_info includes all necessary keys defined in schema/constants
    file_info = {
        "path": "/test/save/file.wav",
        "size": 1024,
        "mod_time": mod_time_dt,
        "duration": 5.123,
        "bpm": 120,
        "key": "C",
        "used": False,
        "samplerate": 44100,
        "channels": 2,
        "tags": {"genre": ["TEST"], "mood": ["HAPPY"]},
        "bit_depth": 16,
        "loudness_lufs": -14.5,
        "pitch_hz": 440.1,
        "attack_time": 0.015,
        # Example: Add placeholders for MFCCs etc if they are expected non-null by DB constraints
        # or ensure None is handled correctly by save logic/DB
        "brightness": 1500.0,
        "loudness_rms": 0.5,
        "zcr_mean": 0.1,
        "spectral_contrast_mean": 10.0,
        **{f"mfcc{i+1}_mean": float(i) for i in range(13)},  # Example MFCC data
    }
    db_manager.save_file_record(file_info)
    retrieved = db_manager.get_file_record("/test/save/file.wav")

    assert retrieved is not None, "Record should be retrieved"
    assert retrieved["path"] == file_info["path"]
    assert retrieved["size"] == file_info["size"]
    # Use pytest.approx for float comparisons
    assert retrieved["mod_time"].timestamp() == pytest.approx(mod_time_ts, abs=1e-5)
    assert retrieved["duration"] == pytest.approx(file_info["duration"], abs=1e-5)
    assert retrieved["bpm"] == file_info["bpm"]
    assert retrieved["key"] == file_info["key"]
    assert retrieved["used"] == file_info["used"]
    assert retrieved["samplerate"] == file_info["samplerate"]
    assert retrieved["channels"] == file_info["channels"]
    assert retrieved["tags"] == file_info["tags"], "Tags dictionary mismatch"
    # Assert a few feature columns
    assert retrieved["bit_depth"] == 16
    assert retrieved["loudness_lufs"] == pytest.approx(-14.5)
    assert retrieved["mfcc1_mean"] == pytest.approx(0.0)


def test_get_nonexistent_record(db_manager: DatabaseManager):  # Inject fixture
    """Test getting a record that hasn't been saved returns None."""
    logger.info("Running test_get_nonexistent_record")
    retrieved = db_manager.get_file_record("/test/nonexistent/file.wav")
    assert retrieved is None, "Getting a non-existent record should return None"


def test_batch_save_and_get(db_manager: DatabaseManager):  # Inject fixture
    """Test saving multiple records via batch and retrieving them."""
    logger.info("Running test_batch_save_and_get")
    # Use datetime objects directly for mod_time
    dt1 = datetime.datetime.now()
    dt2 = dt1 + datetime.timedelta(seconds=1)
    files_to_save = [
        {
            "path": "/batch/1.wav",
            "size": 100,
            "mod_time": dt1,
            "tags": {"a": ["1"]},
            "bpm": 100,
        },
        {
            "path": "/batch/2.flac",
            "size": 200,
            "mod_time": dt2,
            "tags": {"b": ["2"]},
            "key": "Dm",
        },
    ]
    db_manager.save_file_records(files_to_save)

    retrieved1 = db_manager.get_file_record("/batch/1.wav")
    retrieved2 = db_manager.get_file_record("/batch/2.flac")
    retrieved_nonexistent = db_manager.get_file_record("/batch/nonexistent.wav")

    assert retrieved1 is not None, "Record 1 should be retrieved"
    assert retrieved2 is not None, "Record 2 should be retrieved"
    assert retrieved_nonexistent is None, "Non-existent record should be None"

    if retrieved1:
        assert retrieved1["size"] == 100
        assert retrieved1["tags"] == {"a": ["1"]}
        assert retrieved1["bpm"] == 100
    if retrieved2:
        assert retrieved2["size"] == 200
        assert retrieved2["tags"] == {"b": ["2"]}
        assert retrieved2["key"] == "Dm"


def test_update_record_via_save(db_manager: DatabaseManager):  # Inject fixture
    """Test that saving a record with an existing path updates it."""
    logger.info("Running test_update_record_via_save")
    path = "/update/file.mp3"
    dt1 = datetime.datetime.now()
    dt2 = dt1 + datetime.timedelta(seconds=10)

    initial_info = {
        "path": path,
        "size": 500,
        "mod_time": dt1,
        "bpm": 90,
        "tags": {"initial": ["TAG"]},
    }
    # Ensure updated info also includes all necessary fields if the schema changed
    updated_info = {
        "path": path,
        "size": 550,
        "mod_time": dt2,
        "bpm": 95,
        "tags": {"updated": ["NEWTAG"]},
        "key": "Am",
        "bit_depth": 24,  # Example change/addition
    }

    db_manager.save_file_record(initial_info)
    retrieved_initial = db_manager.get_file_record(path)
    assert retrieved_initial is not None
    assert retrieved_initial["bpm"] == 90
    assert (
        retrieved_initial.get("bit_depth") is None
    )  # Assuming it wasn't in initial save

    db_manager.save_file_record(updated_info)
    retrieved_updated = db_manager.get_file_record(path)
    assert retrieved_updated is not None
    assert retrieved_updated["size"] == 550
    assert retrieved_updated["mod_time"].timestamp() == pytest.approx(
        dt2.timestamp(), abs=1e-5
    )
    assert retrieved_updated["bpm"] == 95
    assert retrieved_updated["tags"] == {"updated": ["NEWTAG"]}
    assert retrieved_updated["key"] == "Am"
    assert retrieved_updated["bit_depth"] == 24  # Check updated value


def test_get_all_files(db_manager: DatabaseManager):  # Inject fixture
    """Test retrieving all saved records."""
    logger.info("Running test_get_all_files")
    files_to_save = [
        {"path": "/all/1.wav", "size": 10},
        {"path": "/all/2.wav", "size": 20},
        {"path": "/all/sub/3.aiff", "size": 30},
    ]
    db_manager.save_file_records(files_to_save)

    all_files = db_manager.get_all_files()
    assert len(all_files) == 3  # Check count
    retrieved_paths = {f["path"] for f in all_files}
    expected_paths = {"/all/1.wav", "/all/2.wav", "/all/sub/3.aiff"}
    assert retrieved_paths == expected_paths


def test_delete_file_record(db_manager: DatabaseManager):  # Inject fixture
    """Test deleting a specific record."""
    logger.info("Running test_delete_file_record")
    path_to_delete = "/delete/this.wav"
    path_to_keep = "/delete/keep.wav"
    files_to_save = [
        {"path": path_to_delete, "size": 10},
        {"path": path_to_keep, "size": 20},
    ]
    db_manager.save_file_records(files_to_save)
    assert db_manager.get_file_record(path_to_delete) is not None
    db_manager.delete_file_record(path_to_delete)
    assert db_manager.get_file_record(path_to_delete) is None
    assert db_manager.get_file_record(path_to_keep) is not None


def test_delete_files_in_folder(db_manager: DatabaseManager):  # Inject fixture
    """Test deleting records based on a folder path prefix."""
    logger.info("Running test_delete_files_in_folder")
    folder_to_clear = "/folder/to/clear"
    # Use consistent path normalization if your save/get methods rely on it
    f1_path = os.path.normpath(os.path.join(folder_to_clear, "file1.wav"))
    f2_path = os.path.normpath(os.path.join(folder_to_clear, "sub", "file2.wav"))
    f3_path = os.path.normpath("/folder/to/keep/file3.wav")
    f4_path = os.path.normpath("/other/root/file4.wav")
    files_to_save = [
        {"path": f1_path, "size": 10},
        {"path": f2_path, "size": 20},
        {"path": f3_path, "size": 30},
        {"path": f4_path, "size": 40},
    ]
    db_manager.save_file_records(files_to_save)
    assert len(db_manager.get_all_files()) == 4  # Check initial count
    db_manager.delete_files_in_folder(os.path.normpath(folder_to_clear))
    all_remaining = db_manager.get_all_files()
    assert len(all_remaining) == 2  # Check count after delete
    remaining_paths = {f["path"] for f in all_remaining}
    assert f1_path not in remaining_paths
    assert f2_path not in remaining_paths
    assert f3_path in remaining_paths
    assert f4_path in remaining_paths


def test_get_files_in_folder(db_manager: DatabaseManager):  # Inject fixture
    """Test retrieving records based on a folder path prefix."""
    logger.info("Running test_get_files_in_folder")
    target_folder = "/target/folder"
    path_in_1 = "/target/folder/fileA.wav"
    path_in_2 = "/target/folder/sub/fileB.wav"
    path_out_1 = "/target/folder_other/fileC.wav"
    path_out_2 = "/target/fileD.wav"

    # Normalize paths consistently if needed
    files_to_save = [
        {"path": os.path.normpath(path_in_1), "size": 11},
        {"path": os.path.normpath(path_in_2), "size": 22},
        {"path": os.path.normpath(path_out_1), "size": 33},
        {"path": os.path.normpath(path_out_2), "size": 44},
    ]
    query_folder_path = os.path.normpath(target_folder)

    db_manager.save_file_records(files_to_save)
    folder_files = db_manager.get_files_in_folder(query_folder_path)
    returned_paths = {f.get("path") for f in folder_files}

    assert len(folder_files) == 2  # Check count
    expected_paths = {os.path.normpath(path_in_1), os.path.normpath(path_in_2)}
    assert returned_paths == expected_paths
    assert os.path.normpath(path_out_1) not in returned_paths
