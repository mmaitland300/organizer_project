import os
from datetime import datetime
import pytest
from PyQt5.QtCore import Qt
from models.file_model import FileTableModel

@pytest.fixture
def sample_files():
    return [
        {
            'path': '/tmp/sample1.mp3',
            'size': 2048,
            'mod_time': datetime(2021, 1, 1, 12, 0, 0),
            'duration': 120,
            'bpm': 100,
            'key': 'C#m',
            'used': False,
            'samplerate': 44100,
            'channels': 2,
            'tags': {"genre": ["ROCK"]}
        },
        {
            'path': '/tmp/sample2.mp3',
            'size': 4096,
            'mod_time': datetime(2021, 1, 2, 12, 0, 0),
            'duration': 180,
            'bpm': 110,
            'key': 'Dbmaj',
            'used': True,
            'samplerate': 48000,
            'channels': 2,
            'tags': {"mood": ["HAPPY"]}
        }
    ]

def test_row_and_column_counts(sample_files):
    model = FileTableModel(sample_files, size_unit="KB")
    assert model.rowCount() == 2
    # Expect 11 columns.
    assert model.columnCount() == 11

def test_data_display(sample_files):
    model = FileTableModel(sample_files, size_unit="KB")
    index = model.index(0, 1)  # Column 1 should be File Name.
    file_name = model.data(index, role=Qt.DisplayRole)
    assert file_name == os.path.basename(sample_files[0]['path'])
