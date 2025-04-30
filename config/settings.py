"""
Configuration settings for Musicians Organizer.

Centralizes constants, dependency toggles, regex patterns, and tagging rules.
"""

import logging
import os
import re
import warnings
from typing import Optional, Any, List, Dict, Tuple, Pattern
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# --- Logging Setup ---
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# --- Global Constants ---
MAX_HASH_FILE_SIZE = 250 * 1024 * 1024  # 250 MB
HASH_TIMEOUT_SECONDS = 5  # in seconds
DB_FILENAME = os.path.expanduser("~/.musicians_organizer.db")

# --- Audio File Extensions ---
AUDIO_EXTENSIONS = {".wav", ".aiff", ".flac", ".mp3", ".ogg"}

# --- Musical Key Detection Regex ---
KEY_REGEX = re.compile(
    r"(?:^|[^a-zA-Z])"
    r"(?P<root>[A-G](?:[#b]|-sharp|-flat)?)"
    r"(?:-|_| )?"
    r"(?P<quality>m(?:in(?:or)?)?|maj(?:or)?|minor|major)?"
    r"(?:[^a-zA-Z]|$)",
    flags=re.IGNORECASE,
)

# --- BPM Detection Regex ---
BPM_REGEX = re.compile(
    # Matches common BPM patterns like "120bpm", "120 bpm", "120BPM", or just "120" if it looks like a BPM value
    # Use \b for word boundaries to avoid matching parts of other numbers.
    r"\b(?P<bpm>\d{2,3})\s?(?:bpm|BPM)?\b"
)

# --- Feature toggles ----------------------------------------------------
ENABLE_ADVANCED_AUDIO_ANALYSIS = True  # used by tests and UI
ENABLE_FILENAME_TAGGING = True
ENABLE_FOLDER_TAGGING = True
ENABLE_CONTENT_TAGGING: bool  # defined after dependency imports

# --- Auto-Tagging Parameters ---
AUTO_TAG_BPM_MAX_DURATION: float = 30.0  # seconds of audio to analyze per file

# --- Filename Patterns for Auto-Tagging ---
# Order is significant for overlapping patterns
FILENAME_TAG_PATTERNS: List[Tuple[str, Pattern[str]]] = [
    (
        "instrument",
        re.compile(
            r"\b(kick|kd|snare|sd|clap|clp|hat|hh|cymbal|cym|tom|bass|sub|synth|lead|pad|pluck|piano|guitar|vocal|vox|fx|riser|impact)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "type",
        re.compile(
            r"\b(loop|lp|one[- ]?shot|oneshot|os|drum[- ]?loop|melody|chord|arp)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "character",
        re.compile(
            r"\b(punchy|heavy|light|dark|ambient|dirty|clean|distorted|short|long|wet|dry|processed|raw)\b",
            re.IGNORECASE,
        ),
    ),
]

# --- Folder-Based Tagging Rules ---
_FOLDER_IGNORE_RE = re.compile(
    r"^(samples|library|libraries|audio|sound|sounds|packs|kits|collections|"
    r"sorted|processed|downloads|fx|misc|various|other|c|d|e|f|g|users|documents)$",
    re.IGNORECASE,
)
FOLDER_STRUCTURE_DEPTH: int = 4
_RAW_FOLDER_DIMENSION_MAP: Dict[str, str] = {
    "drums": "category",
    "synth": "category",
    "vocals": "category",
    "guitar": "category",
    "bass": "category",
    "fx": "category",
    "loops": "type",
    "oneshots": "type",
    "kick": "instrument",
    "snare": "instrument",
    "hats": "instrument",
    "cymbals": "instrument",
    "808": "instrument",
}
# Normalize and validate folder dimension map
KNOWN_DIMENSIONS = {dim for dim, _ in FILENAME_TAG_PATTERNS} | {"category"}
FOLDER_DIMENSION_MAP: Dict[str, str] = {
    folder.lower(): dim.lower() for folder, dim in _RAW_FOLDER_DIMENSION_MAP.items()
}
_invalid_dims = set(FOLDER_DIMENSION_MAP.values()) - KNOWN_DIMENSIONS
assert (
    not _invalid_dims
), f"Unknown tag dimensions in FOLDER_DIMENSION_MAP: {_invalid_dims}"

# --- Dependency Toggles & Plugin Imports ---
TinyTag: Optional[Any]
librosa: Optional[Any]
plt: Optional[Any]
np: Optional[Any]
FigureCanvas: Optional[Any]

try:
    from tinytag import TinyTag
except ImportError:
    logger.warning("tinytag module not found. Audio metadata extraction disabled.")
    TinyTag = None

try:
    import librosa
except ImportError:
    librosa = None

try:
    import matplotlib

    matplotlib.use("Qt5Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    import numpy as np
except ImportError:
    plt = None
    FigureCanvas = None
    np = None

# Set content tagging and waveform preview toggles
enable_content = librosa is not None
ENABLE_CONTENT_TAGGING = enable_content
ENABLE_WAVEFORM_PREVIEW = bool(plt and np)

# --- Audio Feature Constants ---
N_MFCC: int = 13

CORE_FEATURE_KEYS: List[str] = [
    "brightness",  # Spectral Centroid Mean
    "loudness_rms",  # RMS Energy Mean
]

SPECTRAL_FEATURE_KEYS: List[str] = [
    "zcr_mean",  # Zero-Crossing Rate Mean
    "spectral_contrast_mean",  # Mean Spectral Contrast
]

MFCC_FEATURE_KEYS: List[str] = [f"mfcc{i+1}_mean" for i in range(N_MFCC)]

ADDITIONAL_FEATURE_KEYS: List[str] = [
    "bit_depth",
    "loudness_lufs",
    "pitch_hz",
    "attack_time",
]

# --- Feature Definitions for Database and Display ---
FEATURE_DEFINITIONS: List[Tuple[str, str]] = [
    ("brightness", "Brightness (Spectral Centroid)"),
    ("loudness_rms", "Loudness (RMS)"),
    ("zcr_mean", "Zero-Crossing Rate"),
    ("spectral_contrast_mean", "Spectral Contrast"),
    *[(f"mfcc{i+1}_mean", f"MFCC {i+1}") for i in range(N_MFCC)],
    *[(key, key.replace("_", " ").title()) for key in ADDITIONAL_FEATURE_KEYS],
]

ALL_FEATURE_KEYS: List[str] = [key for key, _ in FEATURE_DEFINITIONS]
FEATURE_DISPLAY_NAMES: Dict[str, str] = dict(FEATURE_DEFINITIONS)
# --- Spectrogram Settings ---
# Defaults for STFT calculation
STFT_N_FFT: int = 2048
STFT_HOP_LENGTH: int = 512
STFT_WIN_LENGTH: Optional[int] = None  # Defaults to n_fft
STFT_WINDOW: str = "hann"  # Default window function

# Cache size for SpectrogramService (number of files/parameter sets)
SPECTROGRAM_CACHE_SIZE: int = 128
# Sanity check: display names cover all feature keys
assert all(
    key in FEATURE_DISPLAY_NAMES for key in ALL_FEATURE_KEYS
), "Mismatch between ALL_FEATURE_KEYS and FEATURE_DISPLAY_NAMES"

# --- Database column helpers -------------------------------------------
# Base columns we persist (excluding autoupdated LAST_SCANNED)
BASE_DB_COLUMNS = [
    "file_path",
    "size",
    "mod_time",
    "duration",
    "bpm",
    "file_key",
    "used",
    "samplerate",
    "channels",
    "tags",
]

# Public constant expected by tests/test_db_schema_sync.py
ALL_SAVABLE_COLUMNS = (
    BASE_DB_COLUMNS
    + ALL_FEATURE_KEYS
    + ["bit_depth", "loudness_lufs", "pitch_hz", "attack_time"]
)

# ADD Database Configuration
# Use environment variable or default
DEFAULT_DB_PATH = os.path.expanduser("~/.musicians_organizer.db")
DB_PATH = os.environ.get("MUSICORG_DB_PATH", DEFAULT_DB_PATH)
DB_URL = f"sqlite:///{DB_PATH}"

STATS_CACHE_FILENAME = os.path.expanduser("~/.musicians_organizer_stats.json")
# END Database Configuration

# ADD Engine Factory Function
_engine_instance: Optional[Engine] = None


def get_engine() -> Engine:
    """Creates and returns a single SQLAlchemy Engine instance."""
    global _engine_instance
    if _engine_instance is None:
        logger.info(f"Creating SQLAlchemy engine for URL: {DB_URL}")
        # Ensure parent directory exists
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        _engine_instance = create_engine(
            DB_URL,
            connect_args={
                "check_same_thread": False
            },  # Needed for SQLite multithreading
            echo=False,  # Set to True for debugging SQL
        )
        # Optional: Add PRAGMA event listener here if desired
    return _engine_instance
