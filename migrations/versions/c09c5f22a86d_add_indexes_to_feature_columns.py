"""add_indexes_to_feature_columns

Revision ID: c09c5f22a86d
Revises: a970f5188eb3
Create Date: 2025-04-20 18:18:27.278498

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c09c5f22a86d"
down_revision: Union[str, None] = "a970f5188eb3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# List of columns to create indexes on in this migration
# Based on previous discussion for performance boost on similarity search
columns_to_index = [
    "brightness",
    "loudness_rms",
    "zcr_mean",
    "spectral_contrast_mean",
    "mfcc1_mean",
    "mfcc2_mean",
    "mfcc3_mean",
]

# Generate index names based on column names (standard convention)
index_names = {col: f"ix_files_{col}" for col in columns_to_index}


def upgrade() -> None:
    """Creates indexes on selected audio feature columns for query performance."""
    print(f"Applying upgrade {revision}: Adding indexes to feature columns...")
    # Use batch mode for SQLite compatibility when adding/dropping indexes
    with op.batch_alter_table("files", schema=None) as batch_op:
        for col_name in columns_to_index:
            index_name = index_names[col_name]
            try:
                print(f"Creating index: {index_name} on column {col_name}")
                batch_op.create_index(
                    index_name,  # Index name
                    [col_name],  # Column(s) to index
                    unique=False,  # Indexes are not unique
                )
                print(f"Successfully added create_index operation for: {index_name}")
            except Exception as e:
                print(
                    f"Warning/Error creating index {index_name}: {e}. Attempting to continue."
                )
                # Consider raising the error depending on desired strictness
                # raise e
    print(f"Finished applying upgrade {revision}.")


def downgrade() -> None:
    """Drops the indexes created in the upgrade function."""
    print(f"Applying downgrade {revision}: Removing indexes from feature columns...")
    # Use batch mode for SQLite compatibility
    with op.batch_alter_table("files", schema=None) as batch_op:
        # Drop in reverse order of creation (good practice)
        for col_name in reversed(columns_to_index):
            index_name = index_names[col_name]
            try:
                print(f"Dropping index: {index_name}")
                batch_op.drop_index(index_name)
                print(f"Successfully added drop_index operation for: {index_name}")
            except Exception as e:
                print(
                    f"Warning/Error dropping index {index_name}: {e}. Attempting to continue."
                )
                # raise e
    print(f"Finished applying downgrade {revision}.")
