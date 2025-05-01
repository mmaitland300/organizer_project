"""create_files_table

Revision ID: a39924643879
Revises:
Create Date: 2025-04-20 16:34:31.920057

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a39924643879"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("mod_time", sa.Float(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("bpm", sa.Integer(), nullable=True),
        sa.Column("file_key", sa.Text(), nullable=True),
        sa.Column("used", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("samplerate", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column(
            "last_scanned", sa.TIMESTAMP(), nullable=True, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_path"),
    )


def downgrade() -> None:
    op.drop_table("files")
