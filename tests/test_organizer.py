import pytest
from typing import List, Dict, Any

from PyQt5 import QtCore, QtWidgets
from organizer.organizer import FileTableModel, FileFilterProxyModel, FileScanner

# Sample data for testing the model.
dummy_files: List[Dict[str, Any]] = [
    {
        'path': '/path/to/file1.mp3',
        'size': 1024,
        'mod_time': QtCore.QDateTime.currentDateTime().toPyDateTime(),
        'duration': 60,
        'bpm': 120,
        'key': "C#m",
        'used': False,
        'tags': "MP3"
    },
    {
        'path': '/path/to/file2.flac',
        'size': 2048,
        'mod_time': QtCore.QDateTime.currentDateTime().toPyDateTime(),
        'duration': 120,
        'bpm': 100,
        'key': "Dbmaj",
        'used': True,
        'tags': "FLAC"
    }
]


# Tests for FileTableModel
@pytest.fixture
def table_model() -> FileTableModel:
    """
    Returns a FileTableModel instance initialized with dummy_files.
    """
    return FileTableModel(dummy_files, size_unit="KB")


def test_file_table_model_row_count(table_model: FileTableModel) -> None:
    """
    Verify that the model returns the correct number of rows.
    """
    assert table_model.rowCount() == len(dummy_files)


def test_file_table_model_column_count(table_model: FileTableModel) -> None:
    """
    Verify that the model returns 10 columns as defined in COLUMN_HEADERS.
    """
    assert table_model.columnCount() == 10


def test_file_table_model_data_display(table_model: FileTableModel) -> None:
    """
    Verify that the file path in the first row is displayed correctly.
    """
    index = table_model.index(0, 0)
    value = table_model.data(index, role=QtCore.Qt.DisplayRole)
    assert value == dummy_files[0]['path']


def test_file_table_model_edit_duration(table_model: FileTableModel) -> None:
    """
    Test that editing the Duration cell with a valid "mm:ss" string updates the data.
    """
    index = table_model.index(0, 3)  # Duration column
    # Change duration from "60" to "2:30" (150 seconds)
    success = table_model.setData(index, "2:30", role=QtCore.Qt.EditRole)
    assert success is True, "Expected valid duration edit to succeed."
    file_info = table_model.getFileAt(0)
    assert file_info["duration"] == 150, "Duration should be updated to 150 seconds."


def test_file_table_model_edit_invalid_duration(table_model: FileTableModel) -> None:
    """
    Test that an invalid duration string (not in mm:ss) is rejected.
    """
    index = table_model.index(0, 3)
    success = table_model.setData(index, "invalid", role=QtCore.Qt.EditRole)
    assert success is False, "Expected invalid duration edit to be rejected."


def test_file_table_model_edit_bpm(table_model: FileTableModel) -> None:
    """
    Test that editing the BPM column with a valid numeric string works.
    """
    index = table_model.index(0, 4)
    success = table_model.setData(index, "130", role=QtCore.Qt.EditRole)
    assert success is True, "Expected valid BPM edit to succeed."
    file_info = table_model.getFileAt(0)
    assert file_info["bpm"] == 130, "BPM should be updated to 130."


def test_file_table_model_edit_invalid_bpm(table_model: FileTableModel) -> None:
    """
    Test that non-numeric input for BPM is rejected.
    """
    index = table_model.index(0, 4)
    success = table_model.setData(index, "abc", role=QtCore.Qt.EditRole)
    assert success is False, "Expected invalid BPM edit to be rejected."


def test_file_table_model_edit_key(table_model: FileTableModel) -> None:
    """
    Test that editing the Key column converts the input to uppercase.
    """
    index = table_model.index(0, 5)
    success = table_model.setData(index, "g#m", role=QtCore.Qt.EditRole)
    assert success is True, "Expected valid key edit to succeed."
    file_info = table_model.getFileAt(0)
    assert file_info["key"] == "G#M", "Key should be stored in uppercase."


def test_file_table_model_edit_tags(table_model: FileTableModel) -> None:
    """
    Test that editing the Tags column updates the tags.
    """
    index = table_model.index(0, 7)
    new_tags = "Rock, Pop"
    success = table_model.setData(index, new_tags, role=QtCore.Qt.EditRole)
    assert success is True, "Expected tags edit to succeed."
    file_info = table_model.getFileAt(0)
    assert file_info["tags"] == new_tags, "Tags should be updated accordingly."



# Tests for FileFilterProxyModel
@pytest.fixture
def proxy_model(table_model: FileTableModel) -> FileFilterProxyModel:
    """
    Returns a FileFilterProxyModel with table_model as its source.
    """
    proxy = FileFilterProxyModel()
    proxy.setSourceModel(table_model)
    return proxy


def test_filter_proxy_model_filtering_by_name(proxy_model: FileFilterProxyModel) -> None:
    """
    Test that filtering by a substring (e.g. "file1") returns only matching rows.
    """
    proxy_model.setFilterFixedString("file1")
    assert proxy_model.rowCount() == 1, "Expected one matching row for filter 'file1'."


def test_filter_proxy_model_only_unused(proxy_model: FileFilterProxyModel) -> None:
    """
    Test that filtering for only unused files shows only the unused ones.
    """
    proxy_model.setOnlyUnused(True)
    assert proxy_model.rowCount() == 1, "Expected one row (unused) when filtering only unused files."


def test_filter_proxy_case_insensitive(proxy_model: FileFilterProxyModel) -> None:
    """
    Test that the filter is case-insensitive.
    """
    proxy_model.setFilterFixedString("FILE1")
    assert proxy_model.rowCount() == 1, "Expected filter to be case-insensitive."



# Tests for FileScanner (non-UI, basic functionality)
def test_file_scanner_empty_directory(tmp_path) -> None:
    """
    Create an empty temporary directory and verify that scanning returns an empty list.
    """
    scanner = FileScanner(str(tmp_path), bpm_detection=False)
    captured: List = []
    scanner.finished.connect(lambda files: captured.extend(files))
    scanner.run()  # Synchronous execution for testing
    assert captured == []


def test_file_scanner_with_files(tmp_path) -> None:
    """
    Create a temporary directory with dummy text files and verify that the scanner detects them.
    """
    # Create two dummy files with a non-audio extension.
    file1 = tmp_path / "test1.txt"
    file1.write_text("Dummy content 1")
    file2 = tmp_path / "test2.txt"
    file2.write_text("Dummy content 2")
    
    scanner = FileScanner(str(tmp_path), bpm_detection=False)
    captured: List = []
    scanner.finished.connect(lambda files: captured.extend(files))
    scanner.run()
    
    # Expect two files to be scanned.
    assert len(captured) == 2, "Expected 2 files to be scanned."
    scanned_paths = {info['path'] for info in captured}
    assert str(file1.resolve()) in scanned_paths
    assert str(file2.resolve()) in scanned_paths

