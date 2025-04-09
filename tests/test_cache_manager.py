import os
import json
import pytest
from utils.cache_manager import CacheManager

@pytest.fixture
def temp_cache_file(tmp_path):
    # Override the CacheManager's file for testing.
    cache_file = tmp_path / "cache.json"
    original_cache_file = CacheManager.CACHE_FILE
    CacheManager.CACHE_FILE = str(cache_file)
    yield cache_file
    CacheManager.CACHE_FILE = original_cache_file

def test_cache_update_and_get(temp_cache_file):
    cm = CacheManager()
    test_path = "/tmp/testfile.txt"
    mod_time = 1234567890.0
    size = 1024
    data = {"duration": 60, "bpm": 120}
    cm.update(test_path, mod_time, size, data)
    result = cm.get(test_path, mod_time, size)
    assert result == data

def test_cache_save_and_load(temp_cache_file):
    cm = CacheManager()
    test_path = "/tmp/testfile.txt"
    mod_time = 1234567890.0
    size = 1024
    data = {"key": "C#m"}
    cm.update(test_path, mod_time, size, data)
    cm.save_cache()
    # Create a new instance to force reloading from the file.
    cm_new = CacheManager()
    result = cm_new.get(test_path, mod_time, size)
    assert result == data
