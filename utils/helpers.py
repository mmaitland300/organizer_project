"""
Helper utilities for Musicians Organizer.

This module includes functions for tag parsing/formatting, hash computation,
file size conversion, duration formatting, and opening file locations.
"""

import hashlib
import os
import platform
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Union
from PyQt5 import QtWidgets


def parse_multi_dim_tags(tag_string: str) -> dict:
    """
    Parse a string into a multi-dimensional tag dictionary.

    Tokens with a colon are split into dimension and value; tokens without are stored under "general".
    """
    if not isinstance(tag_string, str):
        raise ValueError("Tag string must be of type string")

    tokens = [tok.strip() for tok in re.split(r"[,;]", tag_string) if tok.strip()]
    tag_dict: Dict[str, List[str]] = {}
    for token in tokens:
        if ":" in token:
            dimension, tag = token.split(":", 1)
            dimension = dimension.strip().lower()
            if not dimension:
                raise ValueError(f"Empty dimension in token: {token}")
            tag = tag.strip().upper()
            tag_dict.setdefault(dimension, [])
            if tag not in tag_dict[dimension]:
                tag_dict[dimension].append(tag)
        else:
            tag_dict.setdefault("general", [])
            token_upper = token.strip().upper()
            if token_upper and token_upper not in tag_dict["general"]:
                tag_dict["general"].append(token_upper)
    return tag_dict


def format_multi_dim_tags(tag_dict: dict) -> str:
    """
    Format a tag dictionary into a human‑readable string.
    """
    parts = []
    for dimension, tags in tag_dict.items():
        dim_display = dimension.capitalize()
        tags_display = ", ".join(tags)
        parts.append(f"{dim_display}: {tags_display}")
    return "; ".join(parts)


def validate_tag_dimension(dimension: str) -> bool:
    """
    Validate a tag dimension name.
    """
    return bool(dimension) and bool(re.match(r"^[a-zA-Z0-9_]+$", dimension))


def normalize_tag(tag: str) -> str:
    """
    Normalize a tag string by stripping unwanted characters and converting to uppercase.
    """
    normalized = re.sub(r"[^\w\s-]", "", tag)
    return normalized.strip().upper()


def bytes_to_unit(size_in_bytes: Union[int, float], unit: str = "KB") -> float:
    """
    Convert file size in bytes to the specified unit.
    """
    unit = unit.upper()
    if unit == "KB":
        return size_in_bytes / 1024
    elif unit == "MB":
        return size_in_bytes / (1024**2)
    elif unit == "GB":
        return size_in_bytes / (1024**3)
    else:
        return size_in_bytes


def format_duration(seconds: Optional[Union[int, float]]) -> str:
    """
    Format a duration in seconds to mm:ss format.
    """
    if seconds is None:
        return ""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def open_file_location(file_path: str) -> None:
    """
    Open the folder containing the given file in the native file explorer.
    """
    folder = os.path.dirname(file_path)
    try:
        if platform.system() == "Windows":
            os.startfile(folder)
        elif platform.system() == "Darwin":
            subprocess.call(["open", folder])
        else:
            subprocess.call(["xdg-open", folder])
    except Exception as e:
        QtWidgets.QMessageBox.critical(
            None, "Error", f"Could not open folder:\n{str(e)}"
        )


def compute_hash(
    file_path: str,
    block_size: int = 65536,
    timeout_seconds: int = 5,
    max_hash_size: int = 250 * 1024 * 1024,
) -> Optional[str]:
    """
    Compute an MD5 hash for a file.

    Skips files that exceed max_hash_size or if the operation times out.
    """
    try:
        file_size = os.path.getsize(file_path)
        if file_size > max_hash_size:
            print(f"Skipping hash for {file_path}: file too large.")
            return None
        hash_md5 = hashlib.md5()
        start_time = time.monotonic()
        with open(file_path, "rb") as f:
            while True:
                if time.monotonic() - start_time > timeout_seconds:
                    print(f"Hashing for {file_path} timed out.")
                    return None
                chunk = f.read(block_size)
                if not chunk:
                    break
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as e:
        print(f"Error computing hash for {file_path}: {e}")
        return None


def unify_detected_key(root: str, quality: str) -> str:
    """
    Standardize the detected musical key.
    """
    root = root.lower().replace("-sharp", "#").replace("-flat", "b")
    note_letter = root[0].upper()
    remainder = root[1:]
    normalized_root = note_letter + remainder

    if not quality:
        return normalized_root

    quality = quality.lower().strip()
    if quality in {"m", "min", "minor"}:
        return f"{normalized_root}m"
    elif quality in {"maj", "major"}:
        return f"{normalized_root}maj"
    else:
        return f"{normalized_root}m"


def detect_key_from_filename(file_path: str) -> str:
    """
    Detect a musical key from the filename using a regular expression pattern.
    """
    from config.settings import KEY_REGEX

    filename_no_ext = os.path.splitext(os.path.basename(file_path))[0]
    if "--" in filename_no_ext:
        return ""
    match = KEY_REGEX.search(filename_no_ext)
    if match:
        root = match.group("root")
        quality = match.group("quality")
        return unify_detected_key(root, quality)
    return ""


def format_time(seconds: float) -> str:
    """
    Format seconds as mm:ss.
    """
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"
