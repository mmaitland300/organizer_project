import json
import os
import tempfile
import unittest

from services.cache_manager import CacheManager


class TestCacheManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary cache file with a valid JSON object.
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        self.temp_file.write(b"{}")
        self.temp_file.close()
        # Patch the CACHE_FILE path.
        self.original_cache_file = CacheManager.CACHE_FILE
        CacheManager.CACHE_FILE = self.temp_file.name
        self.cache_manager = CacheManager()

    def tearDown(self):
        CacheManager.CACHE_FILE = self.original_cache_file
        os.remove(self.temp_file.name)

    def test_get_update(self):
        test_path = "/dummy/path/file.txt"
        mod_time = 1234567890.0
        size = 2048
        data = {"test": "value"}
        self.assertEqual(self.cache_manager.get(test_path, mod_time, size), {})
        self.cache_manager.update(test_path, mod_time, size, data)
        self.assertEqual(self.cache_manager.get(test_path, mod_time, size), data)

    def test_save_cache(self):
        test_path = "/dummy/path/file.txt"
        mod_time = 1234567890.0
        size = 2048
        data = {"test": "value"}
        self.cache_manager.update(test_path, mod_time, size, data)
        self.cache_manager.save_cache()
        with open(self.temp_file.name, "r") as f:
            loaded = json.load(f)
        self.assertTrue(os.path.abspath(test_path) in loaded)


if __name__ == "__main__":
    unittest.main()
