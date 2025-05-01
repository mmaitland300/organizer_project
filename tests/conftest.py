# tests/conftest.py
import logging
import os
from typing import Generator  # Import Generator for type hint fix

import pytest
from sqlalchemy import (  # Ensure 'text' is imported if using raw SQL cleanup
    create_engine,
    text,
)
from sqlalchemy.engine import Engine

# --- Alembic Imports ---
try:
    from alembic import command
    from alembic.config import Config

    ALEMBIC_AVAILABLE = True
except ImportError:
    ALEMBIC_AVAILABLE = False
    Config = None  # type: ignore[assignment, misc] # Ignore both errors here
    command = None  # type: ignore[assignment]

# Import the DatabaseManager class (ensure path is correct)
from services.database_manager import DatabaseManager

# --- ADD Import for table object ---
from services.schema import files_table  # <<< Import your table object

# --- Configuration ---
TEST_DATABASE_URL = "sqlite:///:memory:"
ALEMBIC_INI_PATH = "alembic.ini"

logger = logging.getLogger("pytest_db_setup")

# --- Fixtures ---


@pytest.fixture(scope="session")
# Update return type hint
def test_engine() -> Generator[Engine, None, None]:
    """Session-scoped engine fixture"""
    if not os.path.exists(ALEMBIC_INI_PATH):
        pytest.fail(f"Alembic config not found at: {ALEMBIC_INI_PATH}")
    logger.info(f"Creating test engine for URL: {TEST_DATABASE_URL}")
    engine = create_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}, echo=False
    )
    yield engine
    logger.info("Disposing test engine.")
    engine.dispose()


@pytest.fixture(scope="session")
def apply_migrations(test_engine: Engine):
    """Session-scoped fixture to apply migrations"""
    if not ALEMBIC_AVAILABLE:
        pytest.skip("Alembic not installed, skipping migration application.")
    logger.info(f"Applying migrations using config: {ALEMBIC_INI_PATH}")
    alembic_cfg = Config(ALEMBIC_INI_PATH)
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    alembic_cfg.attributes["connection"] = test_engine
    try:
        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully to test database.")
    except Exception as e:
        logger.error(f"Alembic upgrade failed during test setup: {e}", exc_info=True)
        pytest.fail(f"Alembic upgrade failed: {e}")
    yield


@pytest.fixture(scope="function")
# Update return type hint
def db_manager(
    test_engine: Engine, apply_migrations
) -> Generator[DatabaseManager, None, None]:
    """
    Provides a DatabaseManager instance for each test function
    and CLEARS the 'files' table after the test runs.
    """
    _ = apply_migrations  # Ensure migrations ran
    manager = DatabaseManager(engine=test_engine)
    yield manager  # Provide the manager instance to the test

    # --- Teardown / Cleanup Code ---
    # This code runs after the test function using this fixture finishes
    logger.debug("db_manager fixture teardown: Clearing 'files' table...")
    try:
        # Use the same session-scoped engine to clear the table
        with test_engine.connect() as connection:
            with connection.begin():  # Use a transaction for the delete
                # Use SQLAlchemy Core delete statement for the specific table
                delete_stmt = files_table.delete()
                connection.execute(delete_stmt)
                # Alternative using raw SQL (less safe if table name changes):
                # connection.execute(text("DELETE FROM files;"))
        logger.debug("'files' table cleared successfully.")
    except Exception as e:
        logger.error(
            f"Error clearing 'files' table in fixture teardown: {e}", exc_info=True
        )
        # Optionally fail tests if cleanup fails:
        # pytest.fail(f"Failed to clean up database: {e}")
