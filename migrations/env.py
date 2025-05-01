# migrations/env.py
import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# --- Project Setup ---
# Add project root to sys.path to allow importing project modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    print(f"Added project root to sys.path: {PROJECT_ROOT}")  # Optional: confirm path

# --- Alembic Config ---
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Setup basic logging if fileConfig fails or is not used
logger = logging.getLogger("alembic.env")
# logger.setLevel(logging.INFO) # Adjust level as needed

# --- Target Metadata ---
# Import the MetaData object from your application's schema definition
try:
    # --->>> Ensure this import path 'services.schema' is correct <<<---
    from services.schema import metadata as target_metadata

    logger.info("Successfully imported target_metadata from services.schema")
except ImportError as e:
    logger.error(
        f"Failed to import target_metadata from services.schema: {e}. "
        "Check PYTHONPATH, sys.path modification, and file existence.",
        exc_info=True,
    )
    raise SystemExit("Failed to import target metadata from services.schema")

# --- Migration Functions ---


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        logger.error(
            "Database URL not configured in alembic.ini section [%s]",
            config.config_ini_section,
        )
        raise ValueError("Database URL must be configured under sqlalchemy.url")

    logger.info(f"Running offline migrations with URL: {url}")
    context.configure(
        url=url,
        target_metadata=target_metadata,  # Use imported metadata
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=True,  # <<< Enable batch mode for offline too
    )

    logger.info("Beginning offline migration transaction.")
    with context.begin_transaction():
        context.run_migrations()
    logger.info("Offline migrations finished.")


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # If tests or other callers passed in an existing engine/connection, use it
    from sqlalchemy.engine import Engine

    existing = config.attributes.get("connection", None)
    if existing is not None:
        logger.info(
            "Using existing connection for Alembic migrations (from Config.attributes)."
        )
        # Determine if it's an Engine (needs .connect()) or already a Connection
        if isinstance(existing, Engine):
            conn = existing.connect()
            close_conn = True
        else:
            conn = existing
            close_conn = False
        try:
            context.configure(
                connection=conn,
                target_metadata=target_metadata,
                compare_type=True,
                compare_server_default=True,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            logger.info("Migrations applied successfully on provided connection.")
        finally:
            if close_conn:
                conn.close()
        return

    # Otherwise fall back to engine_from_config
    try:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
    except Exception as e:
        logger.error(f"Failed to create engine from Alembic config: {e}", exc_info=True)
        raise

    with connectable.connect() as connection:
        logger.info(f"Established connection: {connection.engine.url}")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=True,
        )
        logger.info("Beginning migration transaction (batch mode enabled).")
        with context.begin_transaction():
            context.run_migrations()
        logger.info("Migration transaction committed.")
    logger.info("Online migrations finished successfully.")


# --- Main Execution Block ---
if context.is_offline_mode():
    logger.info("Running migrations in offline mode.")
    run_migrations_offline()
else:
    logger.info("Running migrations in online mode.")
    run_migrations_online()
