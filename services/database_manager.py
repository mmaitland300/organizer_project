# services/database_manager.py
"""
Singleton-style class to manage the application's SQLite database, with batch-write support.
Handles new audio feature columns.
"""
import os
import sqlite3
import logging
import threading
import json
import datetime
import numpy as np
from typing import Dict, Any, List, Optional, Tuple, Union
from config.settings import ALL_FEATURE_KEYS # Import the list of features

logger = logging.getLogger(__name__)


# --- Define Base Columns (excluding ID and new features) ---
BASE_COLUMNS = [
    "file_path", "size", "mod_time", "duration", "bpm", "file_key", "used",
    "samplerate", "channels", "tags", "last_scanned" # last_scanned updated automatically
]
# Combine Base and Feature columns for SQL statements
# Exclude last_scanned for INSERT/UPDATE list as it's handled by default/trigger
ALL_SAVABLE_COLUMNS = BASE_COLUMNS[:10] + ALL_FEATURE_KEYS
# --- New Constant for Stats Cache ---
STATS_CACHE_FILENAME = os.path.expanduser("~/.musicians_organizer_stats.json")
# --- End New Constant ---

class DatabaseManager:
    """
    Manages SQLite database connection and provides methods to insert/update/select file records,
    including new audio feature columns.
    """
    _instance = None
    # Assuming DB_FILENAME is correctly set elsewhere or default is fine
    DB_FILENAME = os.path.expanduser("~/.musicians_organizer.db")

    @classmethod
    def instance(cls) -> "DatabaseManager":
        if cls._instance is None:
            # Add extra logging for singleton creation instance
            logger.debug("Creating new DatabaseManager singleton instance.")
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """
        Initializes the DatabaseManager.
        Relies on Alembic to manage schema creation/updates.
        The _create_schema call is removed.
        """
        # This check prevents re-running __init__ on the existing instance
        # if DatabaseManager.instance() was called before direct instantiation.
        # It relies on tests resetting _instance = None before creating test instances.
        if hasattr(DatabaseManager._instance, 'connection') and DatabaseManager._instance.connection is not None:
             logger.debug("DatabaseManager instance already initialized with connection.")
             return

        logger.debug("Initializing DatabaseManager attributes.")
        self._lock = threading.Lock()
        self._feature_stats: Optional[Dict[str, Dict[str, float]]] = None
        self.connection: Optional[sqlite3.Connection] = None
        self._connect()
        # self._create_schema() # <<< REMOVED - Rely on Alembic

        # Note: Setting _instance here might be problematic if instance() was called first.
        # The classmethod instance() is the primary way to get/create the instance.


    def _connect(self) -> None:
        # Connect method remains the same as before
        try:
            # Check if connection already exists (e.g., from a previous failed init attempt)
            if hasattr(self, 'connection') and self.connection is not None:
                 logger.warning("Connection attempt skipped, self.connection already exists.")
                 return

            logger.debug(f"Attempting to connect to DB: {self.DB_FILENAME}")
            # Ensure parent directory exists (useful for first run)
            db_dir = os.path.dirname(self.DB_FILENAME)
            if db_dir: # Check if path includes a directory
                 os.makedirs(db_dir, exist_ok=True)

            self.connection = sqlite3.connect(
                self.DB_FILENAME,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, # For timestamp handling
                check_same_thread=False # Required for multi-threaded access
            )
            # Enable WAL mode for better concurrency (good practice with threads)
            self.connection.execute("PRAGMA journal_mode = WAL;")
            self.connection.execute("PRAGMA foreign_keys = ON;")
            logger.info(f"Connected to SQLite database at {self.DB_FILENAME}")
        except Exception as e:
            logger.error(f"Failed to connect to the SQLite database: {e}", exc_info=True)
            self.connection = None

    def _create_schema(self) -> None:
        # This method is no longer called by __init__ but kept for reference or potential manual use.
        # Schema creation is now handled by Alembic migrations.
        logger.warning("DatabaseManager._create_schema() called but schema management is handled by Alembic.")
        pass # Do nothing

    def _build_save_sql(self) -> str:
        """Builds the INSERT...ON CONFLICT...DO UPDATE SQL statement dynamically."""
        cols_str = ", ".join(ALL_SAVABLE_COLUMNS)
        placeholders_str = ", ".join([f":{col}" for col in ALL_SAVABLE_COLUMNS])
        # Exclude file_path from update setters as it's the conflict target
        update_setters = [f"{col}=excluded.{col}" for col in ALL_SAVABLE_COLUMNS if col != 'file_path']
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
        # Handle tags (ensure JSON string)
        tags_data = file_info.get("tags", {})
        try:
            # Ensure keys are strings if necessary, handle complex objects if needed
            params["tags"] = json.dumps(tags_data) if tags_data else "{}"
        except TypeError:
            logger.warning(f"Could not serialize tags for {params['file_path']}, saving empty JSON.", exc_info=True)
            params["tags"] = "{}"

        # --- Feature Columns ---
        for key in ALL_FEATURE_KEYS:
            # Ensure None is passed if key is missing or value is None
            params[key] = file_info.get(key) # .get() defaults to None

        return params

    def save_file_record(self, file_info: Dict[str, Any]) -> None:
        """Insert or update a single file record, including new feature columns."""
        if not self.connection:
            logger.error("No database connection. Cannot save file record.")
            return
        sql = self._build_save_sql()
        params = self._prepare_save_params(file_info)

        try:
            with self._lock, self.connection:
                self.connection.execute(sql, params)
        except Exception as e:
            # Log the parameters that caused the error for debugging
            logger.error(f"Failed to save file record for {file_info.get('path')}. Params: {params}. Error: {e}", exc_info=True)


    def save_file_records(self, file_infos: List[Dict[str, Any]]) -> None:
        """Batch insert or update multiple file records, including new feature columns."""
        if not self.connection:
            logger.error("No database connection. Cannot save file records.")
            return
        if not file_infos:
            logger.debug("No file records provided to save_file_records.")
            return

        sql = self._build_save_sql()
        params_list = [self._prepare_save_params(fi) for fi in file_infos]

        try:
            with self._lock, self.connection:
                self.connection.executemany(sql, params_list)
            logger.info(f"Successfully saved batch of {len(file_infos)} records.")
        except Exception as e:
            logger.error(f"Failed batch save file records: {e}", exc_info=True)
            # Optionally log first few failing params for debugging
            if params_list:
                 logger.error(f"First few params in failed batch: {params_list[:2]}")

    def _get_column_names(self, cursor: sqlite3.Cursor) -> List[str]:
        """Gets column names from the cursor description."""
        # Using cursor.description is generally more reliable than PRAGMA table_info
        # especially if the query doesn't select all columns or uses aliases.
        if cursor.description:
             return [desc[0] for desc in cursor.description]
        else:
             # Fallback or handle error if description is not available (e.g., after no rows fetched)
             logger.warning("Cursor description not available to get column names.")
             # As a less reliable fallback, could query PRAGMA table_info here if needed
             return []


    def _row_to_dict(self, row: tuple, column_names: List[str]) -> Dict[str, Any]:
        """
        Convert a DB row tuple to a dictionary matching file_info structure,
        including new feature columns. Uses column names for robustness.
        """
        if not column_names or len(row) != len(column_names):
            logger.error(f"Row length ({len(row)}) mismatch with column names ({len(column_names)})")
            # Log row and names for debugging
            logger.debug(f"Row data: {row}")
            logger.debug(f"Column names: {column_names}")
            return {} # Cannot reliably convert

        row_dict = dict(zip(column_names, row))

        file_info = {}
        # --- Map base columns ---
        file_info["db_id"] = row_dict.get("id")
        file_info["path"] = row_dict.get("file_path")
        file_info["size"] = row_dict.get("size")
        # Convert timestamp float back to datetime
        mod_time_ts = row_dict.get("mod_time")
        try:
             file_info["mod_time"] = datetime.datetime.fromtimestamp(mod_time_ts) if mod_time_ts is not None else None
        except (OSError, TypeError, ValueError) as e:
             logger.warning(f"Could not convert timestamp {mod_time_ts} for {file_info['path']}: {e}")
             file_info["mod_time"] = None # Set to None if conversion fails

        file_info["duration"] = row_dict.get("duration")
        file_info["bpm"] = row_dict.get("bpm")
        file_info["key"] = row_dict.get("file_key", "") # Default to empty string
        file_info["used"] = bool(row_dict.get("used", 0)) # Convert 0/1 to bool
        file_info["samplerate"] = row_dict.get("samplerate")
        file_info["channels"] = row_dict.get("channels")
        # Parse tags JSON
        tags_text = row_dict.get("tags", "{}")
        try:
            file_info["tags"] = json.loads(tags_text) if tags_text else {}
        except json.JSONDecodeError:
            logger.warning(f"Could not decode tags JSON for {file_info.get('path', 'Unknown')}: {tags_text}")
            file_info["tags"] = {}
        # Optional: Include last_scanned timestamp if needed
        # file_info["last_scanned"] = row_dict.get("last_scanned") # Assuming type affinity handles conversion

        # --- Map feature columns ---
        for key in ALL_FEATURE_KEYS:
            file_info[key] = row_dict.get(key) # Defaults to None if column somehow missing

        return file_info

    def get_file_record(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Fetch a single file record by path, including new feature columns."""
        if not self.connection:
            logger.error("No database connection. Cannot get file record.")
            return None
        try:
            with self._lock:
                # Select all columns explicitly for reliable order with _row_to_dict
                # Fetch column names dynamically is safer if schema changes often
                # For now, assume * order matches schema for simplicity if _get_column_names fails
                sql = "SELECT * FROM files WHERE file_path = ?"
                cur = self.connection.cursor()
                cur.execute(sql, (file_path,))
                row = cur.fetchone()
                # Get column names *after* successful execution
                column_names = self._get_column_names(cur)
                cur.close()

                if row and column_names: # Check if row exists AND column names were fetched
                    return self._row_to_dict(row, column_names)
                elif row:
                     logger.error("Fetched row but failed to get column names, cannot convert row to dict.")
                     return None # Or handle differently
                else:
                     return None # No row found
        except Exception as e:
            logger.error(f"Failed to fetch record for {file_path}: {e}", exc_info=True)
            return None

    def get_all_files(self) -> List[Dict[str, Any]]:
        """Return all file records, including new feature columns."""
        results = []
        if not self.connection:
            logger.error("No database connection. Cannot fetch all file records.")
            return results
        try:
            with self._lock:
                sql = "SELECT * FROM files"
                cur = self.connection.cursor()
                cur.execute(sql)
                # Get column names after execution
                column_names = self._get_column_names(cur)
                if not column_names:
                     logger.error("Failed to get column names for get_all_files, returning empty list.")
                     cur.close()
                     return results

                # Fetch all rows
                rows = cur.fetchall()
                cur.close()
                # Convert rows using fetched column names
                results = [self._row_to_dict(row, column_names) for row in rows]

        except Exception as e:
            logger.error(f"Failed to fetch all file records: {e}", exc_info=True)
        return results

    def delete_file_record(self, file_path: str) -> None:
        """Delete a single file record by path."""
        # (Method remains the same as previous version)
        if not self.connection:
            logger.error("No database connection. Cannot delete file record.")
            return
        try:
            with self._lock, self.connection:
                sql = "DELETE FROM files WHERE file_path = ?"
                self.connection.execute(sql, (file_path,))
                logger.debug(f"Deleted record for path: {file_path}")
        except Exception as e:
            logger.error(f"Failed to delete file record for {file_path}: {e}", exc_info=True)

    def delete_files_in_folder(self, folder_path: str) -> None:
        """Delete all files whose paths start with 'folder_path'."""
        # (Method remains the same as previous version, using LIKE)
        if not self.connection:
            logger.error("No database connection. Cannot delete files by folder.")
            return

        folder_path_norm = os.path.normpath(folder_path)
        like_pattern = folder_path_norm + '%'
        logger.info(f"Attempting to delete records with path prefix: {like_pattern}")

        try:
            with self._lock, self.connection:
                sql = "DELETE FROM files WHERE file_path LIKE ?"
                cursor = self.connection.execute(sql, (like_pattern,))
                logger.info(f"Deleted {cursor.rowcount} old records matching prefix: {folder_path_norm}")
        except Exception as e:
            logger.error(f"Failed to delete folder records for {folder_path_norm}: {e}", exc_info=True)


    def get_files_in_folder(self, folder_path: str) -> List[Dict[str, Any]]:
        """Return records whose file_path starts with the specified folder_path."""
        # (Method remains the same as previous version, using LIKE and _row_to_dict)
        results = []
        if not self.connection:
            logger.error("No database connection. Cannot fetch folder file records.")
            return results

        folder_path_norm = os.path.normpath(folder_path)
        like_pattern = folder_path_norm + '%'
        logger.debug(f"Fetching records with path prefix: {like_pattern}")

        try:
            with self._lock:
                sql = "SELECT * FROM files WHERE file_path LIKE ?"
                cur = self.connection.cursor()
                cur.execute(sql, (like_pattern,))
                # Get column names after execution
                column_names = self._get_column_names(cur)
                if not column_names:
                     logger.error(f"Failed to get column names for get_files_in_folder({folder_path_norm}), returning empty list.")
                     cur.close()
                     return results

                rows = cur.fetchall()
                cur.close()
                results = [self._row_to_dict(row, column_names) for row in rows]
                logger.debug(f"Fetched {len(results)} records matching prefix: {folder_path_norm}")
        except Exception as e:
            logger.error(f"Failed to fetch folder records for {folder_path_norm}: {e}", exc_info=True)
        return results
    
    # Helper to get record by ID (used in find_similar_files example)
    def get_file_record_by_id(self, record_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single file record by primary key ID."""
        if not self.connection: return None
        try:
            with self._lock:
                sql = "SELECT * FROM files WHERE id = ?"
                cur = self.connection.cursor()
                cur.execute(sql, (record_id,))
                row = cur.fetchone()
                column_names = self._get_column_names(cur)
                cur.close()
                if row and column_names:
                    return self._row_to_dict(row, column_names)
                return None
        except Exception as e:
            logger.error(f"Failed to fetch record for ID {record_id}: {e}", exc_info=True)
            return None

    # --- New Methods for Statistics Calculation and Caching ---

    def _calculate_feature_statistics(self) -> Dict[str, Dict[str, float]]:
        """
        Calculates mean and standard deviation for each feature in ALL_FEATURE_KEYS
        across all files with non-NULL values for that feature.

        Returns:
            Dict[str, Dict[str, float]]: {'feature_name': {'mean': M, 'std': S}, ...}
                                         Returns empty dict on error or no connection.
                                         'std' will be 0 if only one value exists or all values are identical.
        """
        if not self.connection:
            logger.error("No database connection. Cannot calculate feature statistics.")
            return {}

        stats = {}
        logger.info("Calculating feature statistics...")
        try:
            with self._lock: # Ensure thread safety during DB access
                cursor = self.connection.cursor()
                for feature_key in ALL_FEATURE_KEYS:
                    # Query only non-NULL values for the current feature
                    sql = f"SELECT {feature_key} FROM files WHERE {feature_key} IS NOT NULL"
                    cursor.execute(sql)
                    # Fetch all values as a flat list, converting from tuples
                    values = [row[0] for row in cursor.fetchall()]

                    if values:
                        values_np = np.array(values, dtype=np.float64) # Use float64 for precision
                        mean = float(np.mean(values_np))
                        # Calculate std dev, handle cases with < 2 values (std dev is 0)
                        if len(values_np) > 1:
                            std_dev = float(np.std(values_np))
                        else:
                            std_dev = 0.0
                        stats[feature_key] = {'mean': mean, 'std': std_dev}
                        logger.debug(f"Stats for {feature_key}: mean={mean:.4f}, std={std_dev:.4f} (n={len(values_np)})")
                    else:
                        logger.warning(f"No non-NULL data found for feature '{feature_key}'. Skipping stats calculation.")
                        # Store None or default values if desired, here we just skip
                        stats[feature_key] = {'mean': 0.0, 'std': 0.0} # Default if no data

                cursor.close()
            logger.info("Feature statistics calculation complete.")
            return stats
        except Exception as e:
            logger.error(f"Failed to calculate feature statistics: {e}", exc_info=True)
            return {} # Return empty on error

    def _save_stats_to_cache(self, stats: Dict[str, Dict[str, float]]) -> None:
        """Saves the calculated statistics to the JSON cache file."""
        logger.debug(f"Saving feature statistics to cache: {STATS_CACHE_FILENAME}")
        try:
            with open(STATS_CACHE_FILENAME, 'w') as f:
                json.dump(stats, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save statistics cache to {STATS_CACHE_FILENAME}: {e}", exc_info=True)

    def _load_stats_from_cache(self) -> Optional[Dict[str, Dict[str, float]]]:
        """Loads statistics from the JSON cache file."""
        if not os.path.exists(STATS_CACHE_FILENAME):
            logger.debug("Statistics cache file not found.")
            return None
        logger.debug(f"Loading feature statistics from cache: {STATS_CACHE_FILENAME}")
        try:
            with open(STATS_CACHE_FILENAME, 'r') as f:
                stats = json.load(f)
                # Basic validation: check if it's a dict and contains expected keys structure
                if isinstance(stats, dict) and all(isinstance(v, dict) and 'mean' in v and 'std' in v for v in stats.values()):
                     return stats
                else:
                     logger.warning("Statistics cache file format seems invalid. Ignoring cache.")
                     return None
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to load statistics cache from {STATS_CACHE_FILENAME}: {e}", exc_info=True)
            return None

    def get_feature_statistics(self, refresh: bool = False) -> Optional[Dict[str, Dict[str, float]]]:
        """
        Gets feature statistics (mean, std dev), loading from cache or recalculating.

        Args:
            refresh (bool): If True, forces recalculation and updates the cache.

        Returns:
            Optional[Dict[str, Dict[str, float]]]: Dictionary of statistics or None if unavailable.
        """
        # Use self._lock to ensure thread safety when accessing/updating self._feature_stats cache
        with self._lock:
            if not refresh and self._feature_stats is not None:
                logger.debug("Returning in-memory cached feature statistics.")
                return self._feature_stats

            if not refresh:
                logger.debug("In-memory cache miss, attempting to load from file cache...")
                cached_stats = self._load_stats_from_cache()
                if cached_stats is not None:
                    self._feature_stats = cached_stats
                    logger.info("Successfully loaded feature statistics from file cache.")
                    return self._feature_stats
                else:
                    logger.info("File cache miss or invalid. Recalculating statistics.")
                    # Proceed to calculate if file cache load failed

            # Calculate (or recalculate if refresh=True or cache load failed)
            calculated_stats = self._calculate_feature_statistics()
            if calculated_stats: # Only update cache if calculation was successful
                self._feature_stats = calculated_stats
                self._save_stats_to_cache(calculated_stats) # Update file cache
                logger.info("Calculated and cached new feature statistics.")
            else:
                 # If calculation failed, don't overwrite potentially stale memory cache
                 # self._feature_stats remains as it was (None or previous value)
                 logger.error("Statistics calculation failed. Using potentially stale or no statistics.")

            return self._feature_stats # Return the current state (possibly None)

    # --- Renamed Unscaled Similarity Method ---
    def find_similar_files_unscaled(self, reference_file_id: int, num_results: int = 10) -> List[Dict[str, Any]]:
        """
        Original implementation: Finds files similar to the reference file based on stored feature columns
        using raw Euclidean distance. Kept for reference or specific use cases.
        """
        # (Paste the *exact* previous implementation of find_similar_files here)
        if not self.connection: return []
        logger.info(f"Finding files similar to ID: {reference_file_id} (UNSCALED)") # Added logging indicator
        try:
            with self._lock:
                # 1. Get reference features
                ref_dict = self.get_file_record_by_id(reference_file_id)
                if not ref_dict: return []
                ref_features = {key: ref_dict.get(key) for key in ALL_FEATURE_KEYS}
                 # Check if any essential feature is None in the reference - if so, cannot compare
                if any(ref_dict.get(key) is None for key in ALL_FEATURE_KEYS):
                      logger.warning(f"Reference file ID {reference_file_id} is missing some feature values. Cannot perform unscaled similarity.")
                      return []

                # 2. Build query
                distance_parts = []
                params = {}
                for i, key in enumerate(ALL_FEATURE_KEYS):
                    param_name = f"ref_{key}"
                    # Use COALESCE to handle potential NULLs in *other* files during SQL distance calculation
                    # Though ideally, files with NULLs should perhaps be excluded or handled differently
                    distance_parts.append(f"POW(COALESCE({key}, 0) - :{param_name}, 2)")
                    params[param_name] = ref_features[key] # Assume ref_features has non-NULL values based on check above
                distance_sql = f"SQRT({ ' + '.join(distance_parts) })"
                params['ref_id'] = reference_file_id
                params['limit'] = num_results
                select_cols = ['id', 'file_path', 'tags'] # Keep selection minimal
                select_cols_str = ", ".join(select_cols)
                sim_sql = f"""
                    SELECT {select_cols_str}, {distance_sql} AS distance
                    FROM files
                    WHERE id != :ref_id
                      AND {' AND '.join(f'{key} IS NOT NULL' for key in ALL_FEATURE_KEYS)} -- Ensure candidates have features
                    ORDER BY distance ASC
                    LIMIT :limit
                """

                # 3. Execute
                cur = self.connection.cursor()
                cur.execute(sim_sql, params)
                similar_rows = cur.fetchall()
                sim_col_names = [desc[0] for desc in cur.description] if cur.description else []
                cur.close()

                # 4. Format Results
                similar_files = []
                if not sim_col_names: return []
                for row in similar_rows:
                    row_dict = dict(zip(sim_col_names, row))
                    similar_files.append({
                        "path": row_dict.get("file_path"),
                        "tags": json.loads(row_dict.get("tags", "{}")),
                        "distance": row_dict.get("distance"),
                        "db_id": row_dict.get("id")
                    })
                return similar_files
        except Exception as e:
            logger.error(f"Failed unscaled similarity search for ID {reference_file_id}: {e}", exc_info=True)
            return []


    # --- New Scaled Similarity Method ---
    def find_similar_files(self, reference_file_id: int, num_results: int = 10) -> List[Dict[str, Any]]:
        """
        Finds files similar to the reference file using Z-score scaled features
        and Euclidean distance calculated in Python.

        Args:
            reference_file_id (int): The primary key ID of the file to find similar items for.
            num_results (int): The maximum number of similar files to return.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, each representing a similar file,
                                  including 'path', 'tags', 'db_id', and 'distance'.
                                  Sorted by ascending distance. Returns empty list on error
                                  or if reference file/stats are unavailable.
        """
        if not self.connection:
            logger.error("No DB connection for similarity search.")
            return []

        logger.info(f"Finding files similar to ID: {reference_file_id} (SCALED)")

        # 1. Get Feature Statistics (Mean/Std Dev)
        stats = self.get_feature_statistics() # Load from cache or calculate
        if not stats:
            logger.error("Feature statistics are unavailable. Cannot perform scaled similarity search.")
            return []

        # 2. Get Reference File Features
        ref_dict = self.get_file_record_by_id(reference_file_id)
        if not ref_dict:
            logger.error(f"Reference file ID {reference_file_id} not found.")
            return []

        # Extract and scale reference features, handling None values and zero std dev
        ref_features_scaled = {}
        valid_ref_feature = True
        for key in ALL_FEATURE_KEYS:
            value = ref_dict.get(key)
            if value is None:
                logger.warning(f"Reference file ID {reference_file_id} missing feature '{key}'. Skipping similarity.")
                valid_ref_feature = False
                break # Cannot compare if reference is missing features
            stat = stats.get(key)
            if not stat: # Should not happen if stats loaded correctly, but check anyway
                 logger.warning(f"Missing stats for feature '{key}'. Cannot scale reference.")
                 valid_ref_feature = False
                 break
            mean, std_dev = stat['mean'], stat['std']
            if std_dev > 1e-9: # Use epsilon for float comparison
                ref_features_scaled[key] = (value - mean) / std_dev
            else:
                # If std dev is effectively zero, scaled value is 0 (as all values are the mean)
                ref_features_scaled[key] = 0.0
        if not valid_ref_feature: return []


        # 3. Fetch Candidate Files' Features
        candidate_files = []
        try:
            with self._lock:
                # Select ID, path, tags, and all feature columns for candidate files
                select_cols = ['id', 'file_path', 'tags'] + ALL_FEATURE_KEYS
                select_cols_str = ", ".join(select_cols)
                # Exclude the reference file itself and files missing *any* feature
                # Note: This WHERE clause might be slow without indexes on all feature columns
                # Consider adding more indexes via Alembic if performance is an issue.
                sql = f"""
                    SELECT {select_cols_str}
                    FROM files
                    WHERE id != ?
                      AND {' AND '.join(f'{key} IS NOT NULL' for key in ALL_FEATURE_KEYS)}
                """
                cursor = self.connection.cursor()
                cursor.execute(sql, (reference_file_id,))
                column_names = [desc[0] for desc in cursor.description] if cursor.description else []

                if not column_names:
                     logger.error("Failed to get column names for candidate query.")
                     cursor.close()
                     return []

                # Store candidates as dictionaries for easier processing
                rows = cursor.fetchall()
                cursor.close()
                for row in rows:
                    candidate_files.append(dict(zip(column_names, row)))

        except Exception as e:
            logger.error(f"Failed to fetch candidate files for similarity search: {e}", exc_info=True)
            return []

        if not candidate_files:
            logger.info("No suitable candidate files found for comparison.")
            return []

        # 4. Calculate Scaled Distances in Python
        results_with_distance = []
        for cand_dict in candidate_files:
            cand_features_scaled = {}
            distance_sq_sum = 0.0
            valid_candidate = True

            for key in ALL_FEATURE_KEYS:
                value = cand_dict.get(key)
                # We already filtered for NOT NULL in SQL, but double-check
                if value is None:
                    logger.warning(f"Candidate file ID {cand_dict.get('id')} unexpectedly missing feature '{key}'. Skipping.")
                    valid_candidate = False
                    break
                stat = stats.get(key)
                if not stat: # Should not happen
                     logger.warning(f"Missing stats for feature '{key}'. Cannot scale candidate.")
                     valid_candidate = False
                     break
                mean, std_dev = stat['mean'], stat['std']

                # Scale candidate feature
                scaled_value = 0.0
                if std_dev > 1e-9:
                    scaled_value = (value - mean) / std_dev
                # else: scaled_value remains 0.0 (as set above)

                # Add squared difference to sum
                distance_sq_sum += (ref_features_scaled[key] - scaled_value) ** 2

            if valid_candidate:
                distance = np.sqrt(distance_sq_sum)
                results_with_distance.append(
                    {
                        "path": cand_dict.get("file_path"),
                        "tags": json.loads(cand_dict.get("tags", "{}")), # Parse tags here
                        "distance": distance,
                        "db_id": cand_dict.get("id")
                    }
                )

        # 5. Sort Results and Return Top N
        results_with_distance.sort(key=lambda x: x["distance"])
        return results_with_distance[:num_results]



