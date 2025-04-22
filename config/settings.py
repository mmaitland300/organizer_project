"""
Configuration settings for Musicians Organizer.

This module centralizes constants, dependency toggles, and logging configuration.
"""

import logging
import os
import re
import warnings
from typing import Optional, Any, List, Dict
# Basic logging setup (can be configured further via QSettings if desired)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Global Constants
MAX_HASH_FILE_SIZE = 250 * 1024 * 1024  # 250 MB
HASH_TIMEOUT_SECONDS = 5  # in seconds

# Audio file extensions
AUDIO_EXTENSIONS = {".wav", ".aiff", ".flac", ".mp3", ".ogg"}

# Regular expression to detect musical keys
KEY_REGEX = re.compile(
    r"(?:^|[^a-zA-Z])"  # Start of string or non-alpha
    r"(?P<root>[A-G](?:[#b]|-sharp|-flat)?)"  # Root letter with optional accidental
    r"(?:-|_| )?"  # Optional separator
    r"(?P<quality>m(?:in(?:or)?)?|maj(?:or)?|minor|major)?"  # Optional chord quality
    r"(?:[^a-zA-Z]|$)",  # Non-alpha or end of string
    flags=re.IGNORECASE,
)

# --- <<< NEW: Auto-Tagging Rules >>> ---

# Define common terms/patterns in filenames and map them to tag dimensions
# Use \b for word boundaries to avoid partial matches (e.g., 'kick' matches 'kick' but not 'kicker')
# Order might matter if patterns overlap; more specific patterns could come first if needed.
FILENAME_TAG_PATTERNS: Dict[str, re.Pattern] = {
    'instrument': re.compile(r'\b(kick|kd|snare|sd|clap|clp|hat|hh|cymbal|cym|tom|bass|sub|synth|lead|pad|pluck|piano|guitar|vocal|vox|fx|riser|impact)\b', re.IGNORECASE),
    'type': re.compile(r'\b(loop|lp|one[- ]?shot|oneshot|os|drum[- ]?loop|melody|chord|arp)\b', re.IGNORECASE),
    'character': re.compile(r'\b(punchy|heavy|light|dark|ambient|dirty|clean|distorted|short|long|wet|dry|processed|raw)\b', re.IGNORECASE),
    # Add more dimensions and patterns as needed (e.g., genre, bpm patterns if not handled elsewhere)
}

# Define terms to ignore when extracting tags from folder names
FOLDER_TAG_IGNORE_TERMS: set[str] = {
    # Common library root names
    'samples', 'library', 'libraries', 'audio', 'sound', 'sounds',
    # Common organizational terms (might vary based on user libs)
    'packs', 'kits', 'collections', 'sorted', 'processed', 'downloads',
    # Generic terms
    'fx', 'misc', 'various', 'other',
    # Drive letters/root paths (handle dynamically in code too)
    'c', 'd', 'e', 'f', 'g', 'users', 'documents'
}

# Define how many parent folder levels to check for tags
# (e.g., 3 means check parent, grandparent, great-grandparent)
FOLDER_STRUCTURE_DEPTH: int = 4

# Define potential dimensions to assign folder names to (optional, can be dynamic)
# Could map specific keywords found in paths to dimensions
FOLDER_DIMENSION_MAP: Dict[str, str] = {
    'drums': 'category',
    'synth': 'category',
    'vocals': 'category',
    'guitar': 'category',
    'bass': 'category',
    'fx': 'category',
    'loops': 'type',
    'oneshots': 'type',
    'kick': 'instrument',
    'snare': 'instrument',
    'hats': 'instrument',
    'cymbals': 'instrument',
    '808': 'instrument',
    # Add vendor/pack names if easily identifiable? Complex.
}
# --- <<< END: Auto-Tagging Rules >>> ---

# Predeclare plugin imports for mypy
TinyTag: Optional[Any]
librosa: Optional[Any]
plt: Optional[Any]
np: Optional[Any]
FigureCanvas: Optional[Any]

# Feature toggles – automatically disable features if dependencies are missing.
try:
    from tinytag import TinyTag
except ImportError:
    logger.warning("tinytag module not found. Audio metadata extraction will be disabled.")
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
    np = None
    FigureCanvas = None

ENABLE_ADVANCED_AUDIO_ANALYSIS = librosa is not None
ENABLE_WAVEFORM_PREVIEW = plt is not None and np is not None
# --- Audio Feature Constants ---
N_MFCC: int = 13

# Define base feature keys calculated by AnalysisEngine
CORE_FEATURE_KEYS: List[str] = [
    'brightness',           # Spectral Centroid Mean
    'loudness_rms',         # RMS Energy Mean
]
SPECTRAL_FEATURE_KEYS: List[str] = [
    'zcr_mean',             # Zero-Crossing Rate Mean
    'spectral_contrast_mean', # Mean Spectral Contrast
    # Add other spectral features here if calculated (e.g., bandwidth, rolloff)
]

# Generate MFCC keys based on N_MFCC
MFCC_FEATURE_KEYS: List[str] = [f'mfcc{i+1}_mean' for i in range(N_MFCC)]

# Combine all feature keys that are stored in the database and used for similarity
# Ensure this list exactly matches the columns managed by Alembic migration a970f5188eb3
# and calculated in AnalysisEngine
ALL_FEATURE_KEYS: List[str] = CORE_FEATURE_KEYS + SPECTRAL_FEATURE_KEYS + MFCC_FEATURE_KEYS

# Define user-friendly display names for features (used in FeatureViewDialog)
# Add entries for any new features calculated by AnalysisEngine
FEATURE_DISPLAY_NAMES: Dict[str, str] = {
    'brightness': 'Brightness (Spectral Centroid)',
    'loudness_rms': 'Loudness (RMS)',
    'zcr_mean': 'Zero-Crossing Rate',
    'spectral_contrast_mean': 'Spectral Contrast',
    # Add MFCCs
    **{f'mfcc{i+1}_mean': f'MFCC {i+1}' for i in range(N_MFCC)}
    # Add display names for any other calculated features here
}

# Ensure all keys intended for display/similarity have a display name
assert all(key in FEATURE_DISPLAY_NAMES for key in ALL_FEATURE_KEYS), \
    "Mismatch between ALL_FEATURE_KEYS and FEATURE_DISPLAY_NAMES"