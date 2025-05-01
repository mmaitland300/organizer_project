from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "60ec2f724e78"
down_revision: Union[str, None] = "5663b07ada03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema using explicit batch mode for SQLite compatibility."""
    print(f"Applying upgrade {revision}: Syncing schema using batch mode...")
    # Use batch_alter_table to handle SQLite limitations for ALTER COLUMN etc.
    with op.batch_alter_table("files", schema=None) as batch_op:
        batch_op.alter_column(
            "file_path", existing_type=sa.TEXT(), nullable=False
        )  # Change nullability
        batch_op.alter_column(
            "used",
            existing_type=sa.INTEGER(),
            type_=sa.Boolean(),  # Change type
            existing_nullable=True,
            existing_server_default=sa.text("'0'"),  # type: ignore[arg-type]
        )

        # Alter feature column types from REAL to Float (if needed by schema def)
        feature_columns_to_alter = [
            "brightness",
            "loudness_rms",
            "zcr_mean",
            "spectral_contrast_mean",
            "mfcc1_mean",
            "mfcc2_mean",
            "mfcc3_mean",
            "mfcc4_mean",
            "mfcc5_mean",
            "mfcc6_mean",
            "mfcc7_mean",
            "mfcc8_mean",
            "mfcc9_mean",
            "mfcc10_mean",
            "mfcc11_mean",
            "mfcc12_mean",
            "mfcc13_mean",
            # Note: New features (bit_depth, lufs, pitch, attack) were likely added
            # with correct types already in migration 5663..., so don't need altering here.
        ]
        for col_name in feature_columns_to_alter:
            try:
                batch_op.alter_column(
                    col_name,
                    existing_type=sa.REAL(),  # Assuming previous type was REAL
                    type_=sa.Float(),
                    existing_nullable=True,
                )
            except Exception as e:
                # Log warning if column doesn't exist or type mismatch, but continue
                print(f"  ! Warning altering column {col_name}: {e}")

        # Drop old indexes explicitly defined in migration c09c...
        indexes_to_drop = [
            "ix_files_brightness",
            "ix_files_loudness_rms",
            "ix_files_mfcc1_mean",
            "ix_files_mfcc2_mean",
            "ix_files_mfcc3_mean",
            "ix_files_spectral_contrast_mean",
            "ix_files_zcr_mean",
        ]
        for index_name in indexes_to_drop:
            try:
                batch_op.drop_index(index_name)
            except Exception as e:
                # Log warning if index doesn't exist, but continue
                print(f"  ! Warning dropping index {index_name}: {e}")

        # Create indexes defined in schema.py (using op.f for naming convention)
        try:
            batch_op.create_index(
                batch_op.f("ix_files_file_path"), ["file_path"], unique=False
            )
        except Exception as e:
            print(f"  ! Warning creating index ix_files_file_path: {e}")
        try:
            batch_op.create_index(batch_op.f("ix_files_size"), ["size"], unique=False)
        except Exception as e:
            print(f"  ! Warning creating index ix_files_size: {e}")

        # Create unique constraint defined in schema.py
        try:
            # Ensure constraint name matches schema.py if specified there
            batch_op.create_unique_constraint("uq_files_file_path", ["file_path"])
        except Exception as e:
            print(f"  ! Warning creating unique constraint uq_files_file_path: {e}")

    print(f"Finished applying upgrade {revision}.")


def downgrade() -> None:
    """Downgrade schema using explicit batch mode."""
    print(f"Applying downgrade {revision}: Reverting schema sync using batch mode...")
    with op.batch_alter_table("files", schema=None) as batch_op:
        # Drop unique constraint
        try:
            batch_op.drop_constraint("uq_files_file_path", type_="unique")
        except Exception as e:
            print(f"  ! Warning dropping unique constraint uq_files_file_path: {e}")

        # Drop indexes created in upgrade
        try:
            batch_op.drop_index(batch_op.f("ix_files_size"))
        except Exception as e:
            print(f"  ! Warning dropping index ix_files_size: {e}")
        try:
            batch_op.drop_index(batch_op.f("ix_files_file_path"))
        except Exception as e:
            print(f"  ! Warning dropping index ix_files_file_path: {e}")

        # Recreate old indexes dropped in upgrade
        indexes_to_recreate = [
            ("ix_files_zcr_mean", ["zcr_mean"]),
            ("ix_files_spectral_contrast_mean", ["spectral_contrast_mean"]),
            ("ix_files_mfcc3_mean", ["mfcc3_mean"]),
            ("ix_files_mfcc2_mean", ["mfcc2_mean"]),
            ("ix_files_mfcc1_mean", ["mfcc1_mean"]),
            ("ix_files_loudness_rms", ["loudness_rms"]),
            ("ix_files_brightness", ["brightness"]),
        ]
        for index_name, columns in indexes_to_recreate:
            try:
                batch_op.create_index(index_name, columns, unique=False)
            except Exception as e:
                print(f"  ! Warning recreating index {index_name}: {e}")

        # Revert feature column types from Float back to REAL
        feature_columns_to_revert = [
            "brightness",
            "loudness_rms",
            "zcr_mean",
            "spectral_contrast_mean",
            "mfcc1_mean",
            "mfcc2_mean",
            "mfcc3_mean",
            "mfcc4_mean",
            "mfcc5_mean",
            "mfcc6_mean",
            "mfcc7_mean",
            "mfcc8_mean",
            "mfcc9_mean",
            "mfcc10_mean",
            "mfcc11_mean",
            "mfcc12_mean",
            "mfcc13_mean",
        ]
        for col_name in feature_columns_to_revert:
            try:
                batch_op.alter_column(
                    col_name,
                    existing_type=sa.Float(),
                    type_=sa.REAL(),  # Revert type
                    existing_nullable=True,
                )
            except Exception as e:
                print(f"  ! Warning reverting column {col_name}: {e}")

        # Revert 'used' column type and nullability
        try:
            batch_op.alter_column(
                "used",
                existing_type=sa.Boolean(),
                type_=sa.INTEGER(),  # Revert type
                existing_nullable=True,
                existing_server_default=sa.text("'0'"),  # type: ignore[arg-type]
            )
        except Exception as e:
            print(f"  ! Warning reverting column used: {e}")

        # Revert 'file_path' nullability
        try:
            batch_op.alter_column(
                "file_path", existing_type=sa.TEXT(), nullable=True
            )  # Revert nullability
        except Exception as e:
            print(f"  ! Warning reverting column file_path: {e}")

    print(f"Finished applying downgrade {revision}.")
