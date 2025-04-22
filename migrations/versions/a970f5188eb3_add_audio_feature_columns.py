"""add_audio_feature_columns

Revision ID: a970f5188eb3
Revises: a39924643879
Create Date: 2025-04-20 17:14:28.703553

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a970f5188eb3'
down_revision: Union[str, None] = 'a39924643879'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# --- Define ALL feature columns to be added by this migration ---
# Includes brightness and loudness_rms
core_feature_columns = [
    'brightness',
    'loudness_rms',
]
new_feature_columns = [
    'zcr_mean',
    'spectral_contrast_mean',
]
n_mfcc = 13 # Ensure this matches N_MFCC in your Python code
mfcc_columns = [f'mfcc{i+1}_mean' for i in range(n_mfcc)]

# Combine all columns this migration is responsible for
all_columns_in_this_migration = core_feature_columns + new_feature_columns + mfcc_columns

def upgrade() -> None:
    """Adds REAL columns for storing aggregated audio features."""
    print(f"Applying upgrade {revision}: Adding ALL audio feature columns...")
    # Use batch mode for potentially better performance and atomicity with SQLite
    with op.batch_alter_table('files', schema=None) as batch_op:
        for col_name in all_columns_in_this_migration:
            try:
                print(f"Adding column: {col_name}")
                batch_op.add_column(
                    sa.Column(
                        col_name,
                        sa.REAL(), # Use REAL for SQLite compatibility with floats
                        nullable=True # Allow NULLs initially
                        # Add server_default='0.0' if NULL is problematic for calculations
                    )
                )
                print(f"Successfully added column definition: {col_name}")
            except Exception as e:
                # Handle cases where column might already exist if run partially before
                print(f"Warning/Error adding column {col_name}: {e}. Attempting to continue.")
                # raise e # Optionally re-raise if strictness is needed
    print(f"Finished applying upgrade {revision}.")


def downgrade() -> None:
    """Removes the audio feature columns."""
    print(f"Applying downgrade {revision}: Removing ALL audio feature columns...")
    # Use batch mode for dropping as well
    with op.batch_alter_table('files', schema=None) as batch_op:
        # Drop in reverse order
        for col_name in reversed(all_columns_in_this_migration):
            try:
                print(f"Dropping column: {col_name}")
                batch_op.drop_column(col_name)
                print(f"Successfully added drop column operation: {col_name}")
            except Exception as e:
                print(f"Warning/Error dropping column {col_name}: {e}. Attempting to continue.")
                # raise e
    print(f"Finished applying downgrade {revision}.")