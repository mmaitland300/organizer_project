"""
utils.py

Helper functions and constants for Musicians Organizer.
These utilities are for file size conversion, file hashing,
and filename-based musical key detection.
"""

import os
import re
import platform
import subprocess
import hashlib
import time
import logging
from typing import Union, Optional
from PyQt5 import QtWidgets

logger = logging.getLogger(__name__)

# Constants for hash computation
MAX_HASH_FILE_SIZE = 250 * 1024 * 1024  # 250 MB
HASH_TIMEOUT_SECONDS = 5  # 5 seconds

# Regex for detecting keys (e.g., "C#m", "Db", "A-flat")
KEY_REGEX = re.compile(
    r'(?:^|[^a-zA-Z])'                  # Start of string or non-alpha
    r'(?P<root>[A-G]'                   # Root letter
    r'(?:[#b]|-sharp|-flat)?'           # Optional #, b, -sharp, -flat
    r')'                                # End capture group for root
    r'(?:-|_| )?'                       # Optional dash/underscore/space
    r'(?P<quality>m(?:in(?:or)?)?|maj(?:or)?|minor|major)?'  # Optional chord quality
    r'(?:[^a-zA-Z]|$)',                 # Non-alpha or end of string
    flags=re.IGNORECASE
)

def bytes_to_unit(size_in_bytes: Union[int, float], unit: str = "KB") -> float:
    """
    Convert a file size from bytes to the specified unit.

    Args:
        size_in_bytes (int or float): The size in bytes.
        unit (str): The target unit for conversion. Must be one of "KB", "MB", or "GB".

    Returns:
        float: The size converted to the specified unit.
    """
    unit = unit.upper()
    if unit == "KB":
        return size_in_bytes / 1024
    elif unit == "MB":
        return size_in_bytes / (1024 ** 2)
    elif unit == "GB":
        return size_in_bytes / (1024 ** 3)
    else:
        return size_in_bytes

def format_duration(seconds: Optional[Union[int, float]]) -> str:
    """
    Convert a duration in seconds to a mm:ss string format.
    
    Args:
        seconds (float or None): The duration in seconds.
    
    Returns:
        str: Formatted string (e.g., "3:27") or empty if None.
    """
    if seconds is None:
        return ""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"

def open_file_location(file_path: str) -> None:
    """
    Open the folder containing the given file in the OS file explorer.
    If an error occurs, display a critical message via QMessageBox.
    
    Args:
        file_path (str): The path to the file whose folder should be opened.
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
        QtWidgets.QMessageBox.critical(None, "Error", f"Could not open folder:\n{str(e)}")

def compute_hash(file_path: str, block_size: int = 65536,
                 timeout_seconds: int = HASH_TIMEOUT_SECONDS,
                 max_hash_size: int = MAX_HASH_FILE_SIZE) -> Optional[str]:
    """
    Compute the MD5 hash of a file. Skips files that exceed max_hash_size
    or if hashing exceeds timeout_seconds.

    Args:
        file_path (str): The path of the file to be hashed.
        block_size (int): The chunk size for reading the file in bytes.
        timeout_seconds (int): Timeout in seconds for reading the file.
        max_hash_size (int): Maximum file size in bytes to be hashed.

    Returns:
        str or None: The MD5 hash string, or None if skipped or an error occurred.
    """
    try:
        file_size = os.path.getsize(file_path)
        if file_size > max_hash_size:
            print(f"Skipping hash for {file_path}: size {file_size} exceeds limit.")
            return None
        hash_md5 = hashlib.md5()
        start_time = time.monotonic()
        with open(file_path, "rb") as f:
            while True:
                if time.monotonic() - start_time > timeout_seconds:
                    print(f"Hash for {file_path} timed out.")
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
    Convert key related strings like root='c#' or 'c-sharp' and quality='m', 'min', 'major'
    into a final standardized key format like 'C#m' or 'C#maj'.

    Args:
        root (str): The note root (e.g., 'c#', 'db').
        quality (str): The chord quality (e.g., 'm', 'min', 'maj', 'major').

    Returns:
        str: The standardized key (e.g., 'C#m' or 'C#maj').
    """
    # Normalize the root to replace '-sharp' or '-flat'
    root = root.lower().replace('-sharp', '#').replace('-flat', 'b')
    note_letter = root[0].upper()
    remainder = root[1:]
    normalized_root = note_letter + remainder

    if not quality:
        # If no quality is provided, return just the root.
        return normalized_root

    quality = quality.lower().strip()
    # Check explicitly for minor and major qualities.
    if quality in {"m", "min", "minor"}:
        return f"{normalized_root}m"
    elif quality in {"maj", "major"}:
        return f"{normalized_root}maj"
    else:
        # If unknown, fallback to treating it as minor
        return f"{normalized_root}m"

def detect_key_from_filename(file_path: str) -> str:
    """
    Return a standardized key string (e.g., 'C#m', 'Dbmaj') if found in the filename;
    otherwise return an empty string.

    Args:
        file_path (str): The full path to the file.

    Returns:
        str: The detected key or an empty string if none found.
    """
    filename_no_ext = os.path.splitext(os.path.basename(file_path))[0]
    match = KEY_REGEX.search(filename_no_ext)
    if match:
        root = match.group('root')       # e.g. 'c#' or 'c-sharp'
        quality = match.group('quality') # e.g. 'min', 'm', 'maj'
        return unify_detected_key(root, quality)
    return ""

