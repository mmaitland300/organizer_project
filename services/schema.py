# FILE: models/schema.py
import os
from sqlalchemy import (MetaData, Table, Column, Integer, Float, Text,
                        Boolean, TIMESTAMP, Index, UniqueConstraint)
from sqlalchemy.sql import func # For server_default=func.now()

# Import constants directly from settings to ensure sync
try:
    # Adjust import path based on your project structure
    from config.settings import ALL_FEATURE_KEYS
except ImportError:
    # Fallback for running migrations if settings isn't directly importable
    # WARNING: Ensure this fallback list *exactly* matches settings.py
    print("WARNING: Could not import ALL_FEATURE_KEYS from settings. Using fallback list.")
    ALL_FEATURE_KEYS = [
        'brightness', 'loudness_rms', 'zcr_mean', 'spectral_contrast_mean',
        # Add all MFCC keys manually here if import fails
        *(f'mfcc{i+1}_mean' for i in range(13)) # Example for 13 MFCCs
    ]


# Naming convention for constraints/indexes
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table)s",
    "pk": "pk_%(table_name)s"
}
metadata = MetaData(naming_convention=convention)

# Define the 'files' table
files_table = Table(
    'files', metadata,
    Column('id', Integer, primary_key=True),
    # Use Text for potentially long paths, add index for lookups
    Column('file_path', Text, nullable=False, index=True),
    Column('size', Integer, index=True), # Index size for duplicate checks
    Column('mod_time', Float), # Store as Unix timestamp float
    Column('duration', Float, nullable=True),
    Column('bpm', Integer, nullable=True),
    Column('file_key', Text, nullable=True), # Renamed from 'key'
    # Use Boolean type, ensure default is handled correctly by DB/driver
    Column('used', Boolean, default=False, server_default='0'),
    Column('samplerate', Integer, nullable=True),
    Column('channels', Integer, nullable=True),
    Column('tags', Text, default='{}'), # Store JSON as Text
    # Default/Update handled by DB is often better for timestamps
    Column('last_scanned', TIMESTAMP, server_default=func.now(), onupdate=func.now()),

    # --- Dynamically add feature columns ---
    *(Column(feature, Float, nullable=True) for feature in ALL_FEATURE_KEYS),

    # --- Constraints ---
    UniqueConstraint('file_path', name='uq_files_file_path'), # Explicit unique constraint

    # --- Optional: Add Indexes defined here ---
    # Index('ix_files_bpm', 'bpm'), # Example if needed later
    # Indexes for specific feature columns are currently added in Alembic migration
    # c09c5f22a86d... You could define them here instead for centralization.
)