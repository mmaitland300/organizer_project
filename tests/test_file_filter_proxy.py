# tests/test_file_filter_proxy.py
import pytest
from models.file_model import FileTableModel, FileFilterProxyModel
from PyQt5.QtCore import Qt

@pytest.fixture
def sample_files():
    # Include various feature values
    return [
        {"db_id": 1, "path": "a.wav", "loudness_lufs": -10.0, "bit_depth": 16, "pitch_hz": 440.0, "attack_time": 0.005},
        {"db_id": 2, "path": "b.wav", "loudness_lufs": -20.0, "bit_depth": 24, "pitch_hz": 880.0, "attack_time": 0.010},
        {"db_id": 3, "path": "c.wav", "loudness_lufs": None, "bit_depth": None, "pitch_hz": None, "attack_time": None},
    ]

@pytest.fixture
def proxy_model(sample_files):
    table = FileTableModel(sample_files)
    proxy = FileFilterProxyModel()
    proxy.setSourceModel(table)
    return proxy

@ pytest.mark.parametrize("min_lufs,max_lufs,expected_ids", [
    (-15.0, None, [1]),  # only -10 > -15
    (None, -15.0, [2]),  # only -20 < -15
    (-25.0, -5.0, [1,2]), # both in range
    (None, None, [1,2,3]), # no filter
])
def test_lufs_filter(proxy_model, sample_files, min_lufs, max_lufs, expected_ids):
    proxy_model.set_filter_lufs_range(min_lufs, max_lufs)
    ids = [sample_files[proxy_model.mapToSource(proxy_model.index(i,0)).row()]['db_id']
           for i in range(proxy_model.rowCount())]
    assert set(ids) == set(expected_ids)

@ pytest.mark.parametrize("bit_depth,expected_ids", [
    (16, [1]),
    (24, [2]),
    (None, [1,2,3]),
])
def test_bit_depth_filter(proxy_model, sample_files, bit_depth, expected_ids):
    proxy_model.set_filter_bit_depth(bit_depth)
    ids = [sample_files[proxy_model.mapToSource(proxy_model.index(i,0)).row()]['db_id']
           for i in range(proxy_model.rowCount())]
    assert set(ids) == set(expected_ids)

@ pytest.mark.parametrize("min_pitch,max_pitch,expected_ids", [
    (400.0, None, [1]),
    (None, 600.0, [1]),
    (400.0, 900.0, [1,2]),
    (None, None, [1,2,3]),
])
def test_pitch_filter(proxy_model, sample_files, min_pitch, max_pitch, expected_ids):
    proxy_model.set_filter_pitch_hz_range(min_pitch, max_pitch)
    ids = [sample_files[proxy_model.mapToSource(proxy_model.index(i,0)).row()]['db_id']
           for i in range(proxy_model.rowCount())]
    assert set(ids) == set(expected_ids)

@ pytest.mark.parametrize("min_ms,max_ms,expected_ids", [
    (5, None, [1]),   # file a: 5ms => 0.005s
    (None, 7, [1]),   # only a <=7ms
    (5, 10, [1,2]),   # both a and b
    (None, None, [1,2,3]),
])
def test_attack_time_filter(proxy_model, sample_files, min_ms, max_ms, expected_ids):
    # Convert ms to seconds in setter
    min_s = None if min_ms is None else min_ms / 1000.0
    max_s = None if max_ms is None else max_ms / 1000.0
    proxy_model.set_filter_attack_time_range(min_s, max_s)
    ids = [sample_files[proxy_model.mapToSource(proxy_model.index(i,0)).row()]['db_id']
           for i in range(proxy_model.rowCount())]
    assert set(ids) == set(expected_ids)
