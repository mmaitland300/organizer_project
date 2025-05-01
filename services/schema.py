# FILE: services/schema.py
import logging  # Add logging
import os

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func  # For server_default=func.now()

logger = logging.getLogger(__name__)

# Import constants directly from settings to ensure sync
try:
    from config.settings import ADDITIONAL_FEATURE_KEYS, ALL_FEATURE_KEYS
except ImportError:
    logger.error(
        "Could not import feature keys from settings. Using fallback list.",
        exc_info=True,
    )
    # Fallback ONLY if settings cannot be imported (ensure this list *exactly* matches settings.py)
    _ORIGINAL_FALLBACK = [
        "brightness",
        "loudness_rms",
        "zcr_mean",
        "spectral_contrast_mean",
        *(f"mfcc{i+1}_mean" for i in range(13)),  # Assuming 13 MFCCs
    ]
    ADDITIONAL_FEATURE_KEYS = ["bit_depth", "loudness_lufs", "pitch_hz", "attack_time"]
    ALL_FEATURE_KEYS = _ORIGINAL_FALLBACK + ADDITIONAL_FEATURE_KEYS


# Naming convention for constraints/indexes (keep as is)
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=convention)

# Define the 'files' table
files_table = Table(
    "files",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("file_path", Text, nullable=False, index=True),
    Column("size", Integer, index=True),
    Column("mod_time", Float),  # Unix timestamp float
    Column("duration", Float, nullable=True),
    Column("bpm", Integer, nullable=True),
    Column("file_key", Text, nullable=True),  # Renamed from 'key'
    Column("used", Boolean, default=False, server_default="0"),
    Column("samplerate", Integer, nullable=True),
    Column("channels", Integer, nullable=True),
    Column("tags", Text, default="{}"),  # Store JSON as Text
    Column("last_scanned", TIMESTAMP, server_default=func.now(), onupdate=func.now()),
    # --- Add ALL feature columns based on settings ---
    # This assumes ALL_FEATURE_KEYS contains both original and new keys
    *(
        Column(feature, Float, nullable=True)
        for feature in ALL_FEATURE_KEYS
        if feature not in ["bit_depth"]
    ),  # Exclude bit_depth as it's Integer
    # --- Explicitly define non-Float or already defined new columns ---
    Column("bit_depth", Integer, nullable=True),  # Define explicitly as Integer
    # --- Constraints ---
    UniqueConstraint(
        "file_path", name="uq_files_file_path"
    ),  # Explicit unique constraint
)
