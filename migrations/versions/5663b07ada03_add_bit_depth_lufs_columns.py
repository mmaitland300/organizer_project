"""Add bit_depth, loudness_lufs, pitch_hz, attack_time columns idempotently

Revision ID: 5663b07ada03
down_revision: c09c5f22a86d
Branch Labels: None
depends_on: None
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "5663b07ada03"
down_revision = "c09c5f22a86d"
branch_labels = None
depends_on = None


def upgrade():
    """
    Adds the four new audio feature columns, only if they don't already exist.
    """
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {col["name"] for col in inspector.get_columns("files")}

    with op.batch_alter_table("files") as batch_op:
        if "bit_depth" not in existing_cols:
            batch_op.add_column(sa.Column("bit_depth", sa.Integer(), nullable=True))
        if "loudness_lufs" not in existing_cols:
            batch_op.add_column(sa.Column("loudness_lufs", sa.Float(), nullable=True))
        if "pitch_hz" not in existing_cols:
            batch_op.add_column(sa.Column("pitch_hz", sa.Float(), nullable=True))
        if "attack_time" not in existing_cols:
            batch_op.add_column(sa.Column("attack_time", sa.Float(), nullable=True))


def downgrade():
    """
    Drops the four audio feature columns if they exist.
    """
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_cols = {col["name"] for col in inspector.get_columns("files")}

    with op.batch_alter_table("files") as batch_op:
        if "attack_time" in existing_cols:
            batch_op.drop_column("attack_time")
        if "pitch_hz" in existing_cols:
            batch_op.drop_column("pitch_hz")
        if "loudness_lufs" in existing_cols:
            batch_op.drop_column("loudness_lufs")
        if "bit_depth" in existing_cols:
            batch_op.drop_column("bit_depth")
