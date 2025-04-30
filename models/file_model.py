# FILE: models/file_model.py
"""
File models for Musicians Organizer.

This module defines:
- FileTableModel: Represents file metadata for the main table view (standard columns only).
- FileFilterProxyModel: Provides advanced filtering capabilities, including new features
  and advanced text search.
"""

import logging
import os
import datetime
import math
import re # <<< Added for regex parsing
from typing import Any, Dict, List, Optional, Union

from PyQt5 import QtCore
# ADD DatabaseManager type hint import
from services.database_manager import DatabaseManager
from typing import TYPE_CHECKING # Use for type hinting only if needed to avoid circular imports at runtime
if TYPE_CHECKING:
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

    # MODIFY __init__
    def __init__(
        self,
        files: Optional[List[Dict[str, Any]]] = None,
        size_unit: str = "KB",
        db_manager: "DatabaseManager" = None, # <<< Accept db_manager
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._files = files if files is not None else []
        self.size_unit = size_unit
        if db_manager is None: # Basic check, ideally raise error or handle properly
             logger.error("FileTableModel initialized without a DatabaseManager!")
        self._db_manager = db_manager # <<< Store db_manager

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
                # Ensure consistency: if tags are somehow stored as a list, wrap in 'general'
                if isinstance(tags_data, list): tags_data = {"general": tags_data}
                # Handle cases where tags might not be a dict (though DB save should ensure dict)
                if not isinstance(tags_data, dict): return ""
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
                if not self._db_manager: # Check if db_manager exists
                     logger.error("Cannot save changes: DatabaseManager not available in FileTableModel.")
                     return False
                try:
                    # MODIFY: Use stored instance variable
                    self._db_manager.save_file_record(file_info) # <<< Use instance variable
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
            # Use consistent f-string formatting
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
# == FileFilterProxyModel (Updated for Advanced Search)                     ==
# ============================================================================
class FileFilterProxyModel(QtCore.QSortFilterProxyModel):
    """
    Proxy model for filtering files based on various criteria including
    'unused' status, key, BPM range, tags, advanced features, and advanced
    text search queries (name, path, tags, key with AND/OR/NOT logic).
    Uses normalized internal state for filters.
    """

    # --- Constants for Advanced Search ---
    # Regex to find terms, respecting quotes, field specifiers, and operators
    _QUERY_TOKEN_RE = re.compile(
        r'"([^"]*)"|'          # 1: Quoted string
        r'(\b(?:AND|OR|NOT)\b)|' # 2: Boolean Operators (case-insensitive due to logic later)
        r'([a-zA-Z_]+):"([^"]*)"|' # 3, 4: field:"quoted value"
        r'([a-zA-Z_]+):(\S+)|'  # 5, 6: field:value (non-space)
        r'(\S+)'               # 7: Default term (non-space)
    , re.IGNORECASE)

    _DEFAULT_SEARCH_FIELDS = ['name', 'tag'] # Fields searched for default terms
    _SUPPORTED_FIELDS = {'name', 'path', 'tag', 'key'} # Fields allowed in field:value

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive) # Global case setting
        self.setFilterKeyColumn(-1)
        self.setDynamicSortFilter(True)

        logger.debug("Initializing FileFilterProxyModel filters.")
        # --- Filter Criteria Attributes (Internal State) ---
        self._filter_unused_only: bool = False
        self._filter_key: Optional[str] = None # Dedicated key filter (from combobox)
        self._filter_bpm_min: Optional[int] = None
        self._filter_bpm_max: Optional[int] = None
        self._filter_tags_dict: Dict[str, List[str]] = {} # Specific tag filter (future use?)
        self._filter_tag_text: Optional[str] = None # Simple tag text contains filter
        # ADDED: State for parsed advanced query
        self._advanced_query_structure: Optional[List[Dict[str, Any]]] = None

        # --- New Feature Filters ---
        self._filter_lufs_min: Optional[float] = None
        self._filter_lufs_max: Optional[float] = None
        self._filter_bit_depth: Optional[int] = None
        self._filter_pitch_hz_min: Optional[float] = None
        self._filter_pitch_hz_max: Optional[float] = None
        self._filter_attack_time_min: Optional[float] = None # Stored in seconds
        self._filter_attack_time_max: Optional[float] = None # Stored in seconds

    # --- Advanced Search Parser (NEW) ---
    def _parse_advanced_query(self, query_string: str) -> Optional[List[Dict[str, Any]]]:
        """
        Parses the advanced query string into a structured list of conditions.
        Example Output: [{'term': 'kick', 'fields': ['name','tag'], 'negated': False, 'op': 'AND'}, ...]
        Returns None if query is empty or invalid.
        """
        if not query_string or not query_string.strip():
            return None

        parsed_structure: List[Dict[str, Any]] = []
        current_op = 'AND' # Default operator between terms
        current_negated = False
        # Keep track of the end position of the last processed match
        last_pos = 0

        for match in self._QUERY_TOKEN_RE.finditer(query_string):
            # Check for unprocessed text between matches (usually invalid syntax)
            if match.start() > last_pos and query_string[last_pos:match.start()].strip():
                logger.warning(f"Ignoring potentially invalid syntax between tokens: '{query_string[last_pos:match.start()].strip()}'")
            last_pos = match.end()

            quoted_term, operator, field_q, value_q, field, value, default_term = match.groups()

            # --- Handle Operators ---
            if operator:
                op_upper = operator.upper()
                if op_upper == 'NOT':
                    # Apply negation only if it's not already negated (avoid double negatives)
                    if not current_negated:
                        current_negated = True
                    else:
                        logger.debug("Ignoring consecutive 'NOT' operators.")
                    # 'NOT' applies to the *next* term, doesn't change AND/OR relationship
                    continue # Move to next token
                elif op_upper in ['AND', 'OR']:
                    # Set the operator for the *next* term, only if a term follows
                    # We peek ahead slightly implicitly by checking if a term is added later
                    current_op = op_upper
                    current_negated = False # AND/OR resets negation
                    continue # Move to next token
                else:
                    logger.debug(f"Treating unrecognized operator '{operator}' as search term.")
                    default_term = operator # Fallthrough

            # --- Determine Term, Field(s), and Value ---
            term: Optional[str] = None
            fields: List[str] = self._DEFAULT_SEARCH_FIELDS # Default fields

            if quoted_term is not None: term = quoted_term
            elif field_q and value_q is not None: # field:"quoted value" (check value_q explicitly)
                field = field_q.lower()
                if field in self._SUPPORTED_FIELDS: fields = [field]
                else: logger.warning(f"Unsupported field '{field}' specified, using default search."); fields = self._DEFAULT_SEARCH_FIELDS
                term = value_q # Value can be empty string if quotes are empty ""
            elif field and value: # field:value
                field = field.lower()
                if field in self._SUPPORTED_FIELDS: fields = [field]
                else: logger.warning(f"Unsupported field '{field}' specified, using default search."); fields = self._DEFAULT_SEARCH_FIELDS
                term = value
            elif default_term: # Default term (unquoted, no field)
                # --- FIX: Prevent interpreting 'field:' as a term ---
                # If the default term looks like an incomplete field specifier, ignore it.
                if default_term.endswith(':') and default_term[:-1].lower() in self._SUPPORTED_FIELDS:
                    logger.debug(f"Ignoring incomplete field specifier '{default_term}'")
                    term = None # Do not treat as a term
                else:
                    term = default_term
                # --- END FIX ---

            # --- Add Condition to Structure ---
            # Ensure term is not None and not just whitespace after potential stripping
            if term is not None:
                 term_stripped = term.strip()
                 if term_stripped: # Only add if term is non-empty after stripping
                    condition = {
                        'term': term_stripped, # Use stripped term
                        'fields': fields,
                        'negated': current_negated,
                        'op': current_op
                    }
                    if not parsed_structure: condition['op'] = 'AND'
                    parsed_structure.append(condition)

                    # Reset negation and operator for the *next* term
                    current_negated = False
                    current_op = 'AND' # Reset to default AND unless next token is OR
                 elif term != term_stripped: # Log if only whitespace was ignored
                     logger.debug(f"Ignored term consisting only of whitespace.")

        # Check for trailing unprocessed text (e.g., trailing operator)
        if last_pos < len(query_string) and query_string[last_pos:].strip():
             logger.warning(f"Ignoring trailing invalid syntax: '{query_string[last_pos:].strip()}'")

        logger.debug(f"Parsed query '{query_string}' into: {parsed_structure}")
        return parsed_structure if parsed_structure else None

    # --- Public Setter Methods ---

    # ADDED: Setter for the advanced query
    def set_advanced_filter(self, query_string: Optional[str]) -> None:
        """Parses and sets the advanced text search query."""
        logger.debug(f"Received advanced query string: '{query_string}'")
        new_structure = self._parse_advanced_query(query_string) if query_string else None
        if self._advanced_query_structure != new_structure:
            logger.debug(f"Updating advanced query structure. Old: {self._advanced_query_structure}, New: {new_structure}")
            self._advanced_query_structure = new_structure
            self.invalidateFilter()
        else:
            logger.debug("Advanced query structure unchanged, skipping invalidation.")

    # --- Keep other existing setters ---
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
            logger.debug(f"Setting dedicated key filter: {self._filter_key}")
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
        dim = dimension.lower().strip(); val = value.upper().strip()
        if not dim or not val: return
        needs_update = False
        if dim not in self._filter_tags_dict: self._filter_tags_dict[dim] = []
        if val not in self._filter_tags_dict[dim]:
            self._filter_tags_dict[dim].append(val); needs_update = True
        if needs_update:
            logger.debug(f"Adding tag filter: {self._filter_tags_dict}")
            self.invalidateFilter()

    def remove_filter_tag(self, dimension: str, value: Optional[str] = None) -> None:
        dim = dimension.lower().strip(); needs_update = False
        if dim in self._filter_tags_dict:
            if value:
                val = value.upper().strip()
                if val in self._filter_tags_dict[dim]:
                    self._filter_tags_dict[dim].remove(val); needs_update = True
                if not self._filter_tags_dict[dim]: del self._filter_tags_dict[dim]
            else:
                del self._filter_tags_dict[dim]; needs_update = True
        if needs_update:
            logger.debug(f"Removing tag filter, new state: {self._filter_tags_dict}")
            self.invalidateFilter()

    def clear_filter_tags(self) -> None:
        if self._filter_tags_dict:
            self._filter_tags_dict = {}; logger.debug("Clearing all specific tag filters.")
            self.invalidateFilter()

    def set_filter_tag_text(self, text: Optional[str]) -> None:
        new_value = text.strip().upper() if text else None
        if self._filter_tag_text != new_value:
            self._filter_tag_text = new_value
            logger.debug(f"Setting tag text filter: {self._filter_tag_text}")
            self.invalidateFilter()

    # --- New Feature Filter Setters (Unchanged) ---
    def set_filter_lufs_range(self, min_lufs: Optional[float], max_lufs: Optional[float]) -> None:
        logger.debug(f"set_filter_lufs_range received: min={min_lufs}, max={max_lufs}")
        try:
            new_min = float(min_lufs) if min_lufs is not None else None
            new_max = float(max_lufs) if max_lufs is not None else None
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid type received in set_filter_lufs_range: min='{min_lufs}', max='{max_lufs}'. Error: {e}")
            new_min, new_max = None, None
        if self._filter_lufs_min != new_min or self._filter_lufs_max != new_max:
            logger.debug(f"LUFS filter state changing from ({self._filter_lufs_min}, {self._filter_lufs_max}) to ({new_min}, {new_max})")
            self._filter_lufs_min = new_min
            self._filter_lufs_max = new_max
            logger.debug("Calling self.invalidateFilter() due to LUFS range change.")
            self.invalidateFilter()
        else:
            logger.debug("set_filter_lufs_range called but new values match existing state. No invalidation needed.")

    def set_filter_bit_depth(self, bit_depth: Optional[int]) -> None:
        try: val = int(bit_depth) if bit_depth not in (None, "", "Any", 0) else None
        except (TypeError, ValueError): val = None
        if self._filter_bit_depth != val:
            self._filter_bit_depth = val; logger.debug("Setting bit-depth filter: %s", val); self.invalidateFilter()

    def set_filter_pitch_hz_range(self, min_hz: Optional[float], max_hz: Optional[float]) -> None:
        new_min = float(min_hz) if min_hz else None; new_max = float(max_hz) if max_hz else None
        if (new_min, new_max) != (self._filter_pitch_hz_min, self._filter_pitch_hz_max):
            self._filter_pitch_hz_min, self._filter_pitch_hz_max = new_min, new_max
            logger.debug("Setting pitch-Hz range: %s – %s", new_min, new_max); self.invalidateFilter()

    def set_filter_attack_time_range(self, min_ms: Optional[float], max_ms: Optional[float]) -> None:
        new_min = (min_ms / 1000.0) if min_ms else None; new_max = (max_ms / 1000.0) if max_ms else None
        if (new_min, new_max) != (self._filter_attack_time_min, self._filter_attack_time_max):
            self._filter_attack_time_min, self._filter_attack_time_max = new_min, new_max
            logger.debug("Setting attack-time range: %s – %s", new_min, new_max); self.invalidateFilter()

    # --- Helper for Advanced Query Evaluation (NEW) ---
    def _check_condition(self, condition: Dict[str, Any], file_info: Dict[str, Any]) -> bool:
        """Checks if a single parsed condition matches the file_info."""
        term = condition['term'].lower() # Compare case-insensitively
        fields_to_check = condition['fields']
        negated = condition['negated']

        match_found = False
        for field in fields_to_check:
            value_to_check: Optional[Union[str, Dict, List]] = None
            target_text: Optional[str] = None

            if field == 'name':
                target_text = os.path.basename(file_info.get("path", "")).lower()
            elif field == 'path':
                target_text = file_info.get("path", "").lower()
            elif field == 'key':
                target_text = file_info.get("key", "").lower()
            elif field == 'tag':
                tags_data = file_info.get("tags", {})
                if isinstance(tags_data, dict):
                    # Check if term exists in any tag value list
                    for tag_list in tags_data.values():
                        if isinstance(tag_list, list):
                            if any(term in str(tag).lower() for tag in tag_list):
                                match_found = True
                                break # Found in tags, no need to check other tag dimensions
                    if match_found: break # Found in tags, no need to check other fields for this condition
                continue # Skip to next field if tags aren't a dict or no match found

            # Perform check if target_text was determined
            if target_text is not None:
                if term in target_text:
                    match_found = True
                    break # Found in this field, no need to check others for this condition

        # Apply negation
        return not match_found if negated else match_found

    # --- Filtering Logic ---
    def filterAcceptsRow(
        self, source_row: int, source_parent: QtCore.QModelIndex
    ) -> bool:
        """
        Applies ALL active filters to determine if a row should be shown.
        Includes evaluation of the advanced text search query.
        """
        model = self.sourceModel()
        if not isinstance(model, FileTableModel): return True
        file_info = model.getFileAt(source_row)
        if not file_info or not isinstance(file_info, dict): return False

        # --- Apply Standard Filters (Excluding simple name filter) ---
        if self._filter_unused_only and file_info.get("used", False): return False
        if self._filter_key is not None:
            file_key = file_info.get("key", "").strip().upper()
            if file_key != self._filter_key: return False
        if self._filter_bpm_min is not None or self._filter_bpm_max is not None:
            file_bpm = file_info.get("bpm");
            if file_bpm is None: return False
            try: file_bpm_f = float(file_bpm)
            except (ValueError, TypeError): return False
            if self._filter_bpm_min is not None and file_bpm_f < self._filter_bpm_min: return False
            if self._filter_bpm_max is not None and file_bpm_f > self._filter_bpm_max: return False
        if self._filter_tags_dict:
             file_tags = file_info.get("tags", {});
             if not isinstance(file_tags, dict): return False
             for req_dim, req_values_list in self._filter_tags_dict.items():
                 file_dim_values_list = file_tags.get(req_dim.lower(), [])
                 file_dim_values_upper_set = {str(tag).upper() for tag in file_dim_values_list}
                 if not all(req_val in file_dim_values_upper_set for req_val in req_values_list): return False
        if self._filter_tag_text is not None:
            file_tags = file_info.get("tags", {});
            if not isinstance(file_tags, dict): return False
            found_match = False; search_text = self._filter_tag_text
            for dim_values_list in file_tags.values():
                if any(search_text in str(tag_val).upper() for tag_val in dim_values_list):
                    found_match = True; break
            if not found_match: return False

        # --- Apply NEW Feature Filters (Unchanged) ---
        if self._filter_lufs_min is not None or self._filter_lufs_max is not None:
            file_lufs = file_info.get("loudness_lufs");
            if file_lufs is None: return False
            try: file_lufs_f = float(file_lufs)
            except (ValueError, TypeError): return False
            if self._filter_lufs_min is not None and file_lufs_f < self._filter_lufs_min: return False
            if self._filter_lufs_max is not None and file_lufs_f > self._filter_lufs_max: return False
        if self._filter_bit_depth is not None:
            file_bit_depth = file_info.get("bit_depth");
            if file_bit_depth is None: return False
            try: file_bit_depth_i = int(file_bit_depth)
            except (ValueError, TypeError): return False
            if file_bit_depth_i != self._filter_bit_depth: return False
        if self._filter_pitch_hz_min is not None or self._filter_pitch_hz_max is not None:
            file_pitch = file_info.get("pitch_hz");
            if file_pitch is None: return False
            try: file_pitch_f = float(file_pitch)
            except (ValueError, TypeError): return False
            min_bound = self._filter_pitch_hz_min; max_bound = self._filter_pitch_hz_max
            if (min_bound is not None) and (max_bound is None): max_bound = min_bound * 1.5
            elif (max_bound is not None) and (min_bound is None): min_bound = max_bound / 1.5
            if (min_bound is not None) and (file_pitch_f < min_bound): return False
            if (max_bound is not None) and (file_pitch_f > max_bound): return False
        if self._filter_attack_time_min is not None or self._filter_attack_time_max is not None:
            file_attack = file_info.get("attack_time");
            if file_attack is None: return False
            try: file_attack_f = float(file_attack)
            except (ValueError, TypeError): return False
            if self._filter_attack_time_min is not None and file_attack_f < self._filter_attack_time_min: return False
            if self._filter_attack_time_max is not None and file_attack_f > self._filter_attack_time_max: return False


        # --- Evaluate Advanced Search Query (NEW LOGIC) ---
        if self._advanced_query_structure:
            overall_match = True # Default for first condition or empty structure
            for i, condition in enumerate(self._advanced_query_structure):
                condition_match = self._check_condition(condition, file_info)
                op = condition['op'] # Operator linking previous result to this one

                if i == 0: # First condition sets the initial state
                    overall_match = condition_match
                elif op == 'AND':
                    overall_match = overall_match and condition_match
                elif op == 'OR':
                    overall_match = overall_match or condition_match

                # Optimization: If overall_match becomes False with AND, can stop early.
                # If overall_match becomes True with OR, could potentially stop if ORs are grouped?
                # For simplicity now, evaluate all conditions.
                # if not overall_match and op == 'AND': break # Optional optimization

            # If after evaluating all conditions, the result is False, exclude row
            if not overall_match:
                return False


        # --- If all applicable filters passed ---
        return True # Include the row