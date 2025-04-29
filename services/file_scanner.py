# services/file_scanner.py
"""
FileScannerService - a background service for scanning directories for files.

This module implements the scanning logic in a QThread, reporting progress
and handling cancellation. It performs a single pass directory walk, extracts
basic metadata using TinyTag, checks cache/DB for existing records, and
performs incremental DB sync.
"""
import datetime
import logging
import os
from typing import Any, Dict, List, Optional

from PyQt5 import QtCore

# --- Application Imports ---
# Import only necessary items from settings
from config.settings import (
    AUDIO_EXTENSIONS,
    TinyTag,
)
from services.cache_manager import CacheManager
from services.database_manager import DatabaseManager
# Keep helpers import for key detection (if kept) and potentially hash (if added later)
from utils.helpers import compute_hash, detect_key_from_filename

logger = logging.getLogger(__name__)
# Ensure logger level is set appropriately (DEBUG is useful during development)
# logger.setLevel(logging.DEBUG)


class FileScannerService(QtCore.QThread):
    """
    Scans a directory recursively in a single pass, extracts basic file metadata
    via TinyTag, syncs with cache and database, handles orphan records, and
    reports progress based on the collected file list.

    Emits:
      - progress(current: int, total: int)
      - finished(files_info: List[Dict[str, Any]])
    """

    # --- Signals ---
    progress = QtCore.pyqtSignal(int, int)
    finished = QtCore.pyqtSignal(list)

    # --- Initialization ---
    def __init__(
        self,
        root_path: str,
        db_manager: DatabaseManager, # <<< Accept db_manager instance
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        """
        Initializes the scanner.

        Args:
            root_path: The absolute path to the directory to scan.
            db_manager: The DatabaseManager instance to use. # <<< Updated docstring
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        if not os.path.isdir(root_path):
            logger.error(f"Invalid root path provided to FileScannerService: {root_path}")
        self.root_path = root_path
        self._cancelled = False

        # --- Use the passed-in db_manager ---
        self.db = db_manager # <<< Store the passed instance
        if not self.db or not self.db.engine: # Check if valid manager/engine was passed
             logger.error("FileScannerService initialized without a valid DatabaseManager/engine.")
             raise ConnectionError("Database manager is not properly initialized.")
        # --- End Modification ---

        # Initialize cache manager (keep existing logic)
        try:
            self.cache_manager = CacheManager()
        except Exception as e:
            logger.error(f"Failed to initialize CacheManager: {e}", exc_info=True)
            self.cache_manager = None

    # --- Core Logic ---
    def run(self) -> None:
        """Executes the file scanning process in the background thread."""
        logger.info(f"Starting scan thread for: {self.root_path}")

        # Define progress reporting frequency
        PROGRESS_EMIT_INTERVAL: int = 25 

        files_info: List[Dict[str, Any]] = []
        to_save_in_db: List[Dict[str, Any]] = []
        seen_paths: set[str] = set()
        all_discovered_paths: List[str] = [] # Store paths found during walk

        # --- Pre-Scan Preparations ---
        try:
            # Check if root path is valid before proceeding
            if not os.path.isdir(self.root_path):
                 logger.error(f"Root path does not exist or is not a directory: {self.root_path}")
                 self.progress.emit(0, 0)
                 self.finished.emit([])
                 return

            # Get existing DB paths for orphan detection
            logger.debug("Fetching existing file paths from database for this root...")
            existing_db_records = self.db.get_files_in_folder(self.root_path)
            db_paths: set[str] = {rec["path"] for rec in existing_db_records}
            logger.debug(f"Found {len(db_paths)} existing records in DB for this root.")

            # --- Single Pass Directory Walk to Collect Paths ---
            logger.info("Performing directory walk to collect file paths...")
            walk_error_count = 0
            for dirpath, _, filenames in os.walk(self.root_path, topdown=True, onerror=lambda e: logger.warning(f"os.walk error: {e}")):
                if self._cancelled: break
                for f in filenames:
                    if self._cancelled: break
                    try:
                        # Store the full, normalized path
                        full_path = os.path.normpath(os.path.abspath(os.path.join(dirpath, f)))
                        all_discovered_paths.append(full_path)
                    except Exception as path_e:
                        walk_error_count += 1
                        logger.error(f"Error constructing path in {dirpath} for file {f}: {path_e}", exc_info=False)
                if self._cancelled: break # Break outer loop too
            if walk_error_count > 0:
                 logger.warning(f"Encountered {walk_error_count} errors during path collection.")
            logger.info(f"Collected {len(all_discovered_paths)} file paths.")

        except Exception as setup_e:
            logger.error(f"Error during scan setup or path collection: {setup_e}", exc_info=True)
            self.progress.emit(0, 0)
            self.finished.emit([])
            return # Stop execution

        if self._cancelled:
            logger.info("Scan cancelled during path collection.")
            self.finished.emit([]) # Emit empty list on cancellation
            return

        # --- Process the Collected File List ---
        total_files: int = len(all_discovered_paths)
        audio_exts: set[str] = {ext.lower() for ext in AUDIO_EXTENSIONS}

        logger.info(f"Processing {total_files} collected file paths...")
        for current_count, full_path in enumerate(all_discovered_paths, 1):
            if self._cancelled:
                logger.info("Scan cancelled during file processing.")
                break

            seen_paths.add(full_path) # Mark path as seen on this scan

            try: # Process individual file
                stat = os.stat(full_path)
                size = stat.st_size
                mod_time_ts = stat.st_mtime
                mod_time = datetime.datetime.fromtimestamp(mod_time_ts)
                filename = os.path.basename(full_path)
                extension = os.path.splitext(filename)[1].lower()

                needs_processing = True
                file_data_source = "New/Updated" # For logging

                # 1. Check Cache (if available and cache manager initialized)
                if self.cache_manager and not self.cache_manager.needs_update(full_path, mod_time_ts, size):
                    cached = self.cache_manager.get(full_path, mod_time_ts, size)
                    if cached:
                        # Ensure default keys exist when loading from cache
                        cached.setdefault('bpm', None)
                        cached.setdefault('key', 'N/A')
                        cached.setdefault('duration', None)
                        cached.setdefault('used', False)
                        cached.setdefault('tags', {})
                        cached.setdefault('samplerate', None)
                        cached.setdefault('channels', None)
                        # Add feature keys if they might be missing from old cache?
                        # for f_key in ALL_FEATURE_KEYS: cached.setdefault(f_key, None) # If needed
                        files_info.append(cached)
                        needs_processing = False
                        file_data_source = "Cache"

                # 2. Check Database (if not found in cache)
                if needs_processing:
                    # Use the pre-fetched list for efficiency
                    existing_rec = next((rec for rec in existing_db_records if rec['path'] == full_path), None)
                    if existing_rec and existing_rec.get("mod_time") == mod_time:
                        # Ensure default keys exist when loading from DB
                        existing_rec.setdefault('bpm', None)
                        existing_rec.setdefault('key', 'N/A')
                        # ... other defaults ...
                        files_info.append(existing_rec)
                        needs_processing = False
                        file_data_source = "DB (Unchanged)"
                        # Optionally update cache if DB was used
                        if self.cache_manager:
                            self.cache_manager.update(full_path, mod_time_ts, size, existing_rec)

                # 3. Process New/Updated File
                if needs_processing:
                    file_info: Dict[str, Any] = {
                        "path": full_path, "size": size, "mod_time": mod_time,
                        "duration": None, "key": "N/A", "used": False,
                        "tags": {"filetype": [extension]} if extension else {},
                        "samplerate": None, "channels": None, "bpm": None
                        # Initialize feature keys? Not strictly needed if DB allows NULLs
                    }

                    # TinyTag metadata
                    if extension in audio_exts and TinyTag is not None:
                        try:
                            tag = TinyTag.get(full_path)
                            file_info["duration"] = tag.duration
                            file_info["samplerate"] = tag.samplerate
                            file_info["channels"] = tag.channels
                        except Exception as tag_e:
                            # Log warning, don't stop scan for one file's tag error
                            logger.warning(f"TinyTag read error {full_path}: {tag_e}")

                    # Optional: Key detection from filename
                    try:
                        detected_key = detect_key_from_filename(full_path)
                        if detected_key: file_info["key"] = detected_key
                    except Exception as key_e:
                        logger.warning(f"Key detection error {full_path}: {key_e}")

                    # --- BPM DETECTION IS NO LONGER HERE ---

                    files_info.append(file_info)
                    to_save_in_db.append(file_info)
                    if self.cache_manager:
                        self.cache_manager.update(full_path, mod_time_ts, size, file_info)

                logger.debug(f"Processed: {filename} (Source: {file_data_source})")

            # --- Error Handling for Individual Files ---
            except FileNotFoundError:
                 logger.warning(f"File not found during processing (likely deleted after walk): {full_path}")
                 # Remove from seen_paths if it was added but now missing
                 if full_path in seen_paths: seen_paths.remove(full_path)
            except PermissionError:
                 logger.warning(f"Permission denied for file: {full_path}")
            except OSError as os_e:
                 logger.error(f"OS error processing file {full_path}: {os_e}", exc_info=False)
            except Exception as e:
                logger.error(f"Unexpected error processing file {full_path}: {e}", exc_info=True)

            # --- Emit Progress ---
            if current_count % PROGRESS_EMIT_INTERVAL == 0 or current_count >= total_files:
                 if total_files > 0:
                      logger.debug(f"Emitting scan progress: {current_count}/{total_files}")
                      self.progress.emit(current_count, total_files)
                 # If total_files is 0, this loop won't run, handled earlier.
        # --- End File Processing Loop ---

        if self._cancelled:
            logger.info("Scan cancelled before final operations.")
            # Cache might have partial updates, flushing might be okay or skip? Skip for now.
            self.finished.emit(files_info) # Emit whatever was collected
            return

        # --- Final Operations ---
        logger.info("File processing finished. Finalizing cache, saving records, deleting orphans.")
        try:
            if self.cache_manager:
                self.cache_manager.flush()
        except Exception as cache_e:
            logger.error(f"Error flushing cache: {cache_e}", exc_info=True)

        if to_save_in_db:
            logger.info(f"Saving {len(to_save_in_db)} new/updated records to DB...")
            try:
                self.db.save_file_records(to_save_in_db)
                logger.info("DB save complete.")
            except Exception as db_save_e:
                logger.error(f"Error saving records to DB: {db_save_e}", exc_info=True)

        # Delete orphan DB records
        orphan_paths = db_paths - seen_paths
        if orphan_paths:
            logger.info(f"Deleting {len(orphan_paths)} orphan records from DB...")
            deleted_count = 0
            for orphan in orphan_paths:
                try:
                    self.db.delete_file_record(orphan)
                    deleted_count += 1
                except Exception as del_e:
                     logger.error(f"Error deleting orphan record {orphan}: {del_e}", exc_info=True)
            logger.info(f"Finished deleting {deleted_count} of {len(orphan_paths)} orphan records.")
        else:
            logger.info("No orphan records found to delete.")

        # --- Final Signals ---
        logger.info("Sending final progress and finished signals.")
        # Use the actual number processed for final progress if total_files was 0 initially
        final_total = total_files if total_files > 0 else current_count
        final_current = current_count # current_count reflects processed items
        if final_total >= 0 :
             self.progress.emit(final_current, final_total) # Show actual processed / total
        else:
             self.progress.emit(0,0)

        self.finished.emit(files_info)
        logger.info("FileScannerService finished run method.")

    # --- Cancellation ---
    def cancel(self) -> None:
        """Requests cancellation of the scanning process."""
        if not self._cancelled: # Prevent multiple log messages
             self._cancelled = True
             logger.info("Scan cancellation requested.")