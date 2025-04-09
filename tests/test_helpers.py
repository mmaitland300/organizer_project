import os
import hashlib
import tempfile
import pytest
from utils.helpers import (
    parse_multi_dim_tags,
    format_multi_dim_tags,
    validate_tag_dimension,
    normalize_tag,
    bytes_to_unit,
    format_duration,
    compute_hash,
    unify_detected_key,
    detect_key_from_filename,
    format_time
)

def test_parse_multi_dim_tags():
    # Empty string returns empty dict.
    assert parse_multi_dim_tags("") == {}
    
    # Single token without colon falls under "general".
    assert parse_multi_dim_tags("rock") == {"general": ["ROCK"]}
    
    # Multiple tokens with colon.
    tag_string = "genre:rock, mood:happy"
    expected = {"genre": ["ROCK"], "mood": ["HAPPY"]}
    assert parse_multi_dim_tags(tag_string) == expected
    
    # Mixed tokens.
    tag_string = "rock, genre:pop; mood:excited"
    expected = {"general": ["ROCK"], "genre": ["POP"], "mood": ["EXCITED"]}
    assert parse_multi_dim_tags(tag_string) == expected

def test_format_multi_dim_tags():
    tags = {"genre": ["ROCK"], "mood": ["HAPPY"]}
    result = format_multi_dim_tags(tags)
    # Order might vary so check substrings.
    assert "Genre: ROCK" in result
    assert "Mood: HAPPY" in result

def test_validate_tag_dimension():
    assert validate_tag_dimension("genre")
    assert not validate_tag_dimension("")
    assert validate_tag_dimension("rock123")
    assert not validate_tag_dimension("rock@")

def test_normalize_tag():
    assert normalize_tag("rock!") == "ROCK"
    assert normalize_tag("  pop ") == "POP"

def test_bytes_to_unit():
    # 1024 bytes should equal 1 KB
    assert bytes_to_unit(1024, "KB") == 1
    # 1048576 bytes should equal 1 MB
    assert bytes_to_unit(1048576, "MB") == 1
    # 1073741824 bytes should equal 1 GB
    assert bytes_to_unit(1073741824, "GB") == 1

def test_format_duration():
    assert format_duration(65) == "1:05"
    assert format_duration(0) == "0:00"
    assert format_duration(None) == ""

def test_compute_hash(tmp_path):
    # Create a temporary file with known content.
    file = tmp_path / "test.txt"
    file.write_text("hello world")
    expected_hash = hashlib.md5(b"hello world").hexdigest()
    result = compute_hash(str(file))
    assert result == expected_hash

def test_unify_detected_key():
    # For a minor key.
    assert unify_detected_key("c-sharp", "minor") == "C#m"
    # For a major key.
    assert unify_detected_key("d-flat", "major") == "Dbmaj"
    # No quality provided returns normalized key.
    assert unify_detected_key("e", "") == "E"

def test_detect_key_from_filename(tmp_path):
    # Create a temporary file whose name includes a key.
    file = tmp_path / "song_C#min.mp3"
    file.write_text("dummy")
    result = detect_key_from_filename(str(file))
    # One acceptable answer is "C#m" (case insensitive).
    assert result.upper() in {"C#M", "C#MIN"}

def test_format_time():
    assert format_time(65.5).startswith("1:05")
