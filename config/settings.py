"""
Configuration settings for Musicians Organizer.

This module centralizes constants, dependency toggles, and logging configuration.
"""

import os
import re
import logging
import warnings

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
    r'(?:^|[^a-zA-Z])'                   # Start of string or non-alpha
    r'(?P<root>[A-G](?:[#b]|-sharp|-flat)?)'  # Root letter with optional accidental
    r'(?:-|_| )?'                        # Optional separator
    r'(?P<quality>m(?:in(?:or)?)?|maj(?:or)?|minor|major)?'  # Optional chord quality
    r'(?:[^a-zA-Z]|$)',                   # Non-alpha or end of string
    flags=re.IGNORECASE
)

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

ENABLE_ADVANCED_AUDIO_ANALYSIS = (librosa is not None)
ENABLE_WAVEFORM_PREVIEW = (plt is not None and np is not None)
