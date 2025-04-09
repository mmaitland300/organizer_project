# Required Imports
import os
import json
import threading

class CacheManager:
    """JSON-based cache manager for file metadata and hash values."""
    CACHE_FILE = os.path.expanduser("~/.musicians_organizer_cache.json")
    _lock = threading.Lock()

    def __init__(self):
        self.cache = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def save_cache(self):
        with self._lock:
            with open(self.CACHE_FILE, "w") as f:
                json.dump(self.cache, f, indent=2)

    def get(self, file_path: str, mod_time: float, size: int) -> dict:
        """Return cached data if file attributes match, else an empty dict."""
        key = os.path.abspath(file_path)
        entry = self.cache.get(key)
        if entry and entry.get("mod_time") == mod_time and entry.get("size") == size:
            return entry.get("data", {})
        return {}

    def update(self, file_path: str, mod_time: float, size: int, data: dict):
        """Update cache for the given file."""
        key = os.path.abspath(file_path)
        with self._lock:
            self.cache[key] = {
                "mod_time": mod_time,
                "size": size,
                "data": data
            }
