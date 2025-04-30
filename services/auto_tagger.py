"""
services/auto_tagger.py
Enhanced AutoTagService integrating filename, folder, and key tagging.
"""

import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

# Import necessary components from settings
try:
    from config.settings import (
        ENABLE_FILENAME_TAGGING,
        ENABLE_FOLDER_TAGGING,
        FILENAME_TAG_PATTERNS,
        FOLDER_DIMENSION_MAP,
        FOLDER_STRUCTURE_DEPTH,
        KEY_REGEX,
        BPM_REGEX,  # <<< Import the new BPM_REGEX
        _FOLDER_IGNORE_RE,
    )

    # from services.analysis_engine import AnalysisEngine # Keep commented if not used
except ImportError:
    logging.critical("Failed to import settings for AutoTagService!", exc_info=True)
    # Define minimal fallbacks
    ENABLE_FILENAME_TAGGING = False
    ENABLE_FOLDER_TAGGING = False
    FILENAME_TAG_PATTERNS = []
    FOLDER_DIMENSION_MAP = {}
    FOLDER_STRUCTURE_DEPTH = 0
    KEY_REGEX = None
    BPM_REGEX = None  # <<< Add fallback
    _FOLDER_IGNORE_RE = re.compile(r"^$")

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

    @staticmethod
    def auto_tag(file_info: Dict[str, Any]) -> bool:
        """
        Applies various auto-tagging strategies (filename, folder, key, BPM)
        to the provided file_info dictionary, modifying it in place.
        Args:
            file_info: Dictionary representing file metadata. Expected keys: 'path'.
                       Modified in-place to add 'key', 'bpm', and 'tags'.
        Returns:
            bool: True if modifications were made, False otherwise.
        """
        modified = False
        path = file_info.get("path")
        if not path:
            logger.warning("auto_tag called with missing 'path' in file_info.")
            return False

        filename = os.path.basename(path)
        tags = file_info.setdefault("tags", {})
        if not isinstance(tags, dict):
            logger.warning(f"Tags for {path} are not a dict ({type(tags)}), resetting.")
            tags = {}
            file_info["tags"] = tags

        # --- 1. Filename-Based Key Extraction ---
        if KEY_REGEX:
            match = KEY_REGEX.search(filename)
            if match:
                root = match.group("root").replace("-sharp", "#").replace("-flat", "b")
                quality_match = match.group("quality")
                quality = ""
                if quality_match:
                    q_lower = quality_match.lower()
                    if q_lower.startswith("m"):
                        quality = "m"
                extracted_key = root + quality
                final_key_upper = extracted_key.upper()
                current_key = file_info.get("key")
                if current_key is None or current_key.upper() != final_key_upper:
                    logger.debug(
                        f"Extracted key '{final_key_upper}' from filename: {filename}"
                    )
                    file_info["key"] = final_key_upper
                    modified = True

        # --- 2. Filename-Based BPM Extraction --- ### NEW SECTION ###
        if (
            BPM_REGEX and file_info.get("bpm") is None
        ):  # Only extract if BPM isn't already set
            bpm_match = BPM_REGEX.search(filename)
            if bpm_match:
                try:
                    bpm_val = int(bpm_match.group("bpm"))
                    # Basic sanity check for BPM values
                    if 50 <= bpm_val <= 300:
                        logger.debug(
                            f"Extracted BPM '{bpm_val}' from filename: {filename}"
                        )
                        file_info["bpm"] = bpm_val
                        modified = True
                    else:
                        logger.debug(
                            f"Ignoring potential BPM match '{bpm_val}' (out of range 50-300) in {filename}"
                        )
                except (ValueError, IndexError):
                    logger.warning(
                        f"Could not convert potential BPM match '{bpm_match.group('bpm')}' to int in {filename}"
                    )

        # --- 3. Filename-Based Tag Extraction --- (Renumbered)
        if ENABLE_FILENAME_TAGGING:
            for dimension, pattern in FILENAME_TAG_PATTERNS:
                dim_tags = tags.setdefault(dimension, [])
                for tag_match in pattern.finditer(filename):
                    tag_value = (
                        tag_match.group(1) if tag_match.groups() else tag_match.group(0)
                    )
                    tag_value_norm = tag_value.lower().replace("-", " ")
                    if tag_value_norm not in dim_tags:
                        logger.debug(
                            f"Adding filename tag '{tag_value_norm}' to dimension '{dimension}' for: {filename}"
                        )
                        dim_tags.append(tag_value_norm)
                        modified = True

        # --- 4. Folder-Based Tag Extraction --- (Renumbered)
        if ENABLE_FOLDER_TAGGING:
            try:
                folder_path = os.path.dirname(path)
                path_parts = folder_path.replace("\\", "/").strip("/").split("/")
                relevant_parts = path_parts[-FOLDER_STRUCTURE_DEPTH:]
                for part in relevant_parts:
                    part_lower = part.lower()
                    if _FOLDER_IGNORE_RE and _FOLDER_IGNORE_RE.search(part_lower):
                        continue
                    dimension = FOLDER_DIMENSION_MAP.get(part_lower)
                    if dimension:
                        dim_tags = tags.setdefault(dimension, [])
                        tag_value_norm = part_lower
                        if tag_value_norm not in dim_tags:
                            logger.debug(
                                f"Adding folder tag '{tag_value_norm}' to dimension '{dimension}' for: {path}"
                            )
                            dim_tags.append(tag_value_norm)
                            modified = True
            except Exception as e:
                logger.error(
                    f"Error during folder-based tagging for {path}: {e}", exc_info=False
                )

        # --- Cleanup: Remove empty tag dimensions ---
        for dimension in list(tags.keys()):
            if not tags[dimension]:
                del tags[dimension]

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
