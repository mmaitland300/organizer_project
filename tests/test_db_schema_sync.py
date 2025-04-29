# tests/test_db_schema_sync.py

from services.database_manager import DatabaseManager
from sqlalchemy import text
from config.settings import ALL_SAVABLE_COLUMNS

def test_db_columns_match_constants():
    """
    Verify that the actual columns in the 'files' table match the expected columns
    defined in configuration (plus the primary key 'id').
    """
    db_manager = DatabaseManager.instance()
    if not db_manager.engine:
        # If using unittest framework, could use self.fail or skipTest
        # For a simple function test, raising an error might be appropriate
        raise RuntimeError("DatabaseManager engine not initialized. Cannot run schema sync test.")

    columns = set()
    try:
        with db_manager.engine.connect() as connection:
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