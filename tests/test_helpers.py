import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

from utils.helpers import (
    bytes_to_unit,
    compute_hash,
    format_duration,
    format_multi_dim_tags,
    open_file_location,
    parse_multi_dim_tags,
)


class TestHelpers(unittest.TestCase):
    def test_parse_multi_dim_tags(self):
        tag_string = "genre:rock, mood:happy; energetic"
        result = parse_multi_dim_tags(tag_string)
        expected = {"genre": ["ROCK"], "mood": ["HAPPY"], "general": ["ENERGETIC"]}
        self.assertEqual(result, expected)

    def test_format_multi_dim_tags(self):
        tag_dict = {"genre": ["ROCK"], "mood": ["HAPPY"]}
        result = format_multi_dim_tags(tag_dict)
        self.assertIn("Genre: ROCK", result)
        self.assertIn("Mood: HAPPY", result)

    def test_bytes_to_unit(self):
        self.assertAlmostEqual(bytes_to_unit(1024, "KB"), 1.0)
        self.assertAlmostEqual(bytes_to_unit(1024 * 1024, "MB"), 1.0)
        self.assertAlmostEqual(bytes_to_unit(1024**3, "GB"), 1.0)

    def test_format_duration(self):
        self.assertEqual(format_duration(125), "2:05")
        self.assertEqual(format_duration(None), "")

    def test_compute_hash(self):
        # Create a temporary file with known content.
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(b"test content")
            tmp.flush()
            file_path = tmp.name
        try:
            result = compute_hash(file_path)
            expected = hashlib.md5(b"test content").hexdigest()
            self.assertEqual(result, expected)
        finally:
            os.remove(file_path)

    def test_open_file_location(self):
        # Instead of calling the actual os.startfile,
        # we patch it to prevent an access violation.
        with patch("os.startfile") as mock_startfile:
            # Call the function with a dummy file path.
            open_file_location("/dummy/path/file.txt")
            # Check that os.startfile was called with the directory part.
            mock_startfile.assert_called_once_with("/dummy/path")


if __name__ == "__main__":
    unittest.main()
