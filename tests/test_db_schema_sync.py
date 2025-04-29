# tests/test_db_schema_sync.py

import pytest # Import pytest
from sqlalchemy import text, Engine # Import Engine for type hint
from config.settings import ALL_SAVABLE_COLUMNS

# Import the test_engine fixture if you need it directly,
# or just rely on the db_manager fixture which uses it.
# from .conftest import test_engine # Example import if needed directly

# MODIFY: Use the test_engine fixture provided by conftest.py
def test_db_columns_match_constants(test_engine: Engine): # Inject the test_engine fixture
    """
    Verify that the actual columns in the 'files' table match the expected columns
    defined in configuration (plus the primary key 'id').
    """
    # REMOVE: Old singleton access
    # db_manager = DatabaseManager.instance()
    # if not db_manager.engine:
    #     raise RuntimeError("DatabaseManager engine not initialized. Cannot run schema sync test.")


    columns = set()
    try:
        # Use the injected test_engine directly
        with test_engine.connect() as connection:
            pragma_sql = text("PRAGMA table_info(files)")
            cursor_result = connection.execute(pragma_sql)
            columns = {row[1] for row in cursor_result.fetchall()}
    except Exception as e:
        assert False, f"Failed to query PRAGMA table_info(files): {e}"

    # --- Define the expected set of columns ---
    # --- MODIFY THIS LINE ---
    expected = set(ALL_SAVABLE_COLUMNS) | {"id", "last_scanned"} # <<< ADD "last_scanned" HERE

    # Perform the assertion
    assert expected <= columns, f"Missing columns in DB 'files' table: {expected - columns}"

    # Optional: Check for extra columns (Now this check should pass if expected is correct)
    extra_columns = columns - expected
    assert not extra_columns, f"Extra unexpected columns found in DB 'files' table: {extra_columns}"