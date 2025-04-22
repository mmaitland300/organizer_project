"""
File models for Musicians Organizer.

This module defines the FileTableModel which is used by the UI to represent file metadata.
"""

import logging  # Add logging
import os
from typing import Any, Dict, List, Optional, Union

from PyQt5 import QtCore

from services.database_manager import DatabaseManager
from utils.helpers import format_duration, format_multi_dim_tags, parse_multi_dim_tags

logger = logging.getLogger(__name__)  # Add logger


class FileTableModel(QtCore.QAbstractTableModel):
    """
    Custom table model to hold file metadata.

    Columns include:
      - File Path, File Name, Size, Modified Date, Duration, BPM, Key, Used, Sample Rate, Channels, Tags.
    """

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
        self._files = files if files is not None else []
        self.size_unit = size_unit

    def rowCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        return len(self._files)

    def columnCount(self, parent: Optional[QtCore.QModelIndex] = None) -> int:
        return len(self.COLUMN_HEADERS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        file_info = self._files[index.row()]
        col = index.column()
        if role == QtCore.Qt.DisplayRole:
            if col == 0:
                return os.path.dirname(file_info["path"])
            elif col == 1:
                return os.path.basename(file_info["path"])
            elif col == 2:
                return self.format_size(file_info["size"])
            elif col == 3:
                return file_info["mod_time"].strftime("%Y-%m-%d %H:%M:%S")
            elif col == 4:
                return format_duration(file_info.get("duration"))
            elif col == 5:
                return str(file_info.get("bpm", ""))
            elif col == 6:
                return file_info.get("key", "")
            elif col == 7:
                return ""
            elif col == 8:
                return str(file_info.get("samplerate", ""))
            elif col == 9:
                return str(file_info.get("channels", ""))
            elif col == 10:
                tags_data = file_info.get("tags", {})
                if isinstance(tags_data, list):
                    tags_data = {"general": tags_data}
                return format_multi_dim_tags(tags_data)
        if role == QtCore.Qt.CheckStateRole and col == 7:
            return (
                QtCore.Qt.Checked
                if file_info.get("used", False)
                else QtCore.Qt.Unchecked
            )
        return None

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.DisplayRole,
    ) -> Any:
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            if 0 <= section < len(self.COLUMN_HEADERS):
                return self.COLUMN_HEADERS[section]
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlags:
        if not index.isValid():
            return QtCore.Qt.ItemIsEnabled
        base_flags = QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        col = index.column()
        if col == 7:
            return base_flags | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsEditable
        elif col in [4, 5, 6, 10]:
            return base_flags | QtCore.Qt.ItemIsEditable
        else:
            return base_flags

    def setData(
        self, index: QtCore.QModelIndex, value: Any, role: int = QtCore.Qt.EditRole
    ) -> bool:
        if not index.isValid():
            return False
        file_info = self._files[index.row()]
        col = index.column()
        if role == QtCore.Qt.CheckStateRole and col == 7:
            file_info["used"] = value == QtCore.Qt.Checked
            self.dataChanged.emit(index, index, [role])
            # Save to DB
            DatabaseManager.instance().save_file_record(file_info)
            return True
        if role == QtCore.Qt.EditRole:
            if col == 4:  # Duration
                new_duration = self._parse_duration(value)
                if new_duration is not None:
                    file_info["duration"] = new_duration
                else:
                    return False
            elif col == 5:  # BPM
                try:
                    file_info["bpm"] = int(value) if value.strip() else None
                except ValueError:
                    return False
            elif col == 6:  # Key
                file_info["key"] = value.strip().upper() if value else ""
            elif col == 10:
                tag_dict = parse_multi_dim_tags(value)
                file_info["tags"] = tag_dict
                self.dataChanged.emit(index, index, [role])
                return True
            else:
                return False
            self.dataChanged.emit(index, index, [role])
            DatabaseManager.instance().save_file_record(file_info)
            return True
        return False

    def _parse_duration(self, text: str) -> Optional[float]:
        try:
            parts = text.split(":")
            if len(parts) != 2:
                return None
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        except Exception:
            return None

    def format_size(self, size_in_bytes: Union[int, float]) -> str:
        if self.size_unit == "KB":
            return f"{size_in_bytes / 1024:.2f} KB"
        elif self.size_unit == "MB":
            return f"{size_in_bytes / (1024 ** 2):.2f} MB"
        elif self.size_unit == "GB":
            return f"{size_in_bytes / (1024 ** 3):.2f} GB"
        else:
            return str(size_in_bytes)

    def updateData(self, files: List[Dict[str, Any]]) -> None:
        self.beginResetModel()
        self._files = files
        self.endResetModel()

    def getFileAt(self, row: int) -> Optional[Dict[str, Any]]:
        if 0 <= row < len(self._files):
            return self._files[row]
        return None


class FileFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Proxy model for filtering files based on various criteria including
    name, 'unused' status, key, BPM range, and tags. Uses normalized setters.
    """

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        # Set filterKeyColumn to -1 to disable default filtering by a specific column
        # if we want all filtering logic explicitly in filterAcceptsRow based on self.filter_name_text
        self.setFilterKeyColumn(-1)  # Disable default column filtering

        # --- Filter Criteria Attributes (Internal State) ---
        # Use None to consistently represent "no filter" active
        self._filter_name_text: Optional[str] = None  # For explicit filename filtering
        self._filter_unused_only: bool = False
        self._filter_key: Optional[str] = None
        self._filter_bpm_min: Optional[int] = None
        self._filter_bpm_max: Optional[int] = None
        self._filter_tags_dict: Dict[str, List[str]] = (
            {}
        )  # AND logic within dim, AND logic between dims
        self._filter_tag_text: Optional[str] = (
            None  # Simple text search across all tags
        )

    # --- Public Setter Methods ---

    def set_filter_name(self, text: Optional[str]) -> None:
        """Sets the filter for the filename."""
        # Normalize: Empty string means no filter = None
        new_value = text.strip() if text else None
        if self._filter_name_text != new_value:
            self._filter_name_text = new_value
            logger.debug(f"Setting name filter: {self._filter_name_text}")
            self.invalidateFilter()

    def set_filter_unused(self, enabled: bool) -> None:
        """Sets the filter for showing only unused files."""
        if self._filter_unused_only != enabled:
            self._filter_unused_only = enabled
            logger.debug(f"Setting unused filter: {self._filter_unused_only}")
            self.invalidateFilter()

    def set_filter_key(self, key: Optional[str]) -> None:
        """Sets the filter for musical key (e.g., 'Cm', 'A#'). 'Any'/empty means no filter."""
        # Normalize: Treat empty string or specific keywords like "ANY" as None
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
        """Sets the filter for BPM range. 0 or None disables a boundary."""
        # Normalize: Treat 0 as None for min/max boundaries
        new_min = min_bpm if min_bpm and min_bpm > 0 else None
        new_max = max_bpm if max_bpm and max_bpm > 0 else None

        if self._filter_bpm_min != new_min or self._filter_bpm_max != new_max:
            self._filter_bpm_min = new_min
            self._filter_bpm_max = new_max
            logger.debug(
                f"Setting BPM range: {self._filter_bpm_min}-{self._filter_bpm_max}"
            )
            self.invalidateFilter()

    def add_filter_tag(self, dimension: str, value: str) -> None:
        """Adds a specific dimension:value tag requirement (AND logic)."""
        dim = dimension.lower().strip()
        val = value.upper().strip()
        if not dim or not val:
            return  # Ignore empty dimensions or values

        needs_update = False
        if dim not in self._filter_tags_dict:
            self._filter_tags_dict[dim] = []
        if val not in self._filter_tags_dict[dim]:
            self._filter_tags_dict[dim].append(val)
            needs_update = True

        if needs_update:
            logger.debug(f"Adding tag filter: {self.filter_tags_dict}")
            self.invalidateFilter()

    def remove_filter_tag(self, dimension: str, value: Optional[str] = None) -> None:
        """Removes a specific tag requirement or a whole dimension if value is None."""
        dim = dimension.lower().strip()
        needs_update = False
        if dim in self._filter_tags_dict:
            if value:  # Remove specific value
                val = value.upper().strip()
                if val in self._filter_tags_dict[dim]:
                    self._filter_tags_dict[dim].remove(val)
                    needs_update = True
                if not self._filter_tags_dict[
                    dim
                ]:  # Remove dimension if list becomes empty
                    del self._filter_tags_dict[dim]
                    # needs_update is already True if we removed the last item
            else:  # Remove whole dimension if no specific value given
                del self._filter_tags_dict[dim]
                needs_update = True

        if needs_update:
            logger.debug(f"Removing tag filter, new state: {self.filter_tags_dict}")
            self.invalidateFilter()

    def clear_filter_tags(self) -> None:
        """Clears all dimension:value tag filters."""
        if self._filter_tags_dict:
            self._filter_tags_dict = {}
            logger.debug("Clearing all tag filters.")
            self.invalidateFilter()

    def set_filter_tag_text(self, text: Optional[str]) -> None:
        """Sets a simple text filter to match any tag value (case-insensitive substring)."""
        # Normalize: empty string means no filter = None
        new_value = text.strip().upper() if text else None
        if self._filter_tag_text != new_value:
            self._filter_tag_text = new_value
            logger.debug(f"Setting tag text filter: {self._filter_tag_text}")
            self.invalidateFilter()

    # --- Filtering Logic ---

    def filterAcceptsRow(
        self, source_row: int, source_parent: QtCore.QModelIndex
    ) -> bool:
        """Applies all active filters to determine if a row should be shown."""
        # Get the underlying data dictionary from the source model
        model = self.sourceModel()
        if not isinstance(model, FileTableModel):
            logger.warning("Source model is not FileTableModel!")
            return True
        file_info = model.getFileAt(source_row)
        if not file_info:
            return False

        # 1. Apply Filename filter
        if self._filter_name_text:
            filename = os.path.basename(file_info.get("path", ""))
            # Using case sensitivity from self.filterCaseSensitivity()
            if self.filterCaseSensitivity() == QtCore.Qt.CaseSensitive:
                if self._filter_name_text not in filename:
                    return False
            else:
                if self._filter_name_text.lower() not in filename.lower():
                    return False

        # 2. Apply 'Only Unused' filter
        if self._filter_unused_only and file_info.get("used", False):
            return False

        # 3. Apply Key filter
        if self._filter_key is not None:  # Check against normalized internal state
            file_key = file_info.get("key", "").upper()
            # Handle N/A or empty keys matching specific filters if desired
            # Current logic: Exact match required unless filter is None
            if file_key != self._filter_key:
                # Special case: if filter is 'N/A', also match empty key for convenience?
                # if not (self._filter_key == "N/A" and file_key in ["N/A", ""]):
                #      return False
                # Sticking to exact match for now:
                return False

        # 4. Apply BPM filter
        if self._filter_bpm_min is not None or self._filter_bpm_max is not None:
            file_bpm = file_info.get("bpm")  # Could be None or int
            if file_bpm is None:  # If file has no BPM, it fails any active BPM filter
                return False
            if self._filter_bpm_min is not None and file_bpm < self._filter_bpm_min:
                return False
            if self._filter_bpm_max is not None and file_bpm > self._filter_bpm_max:
                return False

        # 5. Apply specific dimension:value tag filters (AND logic)
        if self._filter_tags_dict:
            file_tags = file_info.get("tags", {})
            if not isinstance(file_tags, dict):
                return False  # Cannot match if tags format is wrong
            for req_dim, req_values_list in self._filter_tags_dict.items():
                file_dim_values_list = file_tags.get(req_dim, [])
                # Check if *all* required values for this dimension are present in the file's tags
                if not all(
                    req_val in file_dim_values_list for req_val in req_values_list
                ):
                    return False  # File missing at least one required tag for this dimension

        # 6. Apply simple tag text filter (case-insensitive substring check across all tag values)
        if self._filter_tag_text is not None:  # Check against normalized internal state
            file_tags = file_info.get("tags", {})
            if not isinstance(file_tags, dict):
                return False  # Cannot match if tags format is wrong
            found_match = False
            # Iterate through all tag values in the dictionary
            for dim_values_list in file_tags.values():
                # Check if the filter text is a substring of any tag in the list
                if any(
                    self._filter_tag_text in tag_val.upper()
                    for tag_val in dim_values_list
                ):
                    found_match = True
                    break  # Found a match in this file, no need to check further tags
            if not found_match:
                return False  # Text filter was active but no match found in any tag

        # If all active filter checks passed
        return True
