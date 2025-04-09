# Required Imports
import os
import logging
import warnings
import re

# Logging configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Global Constants
MAX_HASH_FILE_SIZE = 250 * 1024 * 1024  # 250 MB
HASH_TIMEOUT_SECONDS = 5  # 5 seconds

# Audio file extensions accepted
AUDIO_EXTENSIONS = {".wav", ".aiff", ".flac", ".mp3", ".ogg"}

# Regex for detecting musical keys (e.g. "C#m", "Db")
KEY_REGEX = re.compile(
    r'(?:^|[^a-zA-Z])'                   # Start of string or non-alpha
    r'(?P<root>[A-G](?:[#b]|-sharp|-flat)?)'  # Root letter with optional accidental
    r'(?:-|_| )?'                        # Optional separator
    r'(?P<quality>m(?:in(?:or)?)?|maj(?:or)?|minor|major)?'  # Optional chord quality
    r'(?:[^a-zA-Z]|$)',                   # Non-alpha or end of string
    flags=re.IGNORECASE
)

# Dependency Checks and related flags
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

# Filter warnings if needed
warnings.filterwarnings("ignore", message="This function was moved to 'librosa.feature.rhythm.tempo'")
