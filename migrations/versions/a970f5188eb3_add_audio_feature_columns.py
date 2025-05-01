"""add_audio_feature_columns

Revision ID: a970f5188eb3
Revises: a39924643879
Create Date: 2025-04-20 17:14:28.703553
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Pull in *exactly* the list your app uses everywhere else:
from config.settings import ALL_FEATURE_KEYS

# revision identifiers, used by Alembic.
revision: str = "a970f5188eb3"
down_revision: Union[str, None] = "a39924643879"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Adds REAL columns for storing aggregated audio features."""
    print(f"Applying upgrade {revision}: Adding all audio feature columns...")
    with op.batch_alter_table("files", schema=None) as batch_op:
        for col_name in ALL_FEATURE_KEYS:
            try:
                print(f"  ➤ Adding column: {col_name}")
                batch_op.add_column(sa.Column(col_name, sa.REAL(), nullable=True))
            except Exception as e:
                # in case it already exists
                print(f"    ! Warning adding {col_name}: {e}")
    print(f"Finished applying upgrade {revision}.")


def downgrade() -> None:
    """Removes the audio feature columns."""
    print(f"Applying downgrade {revision}: Dropping all audio feature columns...")
    with op.batch_alter_table("files", schema=None) as batch_op:
        # drop in reverse so anything depending on index order isn’t upset
        for col_name in reversed(ALL_FEATURE_KEYS):
            try:
                print(f"  ➤ Dropping column: {col_name}")
                batch_op.drop_column(col_name)
            except Exception as e:
                print(f"    ! Warning dropping {col_name}: {e}")
    print(f"Finished applying downgrade {revision}.")
