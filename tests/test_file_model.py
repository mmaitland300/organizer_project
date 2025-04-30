# FILE: tests/test_file_model.py
# Refactored to use pytest fixtures
# Includes tests for Advanced Search functionality

import datetime
import os  # <<< Added import
import pytest
from typing import Dict, Any, List
from unittest.mock import MagicMock  # <<< Added import

from PyQt5.QtCore import Qt, QModelIndex  # <<< Added QModelIndex


from models.file_model import FileFilterProxyModel, FileTableModel

# Import the db_manager fixture type hint if needed for model init
from services.database_manager import DatabaseManager

# Assuming conftest.py provides db_manager fixture

# --- Sample Data (From User's File) ---
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
        "bit_depth": 16,
        "loudness_lufs": -15.0,
        "pitch_hz": 440.0,
        "attack_time": 0.02,
        # Add required feature keys if schema expects them (use None if nullable)
        "brightness": 1500.0,
        "loudness_rms": 0.5,
        "zcr_mean": 0.1,
        "spectral_contrast_mean": 10.0,
        **{f"mfcc{i+1}_mean": float(i) for i in range(13)},  # Example MFCC data
    }
]


# --- Fixture for FileTableModel (Existing - Unchanged) ---
@pytest.fixture
def file_model(db_manager: DatabaseManager) -> FileTableModel:
    """Creates a FileTableModel instance with sample data and db_manager"""
    import copy

    test_data = copy.deepcopy(SAMPLE_FILE_INFO_LIST)
    model = FileTableModel(test_data, db_manager=db_manager, size_unit="KB")
    return model


# --- Test Functions for FileTableModel (Existing - Unchanged) ---


def test_row_column_count(file_model: FileTableModel):
    """Test row and column counts."""
    assert file_model.rowCount() == 1
    assert file_model.columnCount() == len(file_model.COLUMN_HEADERS)


def test_data_display(file_model: FileTableModel):
    """Test retrieving display data."""
    col_index = -1
    try:
        col_index = file_model.COLUMN_HEADERS.index("File Name")
    except ValueError:
        pytest.fail("Column 'File Name' not found")
    assert col_index != -1
    index = file_model.index(0, col_index)
    assert file_model.data(index, role=Qt.DisplayRole) == "sample.wav"


def test_setData_edit(file_model: FileTableModel):
    """Test editing data via setData (may interact with db_manager)."""
    key_col_index = -1
    try:
        key_col_index = file_model.COLUMN_HEADERS.index("Key")
    except ValueError:
        pytest.fail("Column 'Key' not found")
    assert key_col_index != -1

    index = file_model.index(0, key_col_index)
    new_key_value = "Dm"

    # Mock the db save call to isolate model logic if preferred
    if hasattr(file_model, "_db_manager") and file_model._db_manager:
        file_model._db_manager.save_file_record = MagicMock()

    result = file_model.setData(index, new_key_value, role=Qt.EditRole)
    assert result is True

    updated_file_info = file_model.getFileAt(0)
    assert updated_file_info is not None
    assert updated_file_info.get("key") == new_key_value.upper()

    # Verify mock call
    if hasattr(file_model, "_db_manager") and file_model._db_manager:
        file_model._db_manager.save_file_record.assert_called_once()


# --- Test Functions for FileFilterProxyModel ---


# --- Fixture for FileFilterProxyModel (Existing - Slightly Modified) ---
@pytest.fixture
def filter_proxy_model(db_manager: DatabaseManager) -> FileFilterProxyModel:
    """Fixture for FileFilterProxyModel, using SAMPLE_FILE_INFO_LIST for defaults."""
    # Needs a source model, which needs a db_manager
    filter_test_data = [
        {"path": "/dummy/path/sample1.wav", "used": False, "size": 100},
        {"path": "/dummy/path/sample2.wav", "used": True, "size": 200},
    ]
    import copy

    for item in filter_test_data:
        base_copy = copy.deepcopy(SAMPLE_FILE_INFO_LIST[0])
        base_copy.update(item)
        item.clear()
        item.update(base_copy)
    source_model = FileTableModel(
        filter_test_data, db_manager=db_manager, size_unit="KB"
    )
    proxy = FileFilterProxyModel()
    proxy.setSourceModel(source_model)
    return proxy

    source_model = FileTableModel(
        filter_test_data, db_manager=db_manager, size_unit="KB"
    )
    proxy = FileFilterProxyModel()
    proxy.setSourceModel(source_model)
    return proxy


# --- Existing Test for FileFilterProxyModel (Unchanged) ---
def test_filter_only_unused(filter_proxy_model: FileFilterProxyModel):
    """Test filtering for unused files."""
    filter_proxy_model.set_filter_unused(True)
    assert filter_proxy_model.rowCount() == 1


# ============================================================
# == NEW TESTS FOR ADVANCED SEARCH FUNCTIONALITY           ==
# ============================================================


# --- Fixture specifically for advanced search tests (NEW) ---
@pytest.fixture
def adv_proxy_model() -> FileFilterProxyModel:
    """Clean FileFilterProxyModel instance without source model initially."""
    return FileFilterProxyModel()


# --- Tests for _parse_advanced_query (NEW) ---
@pytest.mark.parametrize(
    "query_string, expected_structure",
    [
        # Basic terms (default AND, default fields)
        (
            "kick",
            [
                {
                    "term": "kick",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                }
            ],
        ),
        (
            "kick snare",
            [
                {
                    "term": "kick",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },
                {
                    "term": "snare",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },
            ],
        ),
        # Quoted terms
        (
            '"hi hat"',
            [
                {
                    "term": "hi hat",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                }
            ],
        ),
        (
            'kick "808 snare"',
            [
                {
                    "term": "kick",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },
                {
                    "term": "808 snare",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },
            ],
        ),
        # Boolean Operators
        (
            "kick AND snare",
            [
                {
                    "term": "kick",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },
                {
                    "term": "snare",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },
            ],
        ),
        (
            "kick OR snare",
            [
                {
                    "term": "kick",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },  # First term defaults to AND link conceptually
                {
                    "term": "snare",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "OR",
                },
            ],
        ),
        (
            "loop AND NOT acoustic",
            [
                {
                    "term": "loop",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },
                {
                    "term": "acoustic",
                    "fields": ["name", "tag"],
                    "negated": True,
                    "op": "AND",
                },
            ],
        ),
        (
            "NOT closed hat",
            [
                {
                    "term": "closed",
                    "fields": ["name", "tag"],
                    "negated": True,
                    "op": "AND",
                },
                {
                    "term": "hat",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },  # NOT applies only to 'closed'
            ],
        ),
        # Field Specifiers
        (
            "tag:kick",
            [{"term": "kick", "fields": ["tag"], "negated": False, "op": "AND"}],
        ),
        (
            "name:loop",
            [{"term": "loop", "fields": ["name"], "negated": False, "op": "AND"}],
        ),
        ("key:Cm", [{"term": "Cm", "fields": ["key"], "negated": False, "op": "AND"}]),
        (
            "path:/samples/drums",
            [
                {
                    "term": "/samples/drums",
                    "fields": ["path"],
                    "negated": False,
                    "op": "AND",
                }
            ],
        ),
        (
            'tag:"hi hat"',
            [{"term": "hi hat", "fields": ["tag"], "negated": False, "op": "AND"}],
        ),
        # Combinations
        (
            "kick AND tag:808 OR name:snare",
            [
                {
                    "term": "kick",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                },
                {"term": "808", "fields": ["tag"], "negated": False, "op": "AND"},
                {"term": "snare", "fields": ["name"], "negated": False, "op": "OR"},
            ],
        ),
        (
            "name:loop NOT tag:acoustic AND key:Gm",
            [
                {"term": "loop", "fields": ["name"], "negated": False, "op": "AND"},
                {"term": "acoustic", "fields": ["tag"], "negated": True, "op": "AND"},
                {"term": "Gm", "fields": ["key"], "negated": False, "op": "AND"},
            ],
        ),
        # Edge cases
        ("", None),
        ("   ", None),
        ("AND", None),  # Operator alone
        ("NOT", None),  # Operator alone
        ("key:", None),  # Field without value
        ("AND OR", None),  # Multiple operators
        # Invalid field
        (
            "invalidfield:value",
            [
                {
                    "term": "value",
                    "fields": ["name", "tag"],
                    "negated": False,
                    "op": "AND",
                }
            ],
        ),  # Falls back to default search
    ],
)
def test_parse_advanced_query(adv_proxy_model, query_string, expected_structure):
    """Verify _parse_advanced_query correctly structures various query strings."""
    # Accessing private method for testing is acceptable
    parsed = adv_proxy_model._parse_advanced_query(query_string)
    assert parsed == expected_structure


# --- Tests for filterAcceptsRow with Advanced Queries (NEW) ---


# Helper function MODIFIED
def run_advanced_filter(proxy_model, db_manager, query, file_info_list):
    """
    Sets filter, creates REAL source model, and runs filterAcceptsRow.
    Requires db_manager fixture.
    """
    # Create a *real* FileTableModel with the test data
    # Ensure test data has necessary defaults if model requires them
    import copy

    populated_file_info = []
    for item in file_info_list:
        base_copy = copy.deepcopy(SAMPLE_FILE_INFO_LIST[0])  # Use correct base
        base_copy.update(item)
        populated_file_info.append(base_copy)

    # Instantiate real source model - requires db_manager fixture
    source_model = FileTableModel(
        populated_file_info, db_manager=db_manager, size_unit="KB"
    )

    # Set the real source model on the proxy
    proxy_model.setSourceModel(source_model)  # <<< Uses real model now

    # Set the advanced query string (which gets parsed internally)
    proxy_model.set_advanced_filter(query)

    results = []
    for i in range(len(populated_file_info)):  # Iterate up to number of files provided
        # Call filterAcceptsRow using the index relative to the source model
        results.append(proxy_model.filterAcceptsRow(i, QModelIndex()))

    return results


# Test Cases for filterAcceptsRow (Calls Modified, db_manager added)
def test_adv_filter_simple_term(adv_proxy_model, db_manager):  # <<< Added db_manager
    """Test filtering with a single default term (name/tag)."""
    query = "kick"
    files = [
        {"path": "/s/kick_808.wav", "tags": {"instr": ["KICK"]}},
        {"path": "/s/snare_basic.wav", "tags": {"type": ["DRUM"]}},
        {"path": "/s/deep_bass.wav", "tags": {"style": ["KICKDRUM"]}},
        {"path": "/s/Kickstart My Heart.mp3", "tags": {}},
    ]
    expected = [True, False, True, True]
    # Pass db_manager to helper
    assert run_advanced_filter(adv_proxy_model, db_manager, query, files) == expected


def test_adv_filter_quoted_term(
    adv_proxy_model, db_manager
):  # <<< Added db_manager if needed by helper
    """Test filtering with a quoted term (searches for exact substring)."""
    query = '"hi hat"'
    files = [
        {"path": "/s/closed_hi hat_01.wav", "tags": {}},  # Match name (exact phrase)
        {
            "path": "/s/open_hat_02.wav",
            "tags": {"instr": ["HI HAT"]},
        },  # Match tag (exact phrase)
        {
            "path": "/s/loop_with_hi_hats.wav",
            "tags": {},
        },  # Does NOT contain exact phrase "hi hat"
        {"path": "/s/ride_cymbal.wav", "tags": {}},  # No match
    ]
    # --- MODIFICATION: Corrected expected result ---
    # File 3 should NOT match because "hi hat" is not a contiguous substring
    expected = [True, True, False, False]
    # --- END MODIFICATION ---
    assert run_advanced_filter(adv_proxy_model, db_manager, query, files) == expected


def test_adv_filter_field_specifier(
    adv_proxy_model, db_manager
):  # <<< Added db_manager
    """Test filtering with field specifiers (name:, tag:, key:)."""
    query = "name:loop tag:ambient key:Am"
    files = [
        {
            "path": "/s/ambient_loop_01.wav",
            "tags": {"mood": ["AMBIENT"], "type": ["LOOP"]},
            "key": "Am",
        },
        {
            "path": "/s/dark_loop_pad.wav",
            "tags": {"mood": ["AMBIENT", "DARK"]},
            "key": "Cm",
        },
        {"path": "/s/synth_loop_arp.wav", "tags": {"type": ["ARP"]}, "key": "Am"},
        {"path": "/s/pad_texture.wav", "tags": {"mood": ["AMBIENT"]}, "key": "Am"},
        {"path": "/s/drum_loop_break.wav", "tags": {}, "key": "Dm"},
    ]
    expected = [True, False, False, False, False]
    assert run_advanced_filter(adv_proxy_model, db_manager, query, files) == expected


def test_adv_filter_boolean_logic(adv_proxy_model, db_manager):  # <<< Added db_manager
    """Test filtering with AND, OR, NOT operators."""
    query = "kick OR snare AND NOT name:acoustic"
    files = [
        {"path": "/s/kick_808.wav", "tags": {}},
        {"path": "/s/snare_hiphop.wav", "tags": {}},
        {"path": "/s/acoustic_snare_01.wav", "tags": {}},
        {"path": "/s/acoustic_kick_real.wav", "tags": {}},
        {"path": "/s/tom_drum.wav", "tags": {}},
        {"path": "/s/snare_electronic.wav", "tags": {}},
    ]
    expected = [True, True, False, False, False, True]
    assert run_advanced_filter(adv_proxy_model, db_manager, query, files) == expected


def test_adv_filter_tag_field_logic(
    adv_proxy_model, db_manager
):  # <<< Added db_manager
    """Test tag: field specifier searches all tag values."""
    query = "tag:loop"
    files = [
        {"path": "/s/beat.wav", "tags": {"type": ["LOOP", "DRUMS"]}},
        {
            "path": "/s/melody.wav",
            "tags": {"instrument": ["SYNTH"], "form": ["MELODY LOOP"]},
        },
        {"path": "/s/oneshot.wav", "tags": {"type": ["ONESHOT"]}},
        {"path": "/s/multi_tag.wav", "tags": {"general": ["FX"], "custom": ["LOOPY"]}},
        {"path": "/s/no_tags.wav", "tags": {}},
    ]
    expected = [True, True, False, True, False]
    assert run_advanced_filter(adv_proxy_model, db_manager, query, files) == expected


def test_adv_filter_combined_with_other_filters(
    adv_proxy_model, db_manager
):  # <<< Added db_manager
    """Test interaction between advanced query and other standard filters."""
    adv_proxy_model.set_filter_key("Dm")
    query = "tag:bass OR name:sub"
    files = [
        {"path": "/s/sub_bass_heavy.wav", "tags": {"instr": ["BASS"]}, "key": "Dm"},
        {"path": "/s/808_bass.wav", "tags": {"instr": ["BASS"]}, "key": "Am"},
        {"path": "/s/deep_sub.wav", "tags": {}, "key": "Dm"},
        {"path": "/s/lead_synth.wav", "tags": {}, "key": "Dm"},
    ]
    expected = [True, False, True, False]
    assert run_advanced_filter(adv_proxy_model, db_manager, query, files) == expected


# ============================================================
# == END NEW/MODIFIED TESTS                                ==
# ============================================================
