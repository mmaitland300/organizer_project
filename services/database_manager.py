import os
import sqlite3
import logging
import threading
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    Singleton-style class to manage the application's SQLite database.
    Responsible for creating tables, and providing insert/update/select methods.
    """

    _instance = None
    DB_FILENAME = os.path.expanduser("~/.musicians_organizer.db")
    @classmethod
    def instance(cls) -> "DatabaseManager":
        """
        Get the global, singleton instance of the DatabaseManager.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if DatabaseManager._instance is not None:
            # Prevent direct instantiation - enforce singleton
            return
        self._lock = threading.Lock()
        self.connection: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_schema()

    def _connect(self) -> None:
        """
        Establish the SQLite connection.
        """
        try:
            # Add check_same_thread=False so we can access from multiple threads
            self.connection = sqlite3.connect(
                self.DB_FILENAME,
                check_same_thread=False
            )
            self.connection.execute("PRAGMA foreign_keys = ON;")
            self.connection.execute("PRAGMA journal_mode = WAL;")
            logger.info(f"Connected to SQLite database at {self.DB_FILENAME}")
        except Exception as e:
            logger.error(f"Failed to connect to the SQLite database: {e}", exc_info=True)
            self.connection = None

    def _create_schema(self) -> None:
        """
        Create necessary tables if they do not already exist.
        For now, we only need a 'files' table. Additional tables can be added later.
        """
        if not self.connection:
            logger.error("No database connection. Cannot create schema.")
            return

        # We no longer alter the table to add brightness, loudness_rms, stereo_width
        # because we want those metrics to live in the JSON 'tags' column, not separate columns.

        create_files_table = """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            size INTEGER,
            mod_time REAL,
            duration REAL,
            bpm INTEGER,
            file_key TEXT,
            used INTEGER DEFAULT 0,
            samplerate INTEGER,
            channels INTEGER,
            tags TEXT,
            last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """

        try:
            with self.connection:
                self.connection.execute(create_files_table)
            logger.debug("Database schema created or verified successfully.")
        except Exception as e:
            logger.error(f"Failed to create/update schema: {e}", exc_info=True)

    def save_file_record(self, file_info: Dict[str, Any]) -> None:
        """
        Insert or update a single file record in the 'files' table.
        file_info is expected to have the same keys we store in the DB columns.
        """
        if not self.connection:
            logger.error("No database connection. Cannot save file record.")
            return

        try:
            used_val = 1 if file_info.get("used", False) else 0
            import json
            tags_text = ""
            if "tags" in file_info:
                tags_text = json.dumps(file_info["tags"])

            with self._lock:
                # We removed brightness/loudness_rms/stereo_width from the SQL
                sql = """
                INSERT INTO files (
                    file_path, size, mod_time, duration, bpm, file_key, used,
                    samplerate, channels, tags
                )
                VALUES (
                    :file_path, :size, :mod_time, :duration, :bpm, :file_key, :used,
                    :samplerate, :channels, :tags
                )
                ON CONFLICT(file_path) DO UPDATE SET
                    size=excluded.size,
                    mod_time=excluded.mod_time,
                    duration=excluded.duration,
                    bpm=excluded.bpm,
                    file_key=excluded.file_key,
                    used=excluded.used,
                    samplerate=excluded.samplerate,
                    channels=excluded.channels,
                    tags=excluded.tags,
                    last_scanned=CURRENT_TIMESTAMP
                """

                params = {
                    "file_path": file_info.get("path"),
                    "size": file_info.get("size"),
                    "mod_time": file_info["mod_time"].timestamp() if file_info.get("mod_time") else None,
                    "duration": file_info.get("duration"),
                    "bpm": file_info.get("bpm"),
                    "file_key": file_info.get("key"),
                    "used": used_val,
                    "samplerate": file_info.get("samplerate"),
                    "channels": file_info.get("channels"),
                    "tags": tags_text
                }

                with self.connection:
                    self.connection.execute(sql, params)

        except Exception as e:
            logger.error(f"Failed to save file record for {file_info.get('path')}: {e}", exc_info=True)

    def get_file_record(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single file record by path. Returns a dict or None if not found.
        """
        if not self.connection:
            logger.error("No database connection. Cannot get file record.")
            return None
        try:
            with self._lock:
                sql = "SELECT * FROM files WHERE file_path = ?"
                cur = self.connection.cursor()
                cur.execute(sql, (file_path,))
                row = cur.fetchone()
                if row:
                    return self._row_to_dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to fetch record for {file_path}: {e}", exc_info=True)
            return None

    def get_all_files(self) -> List[Dict[str, Any]]:
        """
        Return all file records in the 'files' table.
        """
        results = []
        if not self.connection:
            logger.error("No database connection. Cannot fetch all file records.")
            return results
        try:
            with self._lock:
                sql = "SELECT * FROM files"
                cur = self.connection.cursor()
                for row in cur.execute(sql):
                    results.append(self._row_to_dict(row))
        except Exception as e:
            logger.error(f"Failed to fetch all file records: {e}", exc_info=True)
        return results

    def delete_file_record(self, file_path: str) -> None:
        """
        Delete a single file record from the 'files' table by path.
        """
        if not self.connection:
            logger.error("No database connection. Cannot delete file record.")
            return
        try:
            with self._lock:
                sql = "DELETE FROM files WHERE file_path = ?"
                with self.connection:
                    self.connection.execute(sql, (file_path,))
        except Exception as e:
            logger.error(f"Failed to delete file record for {file_path}: {e}", exc_info=True)

    def _row_to_dict(self, row: tuple) -> Dict[str, Any]:
        """
        Convert a DB row tuple to a dictionary matching file_info structure.
        All advanced DSP fields (brightness, loudness, etc.) 
        are assumed to be stored within 'tags' JSON, not in separate columns.
        """
        import datetime
        import json

        (
            row_id,
            file_path,
            size,
            mod_time_ts,      # float (timestamp) or None
            duration,
            bpm,
            file_key,
            used,             # 0 or 1
            samplerate,
            channels,
            tags_text,        # JSON for all multi-dimensional tags
            last_scanned
        ) = row

        mod_time_dt = None
        if mod_time_ts is not None:
            mod_time_dt = datetime.datetime.fromtimestamp(mod_time_ts)

        # Parse tags JSON
        tags_data = {}
        if tags_text:
            try:
                tags_data = json.loads(tags_text)
            except Exception:
                pass

        file_info = {
            "db_id": row_id,
            "path": file_path,
            "size": size,
            "mod_time": mod_time_dt,
            "duration": duration,
            "bpm": bpm,
            "key": file_key if file_key else "",
            "used": bool(used),
            "samplerate": samplerate,
            "channels": channels,
            "tags": tags_data,
            # "last_scanned": last_scanned  # optional if you want to store it
        }
        return file_info

    def delete_files_in_folder(self, folder_path: str) -> None:
        """
        Delete all files whose paths start with 'folder_path'
        from the 'files' table. This cleans out old data for that folder.
        """
        if not self.connection:
            logger.error("No database connection. Cannot delete files by folder.")
            return

        folder_path = os.path.normpath(folder_path)
        try:
            with self._lock:
                sql = "DELETE FROM files WHERE file_path LIKE ? || '%'"
                self.connection.execute(sql, (folder_path,))
                logger.info(f"Deleted old records from folder: {folder_path}")
        except Exception as e:
            logger.error(f"Failed to delete folder records for {folder_path}: {e}", exc_info=True)

    def get_files_in_folder(self, folder_path: str) -> List[Dict[str, Any]]:
        """
        Return only records that belong to the specified folder_path.
        i.e. file_path starts with folder_path.
        """
        results = []
        if not self.connection:
            logger.error("No database connection. Cannot fetch folder file records.")
            return results

        folder_path = os.path.normpath(folder_path)
        try:
            with self._lock:
                sql = "SELECT * FROM files WHERE file_path LIKE ? || '%'"
                cur = self.connection.cursor()
                cur.execute(sql, (folder_path,))
                rows = cur.fetchall()
                for row in rows:
                    results.append(self._row_to_dict(row))
        except Exception as e:
            logger.error(f"Failed to fetch folder records for {folder_path}: {e}", exc_info=True)
        return results
