# FILE: tests/test_file_model.py
# Refactored to use pytest fixtures

import datetime
import pytest # Import pytest
from typing import Dict, Any, List # Add typing for hints

from PyQt5.QtCore import Qt

from models.file_model import FileFilterProxyModel, FileTableModel
# Import the db_manager fixture type hint
from services.database_manager import DatabaseManager
# Assuming conftest.py is in the same directory or parent searchable by pytest

# Define sample data at module level or within fixtures
SAMPLE_FILE_INFO_LIST: List[Dict[str, Any]] = [
    {
        "path": "/dummy/path/sample.wav",
        "size": 2048,
        "mod_time": datetime.datetime(2020, 1, 1, 12, 0, 0),
        "duration": 125,
        "bpm": 120,
        "key": "C#m",
        "used": False,
        "samplerate": 44100,
        "channels": 2,
        "tags": {"genre": ["ROCK"]},
        # Add other fields expected by the model/DB if necessary
        "bit_depth": 16, "loudness_lufs": -15.0, "pitch_hz": 440.0, "attack_time": 0.02,
        # Add required feature keys if schema expects them (use None if nullable)
        'brightness': 1500.0, 'loudness_rms': 0.5, 'zcr_mean': 0.1, 'spectral_contrast_mean': 10.0,
        **{f'mfcc{i+1}_mean': float(i) for i in range(13)} # Example MFCC data
    }
]

# --- Fixture for FileTableModel ---
@pytest.fixture
def file_model(db_manager: DatabaseManager) -> FileTableModel:
    """ Creates a FileTableModel instance with sample data and db_manager """
    # Use deepcopy if tests might modify the list/dicts, otherwise shallow copy is fine
    import copy
    test_data = copy.deepcopy(SAMPLE_FILE_INFO_LIST)
    # Pass the db_manager fixture during instantiation
    model = FileTableModel(test_data, db_manager=db_manager, size_unit="KB")
    return model

# --- Test Functions for FileTableModel ---

def test_row_column_count(file_model: FileTableModel):
    """ Test row and column counts. """
    assert file_model.rowCount() == 1
    assert file_model.columnCount() == len(file_model.COLUMN_HEADERS)

def test_data_display(file_model: FileTableModel):
    """ Test retrieving display data. """
    # Get index based on header name for robustness
    col_index = -1
    try:
        col_index = file_model.COLUMN_HEADERS.index("File Name")
    except ValueError:
        pytest.fail("Column 'File Name' not found in FileTableModel.COLUMN_HEADERS")
    assert col_index != -1

    index = file_model.index(0, col_index)
    assert file_model.data(index, role=Qt.DisplayRole) == "sample.wav"

def test_setData_edit(file_model: FileTableModel):
    """ Test editing data via setData (which now uses db_manager). """
    # Find index dynamically based on header name
    key_col_index = -1
    try:
        key_col_index = file_model.COLUMN_HEADERS.index("Key")
    except ValueError:
        pytest.fail("Column 'Key' not found in FileTableModel.COLUMN_HEADERS")
    assert key_col_index != -1

    index = file_model.index(0, key_col_index)
    new_key_value = "Dm"
    result = file_model.setData(index, new_key_value, role=Qt.EditRole)

    # Assert that setData returned True (indicating success)
    assert result is True

    # Verify the change in the model's internal data store
    updated_file_info = file_model.getFileAt(0)
    assert updated_file_info is not None, "getFileAt(0) should return the updated dict"
    # Check the actual key value, considering potential case changes by setData/helpers
    assert updated_file_info.get("key") == new_key_value.upper() # Code converts input to uppercase

    # Optional: Verify the change was persisted in the test DB
    # This requires the db_manager fixture again
    retrieved_from_db = file_model._db_manager.get_file_record(updated_file_info['path'])
    assert retrieved_from_db is not None, "Record should exist in DB after successful setData"
    assert retrieved_from_db.get("key") == new_key_value.upper(), "Key change not reflected in DB"


# --- Test Functions for FileFilterProxyModel ---
# (Also refactored to use pytest style)

@pytest.fixture
def filter_proxy_model(db_manager: DatabaseManager) -> FileFilterProxyModel:
    """ Fixture for FileFilterProxyModel. """
    # Needs a source model, which needs a db_manager
    filter_test_data = [
        {"path": "/dummy/path/sample1.wav", "used": False, "size": 100}, # Add size/mod_time if needed by model init/logic
        {"path": "/dummy/path/sample2.wav", "used": True, "size": 200},
    ]
    # Ensure all required fields for FileTableModel are present
    for item in filter_test_data:
        item.setdefault("mod_time", datetime.datetime.now())
        # Add other defaults from SAMPLE_FILE_INFO_LIST if FileTableModel requires them
        for key, value in SAMPLE_FILE_INFO_LIST[0].items():
             if key not in ['path', 'used', 'size', 'mod_time']: # Avoid overwriting specific test values
                  item.setdefault(key, value)


    source_model = FileTableModel(filter_test_data, db_manager=db_manager, size_unit="KB")
    proxy = FileFilterProxyModel()
    proxy.setSourceModel(source_model)
    return proxy

def test_filter_only_unused(filter_proxy_model: FileFilterProxyModel):
    """ Test filtering for unused files. """
    filter_proxy_model.set_filter_unused(True)
    # invalidateFilter() is called automatically by the setter now
    assert filter_proxy_model.rowCount() == 1