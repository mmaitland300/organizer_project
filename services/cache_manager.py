"""
CacheManager - a simple JSON-based cache for storing file metadata and hashes.

This module helps avoid reprocessing files that have not changed.
"""

import os
import json
import threading
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class CacheManager:
    CACHE_FILE = os.path.expanduser("~/.musicians_organizer_cache.json")
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.cache = {}
        self._load_cache()
    
    def _load_cache(self) -> None:
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r") as f:
                    self.cache = json.load(f)
            except Exception as e:
                logger.error(f"Failed loading cache: {e}")
                self.cache = {}
    
    def save_cache(self) -> None:
        with self._lock:
            try:
                with open(self.CACHE_FILE, "w") as f:
                    json.dump(self.cache, f, indent=2)
            except Exception as e:
                logger.error(f"Failed saving cache: {e}")
    
    def get(self, file_path: str, mod_time: float, size: int) -> dict:
        key = os.path.abspath(file_path)
        entry = self.cache.get(key)
        if entry and entry.get("mod_time") == mod_time and entry.get("size") == size:
            return entry.get("data", {})
        return {}
    
    def update(self, file_path: str, mod_time: float, size: int, data: dict) -> None:
        key = os.path.abspath(file_path)
        # Convert datetime in data to timestamp
        import datetime as _dt
        cleaned = {}
        for k, v in data.items():
            if isinstance(v, _dt.datetime):
                cleaned[k] = v.timestamp()
            else:
                cleaned[k] = v
        with self._lock:
            self.cache[key] = {
                "mod_time": mod_time,
                "size": size,
                "data": cleaned
            }

    def needs_update(self, file_path: str, mod_time: float, size: int) -> bool:
        """
        Return True if no cache entry exists for this file, or if its
        stored mod_time or size differ from the current values.
        """
        key = os.path.abspath(file_path)
        entry = self.cache.get(key)
        return (
            entry is None or
            entry.get("mod_time") != mod_time or
            entry.get("size")    != size
        )

    def flush(self) -> None:
        """Persist any pending cache entries to disk."""
        self.save_cache()