import os
import pytest
from datetime import datetime
from PyQt5.QtTest import QSignalSpy
from core.duplicate_finder import DuplicateFinder

@pytest.fixture
def sample_files_with_duplicates(tmp_path):
    # Create a temporary directory with duplicate files.
    dir_path = tmp_path / "dup_dir"
    dir_path.mkdir()
    file1 = dir_path / "dup1.mp3"
    file2 = dir_path / "dup2.mp3"
    file3 = dir_path / "unique.mp3"
    file1.write_text("same content")
    file2.write_text("same content")
    file3.write_text("different content")
    files_info = []
    for file in [file1, file2, file3]:
        info = {
            'path': str(file),
            'size': os.path.getsize(file),
            'mod_time': datetime.fromtimestamp(os.path.getmtime(file)),
            'duration': None,
            'bpm': None,
            'key': "N/A",
            'used': False,
            'tags': {}
        }
        files_info.append(info)
    return files_info

def test_duplicate_finder(qtbot, sample_files_with_duplicates):
    finder = DuplicateFinder(sample_files_with_duplicates)
    spy = QSignalSpy(finder.finished)
    finder.start()  # Do NOT call qtbot.addWidget here since finder is not a QWidget
    assert spy.wait(5000)
    duplicate_groups = spy[0][0]
    # Expect one duplicate group (the two files with "same content").
    assert isinstance(duplicate_groups, list)
    found = any(len(group) == 2 for group in duplicate_groups)
    assert found


