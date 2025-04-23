"""
Configuration settings for Musicians Organizer.

Centralizes constants, dependency toggles, regex patterns, and tagging rules.
"""
import logging
import os
import re
import warnings
from typing import Optional, Any, List, Dict, Tuple, Pattern

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

# --- Feature Toggles ---
# Enable or disable specific auto-tagging sources
ENABLE_FILENAME_TAGGING = True
ENABLE_FOLDER_TAGGING = True
# Content tagging depends on advanced analysis availability
# (set after librosa import)
ENABLE_CONTENT_TAGGING: bool  # defined later

# --- Auto-Tagging Parameters ---
AUTO_TAG_BPM_MAX_DURATION: float = 30.0  # seconds of audio to analyze per file

# --- Filename Patterns for Auto-Tagging ---
# Order is significant: first match wins for overlapping patterns
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
# Ignore common folder names via a single regex for performance
_FOLDER_IGNORE_RE = re.compile(
    r"^(samples|library|libraries|audio|sound|sounds|packs|kits|collections|"
    r"sorted|processed|downloads|fx|misc|various|other|c|d|e|f|g|users|documents)$",
    re.IGNORECASE,
)

# Depth of folder ancestry to inspect for tags
FOLDER_STRUCTURE_DEPTH: int = 4

# Raw mapping from folder keyword to tag dimension
_RAW_FOLDER_DIMENSION_MAP: Dict[str, str] = {
    'drums':    'category',
    'synth':    'category',
    'vocals':   'category',
    'guitar':   'category',
    'bass':     'category',
    'fx':       'category',
    'loops':    'type',
    'oneshots': 'type',
    'kick':     'instrument',
    'snare':    'instrument',
    'hats':     'instrument',
    'cymbals':  'instrument',
    '808':      'instrument',
}
# Normalize and validate folder dimension map
KNOWN_DIMENSIONS = {dim for dim, _ in FILENAME_TAG_PATTERNS} | {'category'}
FOLDER_DIMENSION_MAP: Dict[str, str] = {
    folder.lower(): dim.lower()
    for folder, dim in _RAW_FOLDER_DIMENSION_MAP.items()
}
_invalid_dims = set(FOLDER_DIMENSION_MAP.values()) - KNOWN_DIMENSIONS
assert not _invalid_dims, f"Unknown tag dimensions in FOLDER_DIMENSION_MAP: {_invalid_dims}"

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

# Tie content tagging toggle to librosa availability
ENABLE_CONTENT_TAGGING = (librosa is not None)
# Waveform preview toggle
ENABLE_WAVEFORM_PREVIEW = bool(plt and np)

# --- Audio Feature Constants ---
N_MFCC: int = 13

CORE_FEATURE_KEYS: List[str] = [
    'brightness',       # Spectral Centroid Mean
    'loudness_rms',     # RMS Energy Mean
]

SPECTRAL_FEATURE_KEYS: List[str] = [
    'zcr_mean',             # Zero-Crossing Rate Mean
    'spectral_contrast_mean', # Mean Spectral Contrast
]

MFCC_FEATURE_KEYS: List[str] = [f'mfcc{i+1}_mean' for i in range(N_MFCC)]


# --- Database Column Definitions ---
# Each tuple: (column_name, display_name)
FEATURE_DEFINITIONS: List[Tuple[str,str]] = [
    ("brightness",           "Brightness (Spectral Centroid)"),
    ("loudness_rms",         "Loudness (RMS)"),
    ("zcr_mean",             "Zero-Crossing Rate"),
    ("spectral_contrast_mean","Spectral Contrast"),
    *[(f"mfcc{i+1}_mean", f"MFCC {i+1}") for i in range(13)],
]

ALL_FEATURE_KEYS = [key for key, _ in FEATURE_DEFINITIONS]

FEATURE_DISPLAY_NAMES = dict(FEATURE_DEFINITIONS)

# Sanity check: display names cover all feature keys
assert all(key in FEATURE_DISPLAY_NAMES for key in ALL_FEATURE_KEYS), \
    "Mismatch between ALL_FEATURE_KEYS and FEATURE_DISPLAY_NAMES"
