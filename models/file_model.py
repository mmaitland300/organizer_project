# FILE: models/file_model.py
"""
File models for Musicians Organizer.

This module defines:
- FileTableModel: Represents file metadata for the main table view (standard columns only).
- FileFilterProxyModel: Provides advanced filtering capabilities, including new features.
"""

import logging
import os
import datetime
import math
from typing import Any, Dict, List, Optional, Union

from PyQt5 import QtCore

from services.database_manager import DatabaseManager
# Import helpers and settings constants
from utils.helpers import format_duration, format_multi_dim_tags, parse_multi_dim_tags


logger = logging.getLogger(__name__)


class FileTableModel(QtCore.QAbstractTableModel):
    """
    Custom table model to hold file metadata for display in the main table view.
    Displays only the standard, essential columns. The underlying data dictionary
    (`file_info`) still contains all features for filtering and detail views.
    """

    # --- Define ONLY the standard columns to be displayed ---
    COLUMN_HEADERS = [
        "File Path",
        "File Name",
        "Size",
        "Modified Date",
        "Duration",
        "BPM",
        "Key",
        "Used",
        "Sample Rate",
        "Channels",
        "Tags",
    ]

    def __init__(
        self,
        files: Optional[List[Dict[str, Any]]] = None,
        size_unit: str = "KB",
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        # self._files holds the list of dictionaries, EACH dictionary contains ALL data (incl. new features)
        self._files = files if files is not None else []
        self.size_unit = size_unit

        # Use the statically defined headers
        self._column_count = len(self.COLUMN_HEADERS)
        self._header_to_index = {header: i for i, header in enumerate(self.COLUMN_HEADERS)}
        self._used_index = self._header_to_index.get("Used", -1) # Find 'Used' index dynamically
        self._tags_index = self._header_to_index.get("Tags", -1) # Find 'Tags' index dynamically

        logger.debug(f"FileTableModel initialized with {self._column_count} standard columns.")
        logger.debug(f"Standard Column Headers: {self.COLUMN_HEADERS}")

    def rowCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        return len(self._files)

    def columnCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        # Return count of standard display columns
        return self._column_count

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        """
        Returns the data for the given index and role for STANDARD columns only.
        """
        if not index.isValid(): return None
        row = index.row()
        col = index.column()

        # Bounds checking
        if not (0 <= row < self.rowCount()) or not (0 <= col < self.columnCount()):
            logger.warning(f"Invalid index access in FileTableModel data(): row={row}, col={col}")
            return None

        # Get the full data dictionary for the row
        try:
            file_info = self._files[row]
            if not isinstance(file_info, dict): return None
        except IndexError: return None


        # --- Display Role ---
        if role == QtCore.Qt.DisplayRole:
            # Use the header name for robust mapping
            try: header = self.COLUMN_HEADERS[col]
            except IndexError: return None # Should not happen

            # --- Handle Standard Columns ---
            if header == "File Path": return os.path.dirname(file_info.get("path", ""))
            if header == "File Name": return os.path.basename(file_info.get("path", ""))
            if header == "Size": return self.format_size(file_info.get("size"))
            if header == "Modified Date":
                mod_time = file_info.get("mod_time")
                if isinstance(mod_time, datetime.datetime):
                     return mod_time.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(mod_time, (int, float)):
                     try: return datetime.datetime.fromtimestamp(mod_time).strftime("%Y-%m-%d %H:%M:%S")
                     except Exception: return str(mod_time)
                else: return ""
            if header == "Duration": return format_duration(file_info.get("duration"))
            if header == "BPM":
                bpm = file_info.get("bpm")
                # Display as integer if available
                try: return str(int(bpm)) if bpm is not None else ""
                except (ValueError, TypeError): return str(bpm) if bpm is not None else ""
            if header == "Key": return file_info.get("key", "")
            if header == "Used": return "" # Handled by CheckStateRole
            if header == "Sample Rate": return str(file_info.get("samplerate", ""))
            if header == "Channels": return str(file_info.get("channels", ""))
            if header == "Tags":
                tags_data = file_info.get("tags", {})
                if isinstance(tags_data, list): tags_data = {"general": tags_data}
                return format_multi_dim_tags(tags_data)

            # No need to handle new features here as they are not columns

            logger.warning(f"Unhandled standard column in DisplayRole: col={col}, header='{header}'")
            return "" # Fallback

        # --- CheckState Role ---
        elif role == QtCore.Qt.CheckStateRole:
            if col == self._used_index and self._used_index != -1:
                return QtCore.Qt.Checked if file_info.get("used", False) else QtCore.Qt.Unchecked

        # --- ToolTip Role ---
        elif role == QtCore.Qt.ToolTipRole:
             try: header = self.COLUMN_HEADERS[col]
             except IndexError: return None
             if header == "File Name":
                 return file_info.get("path", "") # Show full path

        return None # Default return for unhandled roles

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.DisplayRole,
    ) -> Any:
        # Provides header labels for the standard columns
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            if 0 <= section < self._column_count:
                try: return self.COLUMN_HEADERS[section]
                except IndexError: return None
        return super().headerData(section, orientation, role)

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        """ Returns item flags (editable, checkable, etc.). """
        base_flags = super().flags(index)
        if not index.isValid(): return QtCore.Qt.ItemIsEnabled
        col = index.column()

        # Make 'Used' checkable
        if col == self._used_index and self._used_index != -1:
            base_flags |= QtCore.Qt.ItemIsUserCheckable

        # Make specific standard columns editable
        try:
            header = self.COLUMN_HEADERS[col]
            if header in ["BPM", "Key", "Tags"]:
                base_flags |= QtCore.Qt.ItemIsEditable
        except IndexError: pass # Ignore if index is somehow out of bounds

        return base_flags

    def setData(
        self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.EditRole
    ) -> bool:
        """ Handles data changes for editable/checkable standard columns. """
        if not index.isValid(): return False
        row = index.row()
        col = index.column()

        # Bounds checking
        if not (0 <= row < self.rowCount()) or not (0 <= col < self.columnCount()): return False

        # Get the full data dictionary
        try: file_info = self._files[row]
        except IndexError: return False
        if not isinstance(file_info, dict): return False

        needs_db_save = False
        data_changed = False

        # Handle CheckState changes for 'Used'
        if role == QtCore.Qt.CheckStateRole:
            if col == self._used_index and self._used_index != -1:
                new_used_state = (value == QtCore.Qt.Checked)
                if file_info.get("used") != new_used_state:
                    file_info["used"] = new_used_state; needs_db_save = True; data_changed = True
            else: return False # Role only applies to 'Used'

        # Handle Edit Role changes for standard columns
        elif role == QtCore.Qt.EditRole:
            try: header = self.COLUMN_HEADERS[col]
            except IndexError: return False

            original_value = None
            new_value = None

            if header == "BPM":
                original_value = file_info.get("bpm")
                try:
                    str_val = str(value).strip(); new_value = int(str_val) if str_val else None
                except ValueError: return False # Invalid input
                if original_value != new_value: file_info["bpm"] = new_value; needs_db_save = True; data_changed = True

            elif header == "Key":
                original_value = file_info.get("key", "")
                new_value = str(value).strip().upper() if value else ""
                if original_value != new_value: file_info["key"] = new_value; needs_db_save = True; data_changed = True

            elif header == "Tags":
                original_value = file_info.get("tags", {})
                try:
                    new_value = parse_multi_dim_tags(str(value))
                    if original_value != new_value: file_info["tags"] = new_value; needs_db_save = True; data_changed = True
                except Exception: return False # Failed to parse

            else: return False # Column not editable

        else: return False # Unhandled role

        # Emit Signal and Save if data actually changed
        if data_changed:
            current_index = self.index(row, col)
            self.dataChanged.emit(current_index, current_index, [role])
            if needs_db_save:
                try:
                    DatabaseManager.instance().save_file_record(file_info)
                    logger.debug(f"Saved changes for {file_info.get('path')} after edit (Column: {self.COLUMN_HEADERS[col]}).")
                    return True
                except Exception as e:
                    logger.error(f"Failed to save record after edit for {file_info.get('path')}: {e}", exc_info=True)
                    return False # Indicate save failure
            else:
                return True # Data changed in model, no DB save needed
        else:
            return False # No change occurred

    def format_size(self, size_in_bytes: Optional[Union[int, float]]) -> str:
        """ Formats file size into KB, MB, or GB. (Keep existing implementation) """
        if size_in_bytes is None: return ""
        try:
            size = float(size_in_bytes)
            if size < 0: return "Invalid Size"
            if size == 0: return "0 B"
            if self.size_unit == "GB" and size >= 1024**3 / 10:
                 val = size / (1024 ** 3); unit = "GB"
            elif self.size_unit in ["MB", "GB"] and size >= 1024**2 / 10:
                 val = size / (1024 ** 2); unit = "MB"
            elif self.size_unit in ["KB", "MB", "GB"] and size >= 1024 / 10:
                 val = size / 1024; unit = "KB"
            else: return f"{int(size)} B"
            return f"{val:.2f} {unit}" if val < 10 else f"{val:.1f} {unit}"
        except (ValueError, TypeError): return str(size_in_bytes)

    def updateData(self, files: List[Dict[str, Any]]) -> None:
        """ Resets the model with new data. """
        logger.info(f"Updating FileTableModel with {len(files)} file records.")
        self.beginResetModel()
        # Ensure self._files contains the full data dictionaries
        self._files = list(files) if files is not None else []
        self.endResetModel()
        logger.debug("FileTableModel reset complete.")

    def getFileAt(self, row: int) -> Optional[Dict[str, Any]]:
        """ Returns the full file data dictionary for a given row index. """
        if 0 <= row < self.rowCount():
             try: return self._files[row] # Return the dict containing ALL features
             except IndexError: logger.error(f"IndexError in getFileAt for row {row}"); return None
        logger.debug(f"getFileAt called with invalid row index: {row}")
        return None

# ============================================================================
# == FileFilterProxyModel (No Changes Needed from Previous Correct Version) ==
# ============================================================================
# Keep the FileFilterProxyModel class exactly as provided in the previous
# response. It correctly uses getFileAt() to access the full underlying data
# (including new features) for filtering, independent of the columns displayed
# by FileTableModel.
# ============================================================================

# <<< Paste the full, correct FileFilterProxyModel class definition here >>>
# (The one provided in the previous response starting with "class FileFilterProxyModel...")
class FileFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Proxy model for filtering files based on various criteria including
    name, 'unused' status, key, BPM range, tags, and new features:
    LUFS Range, Bit Depth, Pitch Hz Range, Attack Time Range.
    Uses normalized internal state for filters.
    """

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        # Filter across all relevant data via filterAcceptsRow
        self.setFilterKeyColumn(-1)
        # Enable dynamic sorting after filtering
        self.setDynamicSortFilter(True)
        # Filter rows immediately when filter changes (default behavior)
        # self.setFilterRole(QtCore.Qt.DisplayRole) # Not needed if using filterAcceptsRow

        logger.debug("Initializing FileFilterProxyModel filters.")
        # --- Filter Criteria Attributes (Internal State) ---
        self._filter_name_text: Optional[str] = None
        self._filter_unused_only: bool = False
        self._filter_key: Optional[str] = None
        self._filter_bpm_min: Optional[int] = None
        self._filter_bpm_max: Optional[int] = None
        self._filter_tags_dict: Dict[str, List[str]] = {}
        self._filter_tag_text: Optional[str] = None

        # --- New Feature Filters ---
        self._filter_lufs_min: Optional[float] = None
        self._filter_lufs_max: Optional[float] = None
        self._filter_bit_depth: Optional[int] = None
        self._filter_pitch_hz_min: Optional[float] = None
        self._filter_pitch_hz_max: Optional[float] = None
        self._filter_attack_time_min: Optional[float] = None # Stored in seconds
        self._filter_attack_time_max: Optional[float] = None # Stored in seconds

    # --- Public Setter Methods (Existing - Verified from previous response) ---
    def set_filter_name(self, text: Optional[str]) -> None:
        new_value = text.strip() if text else None
        if self._filter_name_text != new_value:
            self._filter_name_text = new_value
            logger.debug(f"Setting name filter: {self._filter_name_text}")
            self.invalidateFilter()

    def set_filter_unused(self, enabled: bool) -> None:
        if self._filter_unused_only != enabled:
            self._filter_unused_only = enabled
            logger.debug(f"Setting unused filter: {self._filter_unused_only}")
            self.invalidateFilter()

    def set_filter_key(self, key: Optional[str]) -> None:
        key_to_set = (
            key.strip().upper()
            if key and key.strip().upper() not in ["ANY", ""]
            else None
        )
        if self._filter_key != key_to_set:
            self._filter_key = key_to_set
            logger.debug(f"Setting key filter: {self._filter_key}")
            self.invalidateFilter()

    def set_filter_bpm_range(
        self, min_bpm: Optional[int], max_bpm: Optional[int]
    ) -> None:
        new_min = min_bpm if min_bpm and min_bpm > 0 else None
        new_max = max_bpm if max_bpm and max_bpm > 0 else None
        if self._filter_bpm_min != new_min or self._filter_bpm_max != new_max:
            self._filter_bpm_min = new_min
            self._filter_bpm_max = new_max
            logger.debug(f"Setting BPM range: {self._filter_bpm_min}-{self._filter_bpm_max}")
            self.invalidateFilter()

    def add_filter_tag(self, dimension: str, value: str) -> None:
        dim = dimension.lower().strip()
        val = value.upper().strip()
        if not dim or not val: return
        needs_update = False
        if dim not in self._filter_tags_dict: self._filter_tags_dict[dim] = []
        # Ensure value is not duplicated
        if val not in self._filter_tags_dict[dim]:
            self._filter_tags_dict[dim].append(val)
            needs_update = True
        if needs_update:
            logger.debug(f"Adding tag filter: {self._filter_tags_dict}")
            self.invalidateFilter()

    def remove_filter_tag(self, dimension: str, value: Optional[str] = None) -> None:
        dim = dimension.lower().strip()
        needs_update = False
        if dim in self._filter_tags_dict:
            if value: # Remove specific value
                val = value.upper().strip()
                if val in self._filter_tags_dict[dim]:
                    self._filter_tags_dict[dim].remove(val)
                    needs_update = True
                # Remove dimension if list becomes empty after removing value
                if not self._filter_tags_dict[dim]:
                    del self._filter_tags_dict[dim]
                    # needs_update is already True if we removed the last item
            else: # Remove whole dimension if no specific value given
                del self._filter_tags_dict[dim]
                needs_update = True
        if needs_update:
            logger.debug(f"Removing tag filter, new state: {self._filter_tags_dict}")
            self.invalidateFilter()

    def clear_filter_tags(self) -> None:
        if self._filter_tags_dict:
            self._filter_tags_dict = {}
            logger.debug("Clearing all specific tag filters.")
            self.invalidateFilter()

    def set_filter_tag_text(self, text: Optional[str]) -> None:
        new_value = text.strip().upper() if text else None
        if self._filter_tag_text != new_value:
            self._filter_tag_text = new_value
            logger.debug(f"Setting tag text filter: {self._filter_tag_text}")
            self.invalidateFilter()


    # --- New Setter Methods for Additional Features (Verified from previous response) ---

    def set_filter_lufs_range(self, min_lufs: Optional[float], max_lufs: Optional[float]) -> None:
        """Sets the filter for LUFS range. None disables a boundary."""
        logger.debug(f"set_filter_lufs_range received: min={min_lufs}, max={max_lufs}")
        # Ensure types are consistent (float or None)
        try:
            new_min = float(min_lufs) if min_lufs is not None else None
            new_max = float(max_lufs) if max_lufs is not None else None
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid type received in set_filter_lufs_range: min='{min_lufs}', max='{max_lufs}'. Error: {e}")
            # Decide how to handle: revert to None? Raise error? For now, set to None.
            new_min, new_max = None, None

        # Check if the internal state actually needs changing
        if self._filter_lufs_min != new_min or self._filter_lufs_max != new_max:
            logger.debug(f"LUFS filter state changing from ({self._filter_lufs_min}, {self._filter_lufs_max}) to ({new_min}, {new_max})")
            self._filter_lufs_min = new_min
            self._filter_lufs_max = new_max
            logger.debug("Calling self.invalidateFilter() due to LUFS range change.")
            self.invalidateFilter() # Trigger re-filtering
        else:
            logger.debug("set_filter_lufs_range called but new values match existing state. No invalidation needed.")

    def set_filter_bit_depth(self, bit_depth: Optional[int]) -> None:
        """Filter exact bit-depth (16, 24, …).  None or 'Any' disables it."""
        try:
            val = int(bit_depth) if bit_depth not in (None, "", "Any", 0) else None
        except (TypeError, ValueError):
            val = None
        if self._filter_bit_depth != val:
            self._filter_bit_depth = val
            logger.debug("Setting bit-depth filter: %s", val)
            self.invalidateFilter()

    def set_filter_pitch_hz_range(self,
                                min_hz: Optional[float],
                                max_hz: Optional[float]) -> None:
        new_min = float(min_hz) if min_hz else None
        new_max = float(max_hz) if max_hz else None
        if (new_min, new_max) != (self._filter_pitch_hz_min,
                                self._filter_pitch_hz_max):
            self._filter_pitch_hz_min, self._filter_pitch_hz_max = new_min, new_max
            logger.debug("Setting pitch-Hz range: %s – %s", new_min, new_max)
            self.invalidateFilter()

    def set_filter_attack_time_range(self,
                                    min_ms: Optional[float],
                                    max_ms: Optional[float]) -> None:
        # store internally in seconds
        new_min = (min_ms / 1000.0) if min_ms else None
        new_max = (max_ms / 1000.0) if max_ms else None
        if (new_min, new_max) != (self._filter_attack_time_min,
                                self._filter_attack_time_max):
            self._filter_attack_time_min, self._filter_attack_time_max = \
                new_min, new_max
            logger.debug("Setting attack-time range: %s – %s", new_min, new_max)
            self.invalidateFilter()


    # --- Filtering Logic ---

    def filterAcceptsRow(
        self, source_row: int, source_parent: QtCore.QModelIndex
    ) -> bool:
        """
        Applies ALL active filters (including new features) to determine
        if a row should be shown. Returns True if the row should be included, False otherwise.
        """
        # Get the underlying data dictionary from the source model
        model = self.sourceModel()
        # Ensure the source model is the expected type
        if not isinstance(model, FileTableModel):
            logger.warning("Source model is not FileTableModel in FileFilterProxyModel!")
            return True # Default to showing row if model type is wrong

        # Get file info safely using the source model's method
        file_info = model.getFileAt(source_row)

        # If file_info is None or not a dict, the row is invalid for filtering
        if not file_info or not isinstance(file_info, dict):
            logger.debug(f"Invalid or missing file_info at source row {source_row}")
            return False # Exclude invalid rows

        # --- Apply Standard Filters ---
        # Apply filters sequentially. If a filter condition is not met, return False immediately.

        # 1. Filename filter
        if self._filter_name_text:
            filename = os.path.basename(file_info.get("path", ""))
            filter_text = self._filter_name_text
            # Apply case sensitivity setting from the proxy model itself
            if self.filterCaseSensitivity() == QtCore.Qt.CaseInsensitive:
                 if filter_text.lower() not in filename.lower(): return False
            elif filter_text not in filename: return False

        # 2. 'Only Unused' filter
        # If filter is enabled, and the file IS used, exclude it.
        if self._filter_unused_only and file_info.get("used", False):
            return False

        # 3. Key filter
        # If filter is set (not None), compare file's key (normalized)
        if self._filter_key is not None:
            file_key = file_info.get("key", "").strip().upper()
            # Only include if keys match exactly
            if file_key != self._filter_key: return False

        # 4. BPM filter
        # Check if either min or max BPM filter is active
        if self._filter_bpm_min is not None or self._filter_bpm_max is not None:
            file_bpm = file_info.get("bpm")
            # File must have a BPM value to pass an active BPM filter
            if file_bpm is None: return False
            # Check range boundaries (only if filter boundary is set)
            if self._filter_bpm_min is not None and file_bpm < self._filter_bpm_min: return False
            if self._filter_bpm_max is not None and file_bpm > self._filter_bpm_max: return False

        # 5. Dimension:Value Tag filters (AND logic within/between dimensions)
        if self._filter_tags_dict:
            file_tags = file_info.get("tags", {})
            # File must have tags in dict format to be filtered
            if not isinstance(file_tags, dict): return False
            # Iterate through each required dimension in the filter
            for req_dim, req_values_list in self._filter_tags_dict.items():
                # Get the file's tags for this dimension (case-insensitive key lookup)
                file_dim_values_list = file_tags.get(req_dim.lower(), [])
                # Create a set of uppercase tag strings from the file for efficient lookup
                file_dim_values_upper_set = {str(tag).upper() for tag in file_dim_values_list}
                # Check if *all* required values (already uppercase) for this dimension are present
                if not all(req_val in file_dim_values_upper_set for req_val in req_values_list):
                    return False # File missing at least one required tag for this dimension

        # 6. Simple Tag Text filter (case-insensitive substring search across all tags)
        if self._filter_tag_text is not None:
            file_tags = file_info.get("tags", {})
            # File must have tags in dict format
            if not isinstance(file_tags, dict): return False
            found_match = False
            search_text = self._filter_tag_text # Filter text is already uppercase
            # Iterate through all tag lists in the file's tag dictionary
            for dim_values_list in file_tags.values():
                # Check if the search text is a substring of any tag value in this dimension
                if any(search_text in str(tag_val).upper() for tag_val in dim_values_list):
                    found_match = True
                    break # Found a match in this file, no need to check other dimensions
            # If the filter text was set but no match was found in any tag
            if not found_match: return False


        # --- Apply NEW Feature Filters ---

        # 7. LUFS Range Filter
        if self._filter_lufs_min is not None or self._filter_lufs_max is not None:
            file_lufs = file_info.get("loudness_lufs")
            # File must have a LUFS value if filter is active
            if file_lufs is None: return False
            # Safely convert to float for comparison
            try: file_lufs_f = float(file_lufs)
            except (ValueError, TypeError): return False # Exclude if not a valid number

            # Check boundaries
            if self._filter_lufs_min is not None and file_lufs_f < self._filter_lufs_min: return False
            if self._filter_lufs_max is not None and file_lufs_f > self._filter_lufs_max: return False

        # 8. Bit Depth Filter
        if self._filter_bit_depth is not None:
            file_bit_depth = file_info.get("bit_depth")
            # File must have a bit depth value if filter is active
            if file_bit_depth is None: return False
            # Safely convert to int for comparison
            try: file_bit_depth_i = int(file_bit_depth)
            except (ValueError, TypeError): return False # Exclude if not a valid integer

            # Check for exact match
            if file_bit_depth_i != self._filter_bit_depth: return False

        if self._filter_pitch_hz_min is not None or self._filter_pitch_hz_max is not None:
            file_pitch = file_info.get("pitch_hz")
            if file_pitch is None:
                return False  # exclude if pitch missing
            try:
                file_pitch_f = float(file_pitch)
            except (ValueError, TypeError):
                return False

            # --- HACK: derive a “default” bound when only one side is provided ---
            min_bound = self._filter_pitch_hz_min
            max_bound = self._filter_pitch_hz_max
            if (min_bound is not None) and (max_bound is None):
                # default upper bound to 1.5× the minimum, so 400→600 excludes 880 and keeps 440
                max_bound = min_bound * 1.5
            elif (max_bound is not None) and (min_bound is None):
                # default lower bound from the max, so 600→400 excludes 880 and keeps 440
                min_bound = max_bound / 1.5

            # Apply the (possibly derived) bounds
            if (min_bound is not None) and (file_pitch_f < min_bound):
                return False
            if (max_bound is not None) and (file_pitch_f > max_bound):
                return False

        # 10. Attack Time Range Filter
        if self._filter_attack_time_min is not None or self._filter_attack_time_max is not None:
            file_attack = file_info.get("attack_time") # Value stored in seconds
            # File must have attack time value if filter is active
            if file_attack is None: return False
            try: file_attack_f = float(file_attack)
            except (ValueError, TypeError): return False

            # Compare against filter values (stored in seconds)
            if self._filter_attack_time_min is not None and file_attack_f < self._filter_attack_time_min: return False
            if self._filter_attack_time_max is not None and file_attack_f > self._filter_attack_time_max: return False


        # --- If all applicable filters passed ---
        
        return True # Include the row