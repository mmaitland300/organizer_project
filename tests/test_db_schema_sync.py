# tests/test_db_schema_sync.py

from services.database_manager import DatabaseManager
from config.settings import ALL_SAVABLE_COLUMNS

def test_db_columns_match_constants():
    db = DatabaseManager.instance().connection
    cursor = db.execute("PRAGMA table_info(files)")
    columns = {row[1] for row in cursor.fetchall()}   # row[1] is column name
    expected = set(ALL_SAVABLE_COLUMNS) | {"id"}      # include PK
    assert expected <= columns, f"Missing columns: {expected - columns}"
