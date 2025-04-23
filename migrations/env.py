# ---> Keep imports and other setup at the top of env.py the same <---
# (Ensure logging setup is present if you had it before)
import os, sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

import logging
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy import MetaData, create_engine

from config.settings import DB_FILENAME, ALL_FEATURE_KEYS

logger = logging.getLogger(__name__)
# logger.setLevel(logging.DEBUG) # Optional: keep for debugging

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# point at your SQLite file
engine = create_engine(f"sqlite:///{DB_FILENAME}")
 
# reflect the current DB into MetaData
target_metadata = MetaData()
target_metadata.reflect(bind=engine)

# ---> Keep run_migrations_offline() function if you need it <---
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    # ... (keep existing offline implementation) ...
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode.
    Handles engine creation or uses connection from config attributes.
    """
    connectable = context.config.attributes.get("connection", None)
    is_engine = False

    if connectable is None:
        # Standard behavior: create engine from config file
        logger.info("No connection provided; creating engine from alembic.ini.")
        try:
            connectable = engine_from_config(
                config.get_section(config.config_ini_section, {}),
                prefix="sqlalchemy.",
                poolclass=pool.NullPool,
                url=config.get_main_option("sqlalchemy.url")
            )
            is_engine = True
        except Exception as e:
            logger.error(f"Failed to create engine from config: {e}", exc_info=True)
            raise
    else:
        # Use the connection passed via attributes (for testing)
        # Check if it looks like an engine or a raw connection
        if hasattr(connectable, 'connect') and callable(connectable.connect):
            logger.info("Provided connectable appears to be an engine.")
            is_engine = True
        else:
            logger.info("Provided connectable appears to be a raw DBAPI connection.")
            is_engine = False

    # Get the actual connection object to use
    db_connection = None
    try:
        if is_engine:
            logger.info("Using engine to get connection for migrations.")
            db_connection = connectable.connect()
        else:
            logger.info("Using provided raw DBAPI connection directly for migrations.")
            db_connection = connectable # It's already the connection

        # --- Configure and run within the connection context ---
        # Pass the connection to context.configure
        context.configure(
            connection=db_connection,
            target_metadata=target_metadata,
            # Provide dialect_name ONLY if it's NOT an engine,
            # otherwise let configure get it from the SQLAlchemy connection.
            dialect_name="sqlite" if not is_engine else None,
            # compare_type=True # Keep this if useful for SQLite type comparison
        )

        # Use Alembic's transaction context
        with context.begin_transaction():
            logger.info(f"Running migrations within Alembic transaction (is_engine={is_engine}).")
            context.run_migrations()
        logger.info("Migrations finished.")

    except Exception as e:
        # Log the error clearly
        logger.error(f"Exception during migration execution: {e}", exc_info=True)
        # Re-raise the exception to ensure the test fails clearly
        raise
    finally:
        # Close the connection *only* if we created it from an engine *here*
        if is_engine and db_connection:
            logger.info("Closing connection created from engine.")
            db_connection.close()
        elif not is_engine:
            # If the connection was passed in (raw connection),
            # leave it open - test teardown should handle it.
            logger.info("Leaving provided raw DBAPI connection open.")


# ---> Ensure this block appears only ONCE at the very end <---
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()