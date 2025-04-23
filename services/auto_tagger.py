"""
services/auto_tagger.py
Enhanced AutoTagService integrating filename, folder, and key tagging.
"""

import logging
import os
import re
from typing import Any, Dict, List

from config.settings import (
    ENABLE_FILENAME_TAGGING,
    ENABLE_FOLDER_TAGGING,
    FILENAME_TAG_PATTERNS,
    FOLDER_STRUCTURE_DEPTH,
    FOLDER_DIMENSION_MAP,
    _FOLDER_IGNORE_RE,
)
from utils.helpers import detect_key_from_filename

logger = logging.getLogger(__name__)

class AutoTagService:
    """
    Service for enhanced auto-tagging of audio files.

    Methods apply filename-based, folder-based, and key-detection tags,
    respecting toggles in settings.
    """

    @staticmethod
    def _add_tag(tags: Dict[str, List[str]], dimension: str, value: str) -> bool:
        """
        Normalize and add a tag to tags[dimension]; avoid duplicates.
        Returns True if added.
        """
        if not dimension or not value:
            return False
        dim = dimension.lower().strip()
        val = value.strip().upper()
        if not val:
            return False
        lst = tags.setdefault(dim, [])
        if val not in lst:
            lst.append(val)
            return True
        return False

    @classmethod
    def _tag_from_filename(cls, file_info: Dict[str, Any]) -> bool:
        """
        Apply ordered filename regex patterns to extract tags.
        """
        if not ENABLE_FILENAME_TAGGING:
            return False
        path = file_info.get("path", "")
        name = os.path.splitext(os.path.basename(path))[0]
        if not name:
            return False
        tags = file_info.setdefault("tags", {})
        modified = False
        for dimension, pattern in FILENAME_TAG_PATTERNS:
            try:
                for m in pattern.finditer(name):
                    tag_value = m.group(1) or m.group(0)
                    if tag_value and cls._add_tag(tags, dimension, tag_value):
                        modified = True
            except Exception as e:
                logger.error(f"Filename tagging error [{dimension}] on {name}: {e}")
        return modified

    @classmethod
    def _tag_from_path(cls, file_info: Dict[str, Any]) -> bool:
        """
        Map folder names to tags based on FOLDER_DIMENSION_MAP.
        """
        if not ENABLE_FOLDER_TAGGING:
            return False
        path = file_info.get("path", "")
        if not path:
            return False
        tags = file_info.setdefault("tags", {})
        parts = os.path.normpath(path).split(os.sep)
        dirs = parts[:-1]
        to_check = dirs[-FOLDER_STRUCTURE_DEPTH:]
        modified = False
        for part in reversed(to_check):
            seg = part.strip()
            if not seg or _FOLDER_IGNORE_RE.match(seg):
                continue
            key = seg.lower()
            dim = FOLDER_DIMENSION_MAP.get(key)
            if dim:
                if cls._add_tag(tags, dim, seg):
                    modified = True
        return modified

    @classmethod
    def _tag_from_key(cls, file_info: Dict[str, Any]) -> bool:
        """
        Detect musical key via filename and update file_info['key'].
        """
        path = file_info.get("path", "")
        if not path:
            return False
        original = file_info.get("key", "")
        try:
            detected = detect_key_from_filename(path) or ""
        except Exception as e:
            logger.error(f"Key detection error on {path}: {e}")
            return False
        new = detected.strip() or original
        if new and new != original:
            file_info["key"] = new
            return True
        return False

    @classmethod
    def auto_tag(cls, file_info: Dict[str, Any]) -> bool:
        """
        Apply all tagging steps to a single file_info in place.
        Returns True if any modification occurred.
        """
        if not isinstance(file_info, dict):
            return False
        file_info.setdefault("tags", {})
        modified = False
        if cls._tag_from_filename(file_info): modified = True
        if cls._tag_from_path(file_info):     modified = True
        if cls._tag_from_key(file_info):      modified = True
        return modified

    @classmethod
    def auto_tag_files(cls, files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Batch process a list of file_info dicts, applying auto_tag to each.
        Returns the same list (modified in place).
        """
        for fi in files:
            try:
                cls.auto_tag(fi)
            except Exception as e:
                logger.error(f"auto_tag_files error on {fi.get('path')}: {e}")
        return files
