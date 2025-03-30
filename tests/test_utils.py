import os
import tempfile
import hashlib
import time
import pytest
from typing import Optional, Union

from organizer.utils import (
    bytes_to_unit,
    format_duration,
    compute_hash,
    unify_detected_key,
    detect_key_from_filename,
)


# Tests for bytes_to_unit function
@pytest.mark.parametrize("size, unit, expected", [
    (1024, "KB", 1),
    (1024 * 1024, "MB", 1),
    (1024 ** 3, "GB", 1),
    (2048, "KB", 2),
    (2048, "MB", 2048 / (1024 ** 2)),
    (2048, "GB", 2048 / (1024 ** 3)),
])
def test_bytes_to_unit(size: Union[int, float], unit: str, expected: float) -> None:
    result = bytes_to_unit(size, unit)
    assert abs(result - expected) < 1e-6, f"Expected {expected}, got {result}"



# Tests for format_duration function
@pytest.mark.parametrize("seconds, expected", [
    (None, ""),
    (0, "0:00"),
    (60, "1:00"),
    (90, "1:30"),
    (3599, "59:59"),
])
def test_format_duration(seconds: Optional[Union[int, float]], expected: str) -> None:
    result = format_duration(seconds)
    assert result == expected, f"Expected '{expected}', got '{result}'"



# Tests for compute_hash function
def test_compute_hash_normal() -> None:
    """
    Create a temporary file with known content and verify the MD5 hash.
    """
    content = b"Hello, World!"
    expected_hash = hashlib.md5(content).hexdigest()
    
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(content)
        tmp_file_path = tmp_file.name

    try:
        result = compute_hash(tmp_file_path)
        assert result == expected_hash, f"Expected hash {expected_hash}, got {result}"
    finally:
        os.remove(tmp_file_path)


def test_compute_hash_large_file(monkeypatch) -> None:
    """
    Simulate a file exceeding the maximum allowed size for hashing.
    """
    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(b"Test")
        tmp_file_path = tmp_file.name

    monkeypatch.setattr(os.path, "getsize", lambda path: 250 * 1024 * 1024 + 1)
    try:
        result = compute_hash(tmp_file_path)
        assert result is None, "Expected None for file exceeding max size"
    finally:
        os.remove(tmp_file_path)


def test_compute_hash_error(monkeypatch) -> None:
    """
    Simulate an error during file reading (e.g., IOError) to verify that compute_hash returns None.
    """
    def fake_open(*args, **kwargs):
        raise IOError("Fake error")
    monkeypatch.setattr("builtins.open", fake_open)
    result = compute_hash("non_existent_file.txt")
    assert result is None, "Expected None when an exception occurs during file reading"



# Tests for unify_detected_key function
@pytest.mark.parametrize("root, quality, expected", [
    ("c#", "m", "C#m"),
    ("c-sharp", "min", "C#m"),
    ("db", "maj", "Dbmaj"),
    ("a", "", "A"),
    ("g", "minor", "Gm"),
    ("f", "major", "Fmaj"),
])
def test_unify_detected_key(root: str, quality: str, expected: str) -> None:
    result = unify_detected_key(root, quality)
    assert result == expected, f"Expected {expected}, got {result}"


def test_unify_detected_key_no_quality() -> None:
    """
    Test that if quality is empty, the function returns just the normalized root.
    """
    result = unify_detected_key("c#", "")
    assert result == "C#", f"Expected 'C#', got '{result}'"



# Tests for detect_key_from_filename function
@pytest.mark.parametrize("filename, expected", [
    ("sample_C#m.mp3", "C#m"),
    ("beat_dbmaj.flac", "Dbmaj"),
    ("track_Amin.wav", "Am"),
    ("no_key_here.mp3", ""),
    ("C-sharp minor sample.mp3", "C#m"),
    ("song F major.mp3", "Fmaj"),
])
def test_detect_key_from_filename(tmp_path, filename: str, expected: str) -> None:
    file_path = tmp_path / filename
    file_path.write_text("dummy content")
    result = detect_key_from_filename(str(file_path))
    assert result == expected, f"For filename '{filename}', expected '{expected}', got '{result}'"


@pytest.mark.parametrize("filename, expected", [
    ("unknown_format.mp3", ""),
    ("song_without_key.flac", ""),
    ("C--maj.mp3", ""),
])
def test_detect_key_from_filename_no_key(tmp_path, filename: str, expected: str) -> None:
    """
    Test that filenames with no recognizable key return an empty string.
    """
    file_path = tmp_path / filename
    file_path.write_text("dummy content")
    result = detect_key_from_filename(str(file_path))
    assert result == expected, f"For filename '{filename}', expected '{expected}', got '{result}'"
