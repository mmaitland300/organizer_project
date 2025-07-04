# services/database_manager.py
"""
Singleton-style class to manage the application's SQLite database, with batch-write support.
Handles new audio feature columns.
"""
import datetime
import json
import logging
import math
import os
import threading
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

# ---> Add SQLAlchemy imports <---
from sqlalchemy import create_engine, delete, insert, select, text

# Import specific dialect construct for ON CONFLICT
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine, Row  # For type hinting

from config.settings import ALL_FEATURE_KEYS  # Import the list of features

# Import your table definition
from services.schema import files_table

logger = logging.getLogger(__name__)


# --- Define Base Columns (excluding ID and new features) ---
BASE_COLUMNS = [
    "file_path",
    "size",
    "mod_time",
    "duration",
    "bpm",
    "file_key",
    "used",
    "samplerate",
    "channels",
    "tags",
    "last_scanned",  # last_scanned updated automatically
]
# Combine Base and Feature columns for SQL statements
# Exclude last_scanned for INSERT/UPDATE list as it's handled by default/trigger
ALL_SAVABLE_COLUMNS = (
    BASE_COLUMNS[:10]
    + ALL_FEATURE_KEYS
    + ["bit_depth", "loudness_lufs", "pitch_hz", "attack_time"]
)
# --- New Constant for Stats Cache ---
STATS_CACHE_FILENAME = os.path.expanduser("~/.musicians_organizer_stats.json")
# --- End New Constant ---


class DatabaseManager:
    """
    Manages SQLite database connection and provides methods to insert/update/select file records,
    including new audio feature columns.
    """

    # --- MODIFY __init__ to accept engine ---
    def __init__(self, engine: Engine):  # Accept engine as argument
        """
        Initializes the DatabaseManager with a SQLAlchemy engine.
        """
        logger.debug("Initializing DatabaseManager attributes.")
        self._lock = threading.RLock()
        self._feature_stats: Optional[Dict[str, Dict[str, float]]] = None
        self.engine: Engine = engine  # Store the passed-in engine

        # Ensure engine is not None after init (already checked by type hint, but safety)
        if self.engine is None:
            # This state should ideally not be reachable if called correctly
            logger.critical("DatabaseManager initialized without a valid engine!")
            raise ValueError("DatabaseManager requires a valid SQLAlchemy engine.")

        logger.info(f"DatabaseManager initialized with engine: {self.engine.url}")

    def _build_save_sql(self) -> str:
        """Builds the INSERT...ON CONFLICT...DO UPDATE SQL statement dynamically."""
        cols_str = ", ".join(ALL_SAVABLE_COLUMNS)
        placeholders_str = ", ".join([f":{col}" for col in ALL_SAVABLE_COLUMNS])
        # Exclude file_path from update setters as it's the conflict target
        update_setters = [
            f"{col}=excluded.{col}" for col in ALL_SAVABLE_COLUMNS if col != "file_path"
        ]
        # Add automatic update for last_scanned on conflict/update
        update_setters.append("last_scanned=CURRENT_TIMESTAMP")
        update_setters_str = ", ".join(update_setters)

        sql = f"""
        INSERT INTO files ({cols_str})
        VALUES ({placeholders_str})
        ON CONFLICT(file_path) DO UPDATE SET
            {update_setters_str}
        """
        # logger.debug(f"Generated Save SQL: {sql}") # Optional: Log generated SQL
        return sql

    def _prepare_save_params(self, file_info: Dict[str, Any]) -> Dict[str, Any]:
        """Prepares the parameter dictionary for saving a single file record."""
        params = {}
        # --- Base Columns ---
        params["file_path"] = file_info.get("path")
        params["size"] = file_info.get("size")
        # Handle mod_time (datetime or timestamp float)
        ft = file_info.get("mod_time")
        if isinstance(ft, datetime.datetime):
            params["mod_time"] = ft.timestamp()
        else:
            params["mod_time"] = ft if isinstance(ft, (int, float)) else None
        params["duration"] = file_info.get("duration")
        params["bpm"] = file_info.get("bpm")
        params["file_key"] = file_info.get("key")
        params["used"] = 1 if file_info.get("used", False) else 0
        params["samplerate"] = file_info.get("samplerate")
        params["channels"] = file_info.get("channels")
        params["bit_depth"] = file_info.get("bit_depth")
        params["loudness_lufs"] = file_info.get("loudness_lufs")
        params["pitch_hz"] = file_info.get("pitch_hz")
        params["attack_time"] = file_info.get("attack_time")
        # Handle tags (ensure JSON string)
        tags_data = file_info.get("tags", {})
        try:
            # Ensure keys are strings if necessary, handle complex objects if needed
            params["tags"] = json.dumps(tags_data) if tags_data else "{}"
        except TypeError:
            logger.warning(
                f"Could not serialize tags for {params['file_path']}, saving empty JSON.",
                exc_info=True,
            )
            params["tags"] = "{}"

        # --- Feature Columns ---
        for key in ALL_FEATURE_KEYS:
            # Ensure None is passed if key is missing or value is None
            params[key] = file_info.get(key)  # .get() defaults to None

        return params

    def save_file_record(self, file_info: Dict[str, Any]) -> None:
        """Insert or update a single file record using SQLAlchemy Core."""
        if not self.engine:  # Check for engine
            logger.error("No SQLAlchemy engine available. Cannot save file record.")
            return

        params = self._prepare_save_params(file_info)
        # Ensure all columns expected by the table are present, even if None
        for col in files_table.columns:
            if (
                col.name not in params
                and col.name != "id"
                and col.name != "last_scanned"
            ):  # Exclude auto cols
                params.setdefault(col.name, None)

        # Build the dialect-specific insert statement for ON CONFLICT
        insert_stmt = sqlite_insert(files_table).values(params)

        # Define the columns to update, excluding the conflict target (file_path)
        update_cols = {
            col.name: getattr(insert_stmt.excluded, col.name)
            for col in files_table.columns
            if col.name not in ["id", "file_path"]  # Exclude PK and conflict target
            # Manually add auto-update columns if needed by the dialect/DB
            # e.g. 'last_scanned': text("CURRENT_TIMESTAMP") # Usually handled by server_default/onupdate
        }

        upsert_stmt = insert_stmt.on_conflict_do_update(
            index_elements=[files_table.c.file_path],  # Column causing conflict
            set_=update_cols,  # Dictionary of columns to update
        )

        logger.debug(
            f"Attempting lock for save_file_record (SQLAlchemy): {file_info.get('path')}"
        )
        try:
            with self._lock:  # Keep lock for thread safety
                logger.debug(
                    f"Lock ACQUIRED for save_file_record (SQLAlchemy): {file_info.get('path')}"
                )
                with self.engine.connect() as connection:  # Get connection from engine
                    with connection.begin():  # Start transaction
                        connection.execute(upsert_stmt)  # Execute statement
                logger.debug(
                    f"Record saved/updated via SQLAlchemy for {file_info.get('path')}"
                )
            logger.debug(f"Lock RELEASED for save_file_record (SQLAlchemy)")
        except Exception as e:
            logger.error(
                f"Failed to save file record (SQLAlchemy) for {file_info.get('path')}. Params: {params}. Error: {e}",
                exc_info=True,
            )

    def save_file_records(self, file_infos: List[Dict[str, Any]]) -> None:
        """Batch insert or update multiple file records using SQLAlchemy Core."""
        if not self.engine:  # Check for engine
            logger.error("No SQLAlchemy engine available. Cannot save file records.")
            return
        if not file_infos:
            logger.debug("No file records provided to save_file_records.")
            return

        # Prepare list of parameter dictionaries
        params_list = []
        for fi in file_infos:
            params = self._prepare_save_params(fi)
            # Ensure all columns expected by the table are present
            for col in files_table.columns:
                if (
                    col.name not in params
                    and col.name != "id"
                    and col.name != "last_scanned"
                ):
                    params.setdefault(col.name, None)
            params_list.append(params)

        # --- NOTE: Batch UPSERT with ON CONFLICT DO UPDATE ---
        # SQLAlchemy Core's default execute()/executemany() might not easily support
        # batching the ON CONFLICT DO UPDATE clause efficiently across all DBAPIs/versions.
        # The safest approach (though potentially slower than a true batch upsert if the
        # DB supports it) is often to execute each upsert individually within a single transaction.

        logger.debug(
            f"Attempting lock for batch save (SQLAlchemy) of {len(file_infos)} records."
        )
        saved_count = 0
        failed_count = 0
        try:
            with self._lock:  # Keep lock
                logger.debug(
                    f"Lock ACQUIRED for batch save (SQLAlchemy) of {len(file_infos)} records."
                )
                with self.engine.connect() as connection:
                    with connection.begin():  # Single transaction for the batch
                        for params in params_list:
                            try:
                                # Build the statement for each record inside the loop
                                insert_stmt = sqlite_insert(files_table).values(params)
                                update_cols = {  # Redefine update_cols based on current params if needed
                                    col.name: getattr(insert_stmt.excluded, col.name)
                                    for col in files_table.columns
                                    if col.name not in ["id", "file_path"]
                                }
                                upsert_stmt = insert_stmt.on_conflict_do_update(
                                    index_elements=[files_table.c.file_path],
                                    set_=update_cols,
                                )
                                connection.execute(upsert_stmt)
                                saved_count += 1
                            except Exception as inner_e:
                                failed_count += 1
                                logger.error(
                                    f"Failed to save record in batch (SQLAlchemy). Path: {params.get('file_path', 'N/A')}. Error: {inner_e}",
                                    exc_info=False,
                                )  # Log less verbosely for batch errors
                                # Decide: continue batch or rollback? Continuing allows partial success.
                    logger.info(
                        f"SQLAlchemy batch save attempt complete. Saved: {saved_count}, Failed: {failed_count}."
                    )
            logger.debug(f"Lock RELEASED for batch save (SQLAlchemy)")

        except Exception as e:
            logger.error(
                f"Major error during batch save (SQLAlchemy): {e}", exc_info=True
            )
            # Optionally log first few failing params for debugging
            if params_list:
                logger.error(f"First few params in failed batch: {params_list[:2]}")

    # Keep _get_column_names - adapt to SQLAlchemy CursorResult if necessary
    def _get_column_names(self, cursor_result) -> List[str]:
        """Gets column names from the SQLAlchemy CursorResult keys."""
        # SQLAlchemy CursorResult has a .keys() method
        try:
            return list(cursor_result.keys())
        except Exception as e:
            logger.warning(f"Could not get column names from CursorResult: {e}")
            return []

    def _row_to_dict(self, row: Row[Any], column_names: List[str]) -> Dict[str, Any]:
        """
        Convert a DB row tuple to a dictionary matching file_info structure,
        including new feature columns. Uses column names for robustness.
        """
        if not column_names or len(row) != len(column_names):
            logger.error(
                f"Row length ({len(row)}) mismatch with column names ({len(column_names)})"
            )
            # Log row and names for debugging
            logger.debug(f"Row data: {row}")
            logger.debug(f"Column names: {column_names}")
            return {}  # Cannot reliably convert

        row_dict = dict(zip(column_names, row))

        file_info = {}
        # --- Map base columns ---
        file_info["db_id"] = row_dict.get("id")
        file_info["path"] = row_dict.get("file_path")
        file_info["size"] = row_dict.get("size")
        # Convert timestamp float back to datetime
        mod_time_ts = row_dict.get("mod_time")
        try:
            file_info["mod_time"] = (
                datetime.datetime.fromtimestamp(mod_time_ts)
                if mod_time_ts is not None
                else None
            )
        except (OSError, TypeError, ValueError) as e:
            logger.warning(
                f"Could not convert timestamp {mod_time_ts} for {file_info['path']}: {e}"
            )
            file_info["mod_time"] = None  # Set to None if conversion fails

        file_info["duration"] = row_dict.get("duration")
        file_info["bpm"] = row_dict.get("bpm")
        file_info["key"] = row_dict.get("file_key", "")  # Default to empty string
        file_info["used"] = bool(row_dict.get("used", 0))  # Convert 0/1 to bool
        file_info["samplerate"] = row_dict.get("samplerate")
        file_info["channels"] = row_dict.get("channels")
        # Parse tags JSON
        tags_text = row_dict.get("tags", "{}")
        try:
            file_info["tags"] = json.loads(tags_text) if tags_text else {}
        except json.JSONDecodeError:
            logger.warning(
                f"Could not decode tags JSON for {file_info.get('path', 'Unknown')}: {tags_text}"
            )
            file_info["tags"] = {}
        # Optional: Include last_scanned timestamp if needed
        # file_info["last_scanned"] = row_dict.get("last_scanned") # Assuming type affinity handles conversion

        # --- Map feature columns ---
        for key in ALL_FEATURE_KEYS:
            file_info[key] = row_dict.get(
                key
            )  # Defaults to None if column somehow missing

        return file_info

    def get_file_record(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Fetch a single file record by path using SQLAlchemy Core."""
        if not self.engine:
            return None

        select_stmt = select(files_table).where(files_table.c.file_path == file_path)

        logger.debug(f"Attempting lock for get_file_record (SQLAlchemy): {file_path}")
        try:
            with self._lock:
                logger.debug(
                    f"Lock ACQUIRED for get_file_record (SQLAlchemy): {file_path}"
                )
                with self.engine.connect() as connection:
                    cursor_result = connection.execute(select_stmt)
                    column_names = self._get_column_names(cursor_result)
                    row = cursor_result.fetchone()  # Fetch the single row
                    if row and column_names:
                        return self._row_to_dict(row, column_names)
                    return None  # Not found
            logger.debug(f"Lock RELEASED for get_file_record (SQLAlchemy)")
        except Exception as e:
            logger.error(
                f"Failed to fetch record (SQLAlchemy) for {file_path}: {e}",
                exc_info=True,
            )
            return None

    def get_all_files(self) -> List[Dict[str, Any]]:
        """Return all file records using SQLAlchemy Core."""
        if not self.engine:
            return []
        results = []
        select_stmt = select(files_table)  # Select all columns from files_table

        logger.debug("Attempting lock for get_all_files (SQLAlchemy)")
        try:
            with self._lock:
                logger.debug("Lock ACQUIRED for get_all_files (SQLAlchemy)")
                with self.engine.connect() as connection:
                    cursor_result = connection.execute(select_stmt)
                    column_names = self._get_column_names(cursor_result)
                    if not column_names:
                        logger.error(
                            "Failed to get column names for get_all_files (SQLAlchemy)."
                        )
                        return []
                    rows = cursor_result.fetchall()
                    results = [self._row_to_dict(row, column_names) for row in rows]
                    logger.debug(f"Fetched {len(results)} total records (SQLAlchemy).")
            logger.debug("Lock RELEASED for get_all_files (SQLAlchemy)")
        except Exception as e:
            logger.error(
                f"Failed to fetch all file records (SQLAlchemy): {e}", exc_info=True
            )
        return results

    def delete_file_record(self, file_path: str) -> None:
        """Delete a single file record by path using SQLAlchemy Core."""
        if not self.engine:
            logger.error("No SQLAlchemy engine available. Cannot delete file record.")
            return

        delete_stmt = delete(files_table).where(files_table.c.file_path == file_path)

        logger.info(f"Attempting to delete record (SQLAlchemy) for path: {file_path}")
        try:
            with self._lock:
                logger.debug(
                    f"Lock ACQUIRED for delete_file_record (SQLAlchemy): {file_path}"
                )
                with self.engine.connect() as connection:
                    with connection.begin():  # Use transaction
                        result = connection.execute(delete_stmt)
                        logger.info(
                            f"Deleted {result.rowcount} record(s) (SQLAlchemy) for path: {file_path}"
                        )
            logger.debug(f"Lock RELEASED for delete_file_record (SQLAlchemy)")
        except Exception as e:
            logger.error(
                f"Failed to delete file record (SQLAlchemy) for {file_path}: {e}",
                exc_info=True,
            )

    def delete_files_in_folder(self, folder_path: str) -> None:
        """Delete all files whose paths start with 'folder_path' using SQLAlchemy Core."""
        if not self.engine:
            logger.error(
                "No SQLAlchemy engine available. Cannot delete files by folder."
            )
            return

        folder_path_norm = os.path.normpath(folder_path)
        like_pattern = folder_path_norm + os.path.sep + "%"

        delete_stmt = delete(files_table).where(
            files_table.c.file_path.like(like_pattern)
        )

        logger.info(
            f"Attempting to delete records (SQLAlchemy) with path prefix: {like_pattern}"
        )
        try:
            with self._lock:
                logger.debug(
                    f"Lock ACQUIRED for delete_files_in_folder (SQLAlchemy): {folder_path_norm}"
                )
                with self.engine.connect() as connection:
                    with connection.begin():  # Use transaction
                        result = connection.execute(delete_stmt)
                        logger.info(
                            f"Deleted {result.rowcount} old records (SQLAlchemy) matching prefix: {folder_path_norm}"
                        )
            logger.debug(f"Lock RELEASED for delete_files_in_folder (SQLAlchemy)")
        except Exception as e:
            logger.error(
                f"Failed to delete folder records (SQLAlchemy) for {folder_path_norm}: {e}",
                exc_info=True,
            )

    def get_files_in_folder(self, folder_path: str) -> List[Dict[str, Any]]:
        """Return records whose file_path starts with the folder_path using SQLAlchemy Core."""
        if not self.engine:
            return []
        results = []
        folder_path_norm = os.path.normpath(folder_path)
        like_pattern = folder_path_norm + os.path.sep + "%"  # Ensure separator

        # Use SQLAlchemy's .like() method
        select_stmt = select(files_table).where(
            files_table.c.file_path.like(like_pattern)
        )

        logger.debug(f"Fetching records (SQLAlchemy) with prefix: {like_pattern}")
        try:
            with self._lock:
                logger.debug(
                    f"Lock ACQUIRED for get_files_in_folder (SQLAlchemy): {folder_path_norm}"
                )
                with self.engine.connect() as connection:
                    cursor_result = connection.execute(select_stmt)
                    column_names = self._get_column_names(cursor_result)
                    if not column_names:
                        logger.error(
                            f"Failed to get column names for get_files_in_folder({folder_path_norm}) (SQLAlchemy)."
                        )
                        return []
                    rows = cursor_result.fetchall()
                    results = [self._row_to_dict(row, column_names) for row in rows]
                    logger.debug(
                        f"Fetched {len(results)} records (SQLAlchemy) matching prefix: {folder_path_norm}"
                    )
            logger.debug(f"Lock RELEASED for get_files_in_folder (SQLAlchemy)")
        except Exception as e:
            logger.error(
                f"Failed to fetch folder records (SQLAlchemy) for {folder_path_norm}: {e}",
                exc_info=True,
            )
        return results

    # Helper to get record by ID (used in find_similar_files example)
    # --- REFACTORED ---
    def get_file_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single file record by primary key ID using SQLAlchemy Core."""
        if not self.engine:
            logger.error("No SQLAlchemy engine. Cannot get file record by ID.")
            return None

        logger.debug(
            f"Attempting lock for get_file_record_by_id (SQLAlchemy): {record_id}"
        )
        try:
            with self._lock:
                logger.debug(
                    f"Lock ACQUIRED for get_file_record_by_id (SQLAlchemy): {record_id}"
                )
                with self.engine.connect() as connection:
                    # Use text() for raw SQL, :param_name for parameters
                    sql = "SELECT * FROM files WHERE id = :record_id"
                    cursor_result = connection.execute(
                        text(sql), {"record_id": record_id}
                    )
                    column_names = self._get_column_names(cursor_result)
                    row = cursor_result.fetchone()
                    if row and column_names:
                        return self._row_to_dict(row, column_names)
                    return None  # Not found or column names failed
            logger.debug(f"Lock RELEASED for get_file_record_by_id (SQLAlchemy)")
        except Exception as e:
            logger.error(
                f"Failed to fetch record (SQLAlchemy) for ID {record_id}: {e}",
                exc_info=True,
            )
            return None

    # --- Internal Statistics Calculation (Safe with RLock) ---
    # --- REFACTORED ---
    def _calculate_feature_statistics(self) -> Dict[str, Dict[str, float]]:
        """
        Calculates feature statistics (count, mean, std dev) using SQL aggregates via SQLAlchemy Core.
        Excludes non-numeric features or features deemed unsuitable for std dev (e.g., bit_depth).
        """
        if not self.engine:
            logger.error("Cannot calculate stats: No SQLAlchemy engine.")
            return {}

        stats: Dict[str, Dict[str, float]] = {}
        features_for_stats_calc = [
            key for key in ALL_FEATURE_KEYS if key != "bit_depth"  # Example exclusion
        ]

        logger.info(
            f"Calculating feature statistics using SQLAlchemy for keys: {features_for_stats_calc}"
        )
        logger.debug("Attempting lock for _calculate_feature_statistics (RLock)...")
        try:
            with self._lock:
                logger.debug("Lock ACQUIRED for _calculate_feature_statistics (RLock).")
                # Use SQLAlchemy engine connection context
                with self.engine.connect() as connection:
                    # Use SQLAlchemy connection transaction context
                    with connection.begin():  # Start a transaction
                        for feature_key in features_for_stats_calc:
                            # Use text() for raw SQL aggregates
                            # Using :feature_key binds doesn't work directly in COUNT/SUM/AVG
                            # So we need to carefully construct the SQL string.
                            # Ensure feature_key is just the column name for safety.
                            if not feature_key.isidentifier():  # Basic safety check
                                logger.warning(
                                    f"Skipping potentially unsafe feature key for stats: {feature_key}"
                                )
                                continue

                            sql = text(
                                f"""
                                SELECT
                                    COUNT("{feature_key}"),
                                    SUM("{feature_key}"),
                                    SUM("{feature_key}" * "{feature_key}")
                                FROM files
                                WHERE "{feature_key}" IS NOT NULL AND ABS("{feature_key}") < 1e30
                            """
                            )  # Use text() and quote identifier

                            count = 0
                            mean = 0.0
                            std_dev = 0.0
                            try:
                                cursor_result = connection.execute(sql)
                                result = cursor_result.fetchone()
                                if result and result[0] is not None:
                                    count, sum_val, sum_sq_val = result
                                    count = int(count)
                                    if (
                                        count > 0
                                        and sum_val is not None
                                        and sum_sq_val is not None
                                    ):
                                        mean = float(sum_val) / count
                                        variance = (float(sum_sq_val) / count) - (
                                            mean * mean
                                        )
                                        if variance < 0 and variance > -1e-9:
                                            variance = 0.0
                                        if variance >= 0 and count > 1:
                                            std_dev = math.sqrt(
                                                variance * count / (count - 1)
                                            )  # Sample std dev
                                        elif variance >= 0 and count == 1:
                                            std_dev = 0.0
                                        else:
                                            std_dev = 0.0
                            except Exception as e:
                                logger.error(
                                    f"Error calculating stats via SQLAlchemy for feature '{feature_key}': {e}",
                                    exc_info=True,
                                )

                            stats[feature_key] = {
                                "mean": mean,
                                "std": std_dev,
                                "count": count,
                            }
                # Transaction commits automatically here if no exceptions
            logger.debug("Lock RELEASED for _calculate_feature_statistics (RLock).")
            logger.info("Feature statistics calculation complete (SQLAlchemy).")
            return stats
        except Exception as e:
            logger.error(
                f"Outer exception during statistics calculation (SQLAlchemy): {e}",
                exc_info=True,
            )
            return {}

    # --- Cache File Helpers (NO LOCKING INSIDE) ---
    def _load_stats_from_file_unsafe(self) -> Optional[Dict[str, Dict[str, float]]]:
        """Loads statistics from JSON file. Caller must handle concurrency if needed."""
        if not os.path.exists(STATS_CACHE_FILENAME):
            return None
        logger.debug(
            f"Loading feature statistics from cache file: {STATS_CACHE_FILENAME}"
        )
        try:
            with open(STATS_CACHE_FILENAME, "r") as f:
                stats = json.load(f)
            # Validation
            if isinstance(stats, dict) and all(
                isinstance(v, dict) and "mean" in v and "std" in v
                for v in stats.values()
            ):
                logger.debug("Successfully loaded stats from file.")
                return stats
            else:
                logger.warning("Statistics cache file format invalid.")
                return None
        except Exception as e:
            logger.error(
                f"Failed to load statistics cache from {STATS_CACHE_FILENAME}: {e}",
                exc_info=True,
            )
            return None

    def _save_stats_to_file_unsafe(self, stats: Dict[str, Dict[str, float]]) -> None:
        """Saves statistics to JSON file. Caller must handle concurrency if needed."""
        logger.debug(f"Saving feature statistics to cache file: {STATS_CACHE_FILENAME}")
        try:
            temp_filename = STATS_CACHE_FILENAME + ".tmp"
            with open(temp_filename, "w") as f:
                json.dump(stats, f, indent=4)
            os.replace(temp_filename, STATS_CACHE_FILENAME)  # Atomic replace
            logger.debug("Successfully saved stats cache file.")
        except Exception as e:
            logger.error(
                f"Failed to save statistics cache to {STATS_CACHE_FILENAME}: {e}",
                exc_info=True,
            )

    def _save_stats_to_cache(self, stats: Dict[str, Dict[str, float]]) -> None:
        """Saves calculated statistics to the JSON cache file (thread-safe)."""
        logger.debug(f"Attempting lock to save stats cache: {STATS_CACHE_FILENAME}")
        with self._lock:  # Acquire lock for file write
            logger.debug(f"Lock ACQUIRED for save stats cache.")
            try:
                with open(STATS_CACHE_FILENAME, "w") as f:
                    json.dump(stats, f, indent=4)
                logger.debug(f"Successfully saved stats cache.")
            except Exception as e:
                logger.error(f"Failed to save statistics cache: {e}", exc_info=True)
        logger.debug(f"Lock RELEASED for save stats cache.")

    def _load_stats_from_cache(self) -> Optional[Dict[str, Dict[str, float]]]:
        """Loads statistics from the JSON cache file (thread-safe)."""
        if not os.path.exists(STATS_CACHE_FILENAME):
            return None
        logger.debug(f"Attempting lock to load stats cache: {STATS_CACHE_FILENAME}")
        stats = None
        with self._lock:  # Acquire lock for file read
            logger.debug(f"Lock ACQUIRED for load stats cache.")
            try:
                with open(STATS_CACHE_FILENAME, "r") as f:
                    loaded_data = json.load(f)
                # Validate structure
                if isinstance(loaded_data, dict) and all(
                    isinstance(v, dict) and "mean" in v and "std" in v
                    for v in loaded_data.values()
                ):
                    stats = loaded_data
                    logger.debug(f"Successfully loaded stats cache.")
                else:
                    logger.warning("Statistics cache file format invalid.")
            except Exception as e:
                logger.error(f"Failed to load statistics cache: {e}", exc_info=True)
        logger.debug(f"Lock RELEASED for load stats cache.")
        return stats

    # --- REFACTORED Public Statistics Method ---
    def get_feature_statistics(
        self, refresh: bool = False
    ) -> Optional[Dict[str, Dict[str, float]]]:
        """
        Gets feature statistics, loading from cache or recalculating.
        Manages lock only for memory cache access and DB calculation call.
        File I/O happens outside the main lock.
        """
        logger.debug(f"Getting feature statistics (refresh={refresh})...")
        calculated_stats: Optional[Dict[str, Dict[str, float]]] = (
            None  # Hold results outside lock
        )

        # 1. Check memory cache (brief lock)
        if not refresh:
            logger.debug("Attempting lock for memory cache check...")
            with self._lock:
                logger.debug("Lock ACQUIRED for memory cache check.")
                if self._feature_stats is not None:
                    logger.debug("Returning in-memory cached stats.")
                    return self._feature_stats  # Lock released automatically
            logger.debug("Lock RELEASED for memory cache check.")  # Auto-released
            logger.debug("In-memory cache miss.")

        # 2. Check file cache (NO lock held during file read)
        if not refresh:
            cached_stats = self._load_stats_from_file_unsafe()  # Read file outside lock
            if cached_stats is not None:
                logger.info("Loaded stats from file cache. Updating memory cache...")
                # Update memory cache (brief lock)
                logger.debug("Attempting lock for memory cache update (from file)...")
                with self._lock:
                    logger.debug("Lock ACQUIRED for memory cache update (from file).")
                    self._feature_stats = cached_stats
                logger.debug("Lock RELEASED for memory cache update (from file).")
                return self._feature_stats  # Return the newly loaded stats
            else:
                logger.info("File cache miss or invalid.")

        # 3. Recalculate if refreshing or cache miss (call needs lock internally)
        logger.info("Recalculating feature statistics...")
        calculated_stats = (
            self._calculate_feature_statistics()
        )  # This method handles its own RLock via 'with'

        # 4. Update caches if calculation succeeded (brief lock for memory, no lock for file)
        if calculated_stats:
            logger.info(
                "Calculation successful. Updating memory cache and saving to file..."
            )
            # Update memory cache (brief lock)
            logger.debug("Attempting lock for memory cache update (post-calc)...")
            with self._lock:
                logger.debug("Lock ACQUIRED for memory cache update (post-calc).")
                self._feature_stats = calculated_stats
            logger.debug("Lock RELEASED for memory cache update (post-calc).")
            # Save to file cache (NO lock held during file write)
            self._save_stats_to_file_unsafe(calculated_stats)
        else:
            logger.error(
                "Statistics calculation failed. Using potentially stale or no statistics."
            )
            # Do not update memory or file cache if calculation failed

        # 5. Return current state of memory cache (brief lock)
        logger.debug("Attempting lock for final stats return...")
        with self._lock:
            logger.debug("Lock ACQUIRED for final stats return.")
            final_result = self._feature_stats  # Read the potentially updated value
        logger.debug("Lock RELEASED for final stats return.")
        return final_result

    # --- Renamed Unscaled Similarity Method ---
    # --- REFACTORED ---
    def find_similar_files_unscaled(
        self, reference_file_id: int, num_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Finds files similar to the reference file based on stored feature columns
        using raw Euclidean distance, executed via SQLAlchemy Core.
        """
        if not self.engine:
            logger.error(
                "No SQLAlchemy engine. Cannot perform unscaled similarity search."
            )
            return []

        logger.info(
            f"Finding files similar to ID: {reference_file_id} (UNSCALED, SQLAlchemy)"
        )
        logger.debug(
            f"Attempting lock for find_similar_files_unscaled (SQLAlchemy): {reference_file_id}"
        )
        try:
            with self._lock:
                logger.debug(
                    f"Lock ACQUIRED for find_similar_files_unscaled (SQLAlchemy): {reference_file_id}"
                )
                # 1. Get reference features (uses refactored get_file_record_by_id)
                ref_dict = self.get_file_record_by_id(reference_file_id)
                if not ref_dict:
                    return []
                ref_features = {key: ref_dict.get(key) for key in ALL_FEATURE_KEYS}
                if any(v is None for v in ref_features.values()):
                    logger.warning(
                        f"Reference file ID {reference_file_id} missing some feature values. Cannot perform unscaled similarity."
                    )
                    return []

                # 2. Build query string and parameters (Similar logic, but for text())
                distance_parts = []
                params = {}
                for i, key in enumerate(ALL_FEATURE_KEYS):
                    if not key.isidentifier():
                        continue  # Safety check
                    param_name = f"ref_{key}"
                    # Ensure column names are quoted if needed (using double quotes is standard)
                    # Use standard SQL POW and COALESCE functions if available, otherwise adapt syntax
                    distance_parts.append(
                        f'POW(COALESCE("{key}", 0) - :{param_name}, 2)'
                    )
                    params[param_name] = ref_features[key]

                if not distance_parts:
                    logger.error("No valid features found to build distance query.")
                    return []

                distance_sql_inner = " + ".join(distance_parts)
                # Use standard SQL SQRT if available, otherwise adapt
                distance_sql = f"SQRT({distance_sql_inner})"
                params["ref_id"] = reference_file_id
                params["limit"] = num_results
                select_cols = ["id", "file_path", "tags"]
                select_cols_str = ", ".join(f'"{c}"' for c in select_cols)  # Quote cols

                # Ensure all features in the WHERE clause are quoted identifiers
                where_not_null = " AND ".join(
                    f'"{key}" IS NOT NULL'
                    for key in ALL_FEATURE_KEYS
                    if key.isidentifier()
                )

                sim_sql_str = f"""
                    SELECT {select_cols_str}, {distance_sql} AS distance
                    FROM files
                    WHERE id != :ref_id
                      AND ({where_not_null}) -- Ensure candidates have features
                    ORDER BY distance ASC
                    LIMIT :limit
                """

                # 3. Execute using SQLAlchemy connection
                similar_rows: List[Row[Any]] = []  # <<< Ensure Annotation exists
                sim_col_names = []
                with self.engine.connect() as connection:
                    cursor_result = connection.execute(text(sim_sql_str), params)
                    sim_col_names = self._get_column_names(cursor_result)
                    similar_rows = cursor_result.fetchall()  # type: ignore[assignment] # Add ignore if needed

                # 4. Format Results
                similar_files = []
                if not sim_col_names:
                    logger.warning(
                        "Similarity query executed but failed to get column names."
                    )
                    return []
                for row in similar_rows:
                    row_dict = dict(zip(sim_col_names, row))
                    # Safely parse tags
                    tags_dict = {}
                    try:
                        tags_json = row_dict.get("tags", "{}")
                        if tags_json:
                            tags_dict = json.loads(tags_json)
                    except json.JSONDecodeError:
                        pass  # Ignore bad JSON

                    similar_files.append(
                        {
                            "path": row_dict.get("file_path"),
                            "tags": tags_dict,
                            "distance": row_dict.get("distance"),
                            "db_id": row_dict.get("id"),
                        }
                    )
                return similar_files
            logger.debug(f"Lock RELEASED for find_similar_files_unscaled (SQLAlchemy)")
        except Exception as e:
            logger.error(
                f"Failed unscaled similarity search (SQLAlchemy) for ID {reference_file_id}: {e}",
                exc_info=True,
            )
            return []

    # --- New Scaled Similarity Method ---
    # --- REFACTORED ---
    def find_similar_files(
        self, reference_file_id: int, num_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Finds files similar using Z-score scaled features and Euclidean distance (Python calc).
        Fetches data using SQLAlchemy Core.
        """
        if not self.engine:  # Check engine first
            logger.error(
                "No SQLAlchemy engine. Cannot perform scaled similarity search."
            )
            return []

        logger.info(
            f"Finding files similar to ID: {reference_file_id} (SCALED, SQLAlchemy)"
        )

        # 1. Get Feature Statistics (No change needed here)
        stats = self.get_feature_statistics()
        if not stats:
            logger.error(
                "Feature statistics unavailable. Cannot perform scaled similarity."
            )
            return []

        # 2. Get Reference File Features (Uses refactored method)
        ref_dict = self.get_file_record_by_id(reference_file_id)
        if not ref_dict:
            logger.error(f"Reference file ID {reference_file_id} not found.")
            return []

        # 3. Scale Reference Features (No change needed here)
        ref_features_scaled = {}
        valid_ref_features = True
        features_to_compare = ALL_FEATURE_KEYS
        for key in features_to_compare:
            value = ref_dict.get(key)
            if value is None:
                valid_ref_features = False
                break
            stat = stats.get(key)
            if not stat or "mean" not in stat or "std" not in stat:
                continue
            mean, std_dev = stat["mean"], stat["std"]
            ref_features_scaled[key] = (
                (value - mean) / std_dev if std_dev > 1e-9 else 0.0
            )
        if not valid_ref_features:
            logger.error("Ref file missing features.")
            return []
        valid_feature_keys = list(ref_features_scaled.keys())
        if not valid_feature_keys:
            logger.error("No valid features for scaling ref.")
            return []

        # 4. Fetch Candidate Files' Features using SQLAlchemy
        candidate_files_data = []
        logger.debug(
            f"Attempting lock for candidate fetch (SQLAlchemy) for ID {reference_file_id}"
        )
        try:
            with self._lock:
                logger.debug(
                    f"Lock ACQUIRED for candidate fetch (SQLAlchemy) for ID {reference_file_id}"
                )
                with self.engine.connect() as connection:
                    # Build select list and where clause safely
                    select_cols = ["id", "file_path", "tags"] + valid_feature_keys
                    select_cols_quoted = ", ".join(
                        f'"{c}"' for c in select_cols if c.isidentifier()
                    )  # Quote safe identifiers

                    where_clauses = [
                        f'"{key}" IS NOT NULL'
                        for key in valid_feature_keys
                        if key.isidentifier()
                    ]
                    where_str = " AND ".join(where_clauses)

                    sql_str = f"""
                        SELECT {select_cols_quoted}
                        FROM files
                        WHERE id != :ref_id
                          AND ({where_str})
                    """
                    cursor_result = connection.execute(
                        text(sql_str), {"ref_id": reference_file_id}
                    )
                    column_names = self._get_column_names(cursor_result)

                    if not column_names:
                        logger.error(
                            "Failed to get column names for candidate query (SQLAlchemy)."
                        )
                        return []

                    rows = cursor_result.fetchall()
                    for row in rows:
                        candidate_files_data.append(dict(zip(column_names, row)))
            logger.debug(
                f"Lock RELEASED for candidate fetch (SQLAlchemy) for ID {reference_file_id}"
            )
        except Exception as e:
            logger.error(
                f"Failed to fetch candidate files (SQLAlchemy): {e}", exc_info=True
            )
            return []

        if not candidate_files_data:
            logger.info("No suitable candidates found.")
            return []

        # 5. Calculate Scaled Distances in Python (No change needed here)
        results_with_distance = []
        for cand_dict in candidate_files_data:
            distance_sq_sum = 0.0
            valid_candidate = True
            for key in valid_feature_keys:
                value = cand_dict.get(key)
                if value is None:
                    valid_candidate = False
                    break
                stat = stats.get(key)
                if not stat:
                    valid_candidate = False
                    break
                mean, std_dev = stat["mean"], stat["std"]
                scaled_value = (value - mean) / std_dev if std_dev > 1e-9 else 0.0
                distance_sq_sum += (ref_features_scaled[key] - scaled_value) ** 2
            if valid_candidate:
                distance = math.sqrt(distance_sq_sum)
                tags_dict = {}
                try:
                    tags_json = cand_dict.get("tags", "{}")
                    if tags_json:
                        tags_dict = json.loads(tags_json)
                except json.JSONDecodeError:
                    pass
                results_with_distance.append(
                    {
                        "path": cand_dict.get("file_path"),
                        "tags": tags_dict,
                        "distance": distance,
                        "db_id": cand_dict.get("id"),
                    }
                )

        # 6. Sort Results and Return Top N (No change needed here)
        results_with_distance.sort(key=lambda x: x["distance"])  # type: ignore[arg-type, return-value]
        logger.info(
            f"Found {len(results_with_distance)} similar files. Returning top {num_results}."
        )
        return results_with_distance[:num_results]
